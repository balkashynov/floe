"""Fresh-kernel execution. Workspaces are disposable copies, not a security sandbox."""

from __future__ import annotations

import hashlib
import json
import keyword
import os
import tempfile
import time
import uuid
from pathlib import Path

import nbformat
from jupyter_client import AsyncKernelManager
from jupyter_client.kernelspec import KernelSpecManager
from jupyter_core.utils import run_sync
from nbclient import NotebookClient

from .compare import evaluate_runs, validate_policy

MIME = "application/vnd.floe.snapshot+json"


def digest(value):
    return hashlib.sha256(value).hexdigest()


def load_contract(path, notebook):
    contract = json.loads(Path(path).read_text())
    if not isinstance(contract, dict):
        raise TypeError("Contract must be a JSON object")
    if contract.get("schema") != 1:
        raise ValueError("Contract schema must be 1")
    if set(contract) - {"schema", "title", "observations", "timeout", "max_values", "inputs"}:
        raise ValueError("Unknown contract fields")
    ids = [c.get("id") for c in notebook.cells]
    if len(set(ids)) != len(ids) or None in ids:
        raise ValueError("Notebook must have unique cell IDs")
    watches = contract.get("observations")
    if not isinstance(watches, list) or not watches:
        raise ValueError("Declare at least one observation")
    names = set()
    for watch in watches:
        if not isinstance(watch, dict):
            raise TypeError("Each observation must be a JSON object")
        if set(watch) - {"name", "cell", "variable", "policy"}:
            raise ValueError("Unknown observation fields")
        name = watch.get("name")
        if not isinstance(name, str) or not name or name in names:
            raise ValueError("Observation names must be nonempty and unique")
        names.add(name)
        variable = watch.get("variable", "")
        if (
            not isinstance(variable, str)
            or not variable.isidentifier()
            or keyword.iskeyword(variable)
        ):
            raise ValueError("Observe a variable name, not an expression or function call")
        if (
            watch.get("cell") not in ids
            or notebook.cells[ids.index(watch["cell"])].cell_type != "code"
        ):
            raise ValueError(f"Observation {name}: cell must identify a code cell")
        validate_policy(watch.get("policy", {}))
    for key, default, upper in (("timeout", 60, 3600), ("max_values", 100000, 1000000)):
        value = contract.get(key, default)
        if isinstance(value, bool) or not isinstance(value, int) or not 0 < value <= upper:
            raise ValueError(f"{key} must be an integer between 1 and {upper}")
    inputs = contract.get("inputs", [])
    if not isinstance(inputs, list) or not all(isinstance(x, str) for x in inputs):
        raise ValueError("inputs must be a list of relative file paths")
    return contract


def input_files(root, contract):
    files = []
    for value in contract.get("inputs", []):
        relative = Path(value)
        path = root / relative
        if relative.is_absolute() or ".." in relative.parts or path.is_symlink():
            raise ValueError("Inputs must be regular relative files within the notebook directory")
        if not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError(f"Input is missing or outside the notebook directory: {value}")
        files.append((relative, path.read_bytes()))
    return files


def source_manifest(notebook, files):
    # Stored outputs and counts are excluded; cell metadata is fingerprinted.
    source = [
        {"id": c.id, "cell_type": c.cell_type, "source": c.source, "metadata": dict(c.metadata)}
        for c in notebook.cells
    ]
    return {
        "notebook_sha256": digest(json.dumps(source, sort_keys=True).encode()),
        "inputs": {str(p): digest(data) for p, data in files},
    }


def execute(notebook, contract, python, files, output, label):
    python = str(Path(python).absolute())
    if not Path(python).is_file():
        raise ValueError(f"Python executable not found: {python}")
    output.mkdir(parents=True, exist_ok=False)
    run = {
        "label": label,
        "observations": {},
        "capture_errors": {},
        "cells": [],
        "error": None,
        "status": "complete",
    }
    capture_source = Path(__file__).with_name("capture.py").read_text()
    token = "__floe_" + uuid.uuid4().hex
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="floe-") as directory:
        work = Path(directory)
        for relative, data in files:
            destination = work / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
        nb = nbformat.v4.new_notebook()
        bootstrap = (
            f"import types as {token}_types\n"
            f"{token} = {token}_types.ModuleType('floe_capture')\n"
            f"exec({capture_source!r}, {token}.__dict__)\n"
            f"from IPython.display import display as {token}_display\n"
            f"{token}_display({{{MIME!r}: {{'environment': {token}.environment()}}}}, raw=True)"
        )
        nb.cells.append(nbformat.v4.new_code_cell(bootstrap))
        spec_dir = work / "kernels" / "floe"
        spec_dir.mkdir(parents=True)
        (spec_dir / "kernel.json").write_text(
            json.dumps(
                {
                    "argv": [python, "-m", "ipykernel_launcher", "-f", "{connection_file}"],
                    "display_name": "Floe isolated kernel",
                    "language": "python",
                }
            )
        )
        km = AsyncKernelManager(
            kernel_name="floe",
            kernel_spec_manager=KernelSpecManager(
                kernel_dirs=[str(work / "kernels")], ensure_native_kernel=False
            ),
        )
        km.connection_file = str(work / "kernel.json")
        client = NotebookClient(
            nb,
            km=km,
            timeout=contract.get("timeout", 60),
            allow_errors=False,
            record_timing=False,
            shutdown_kernel="immediate",
        )
        # No credentials are deliberately forwarded. Trusted notebooks still have
        # the host user's filesystem/network permissions; this is not a sandbox.
        env = {
            k: v
            for k, v in os.environ.items()
            if k in ("PATH", "SYSTEMROOT", "WINDIR", "LANG", "LC_ALL", "TMPDIR")
        }
        env.update(
            HOME=str(work),
            IPYTHONDIR=str(work / "ipython"),
            JUPYTER_CONFIG_DIR=str(work / "jupyter"),
            JUPYTER_RUNTIME_DIR=str(work / "jupyter-runtime"),
            MPLCONFIGDIR=str(work / "mpl"),
            PYTHONNOUSERSITE="1",
        )
        try:
            with client.setup_kernel(cwd=str(work), env=env, cleanup_kc=True):
                client.execute_cell(nb.cells[0], 0)
                for out in nb.cells[0].outputs:
                    payload = out.get("data", {}).get(MIME)
                    if payload:
                        run["environment"] = payload["environment"]
                for cell in notebook.cells:
                    if cell.cell_type != "code":
                        continue
                    original = nbformat.from_dict(dict(cell))
                    original.outputs = []
                    original.execution_count = None
                    # raises-exception metadata must never silently accept failures.
                    original.metadata.pop("tags", None)
                    nb.cells.append(original)
                    cell_started = time.monotonic()
                    try:
                        client.execute_cell(original, len(nb.cells) - 1)
                    except Exception as exc:  # noqa: BLE001 - persist all kernel failures as evidence
                        error = next((o for o in original.outputs if o.output_type == "error"), {})
                        run["error"] = {
                            "cell": cell.id,
                            "type": error.get("ename", type(exc).__name__),
                            "message": error.get("evalue", str(exc))[:1500],
                        }
                        run["status"] = "error"
                    run["cells"].append(
                        {
                            "id": cell.id,
                            "source": cell.source,
                            "seconds": time.monotonic() - cell_started,
                            "outputs": list(original.outputs),
                        }
                    )
                    if run["error"]:
                        break
                    for watch in contract["observations"]:
                        if watch["cell"] != cell.id:
                            continue
                        variable, name = watch["variable"], watch["name"]
                        code = (
                            f"try:\n"
                            f"    {token}_result = {{'name': {name!r}, 'snapshot': {token}.snapshot({variable}, {contract.get('max_values', 100000)})}}\n"
                            f"except Exception as {token}_exc:\n"
                            f"    {token}_result = {{'name': {name!r}, 'error': type({token}_exc).__name__ + ': ' + str({token}_exc)}}\n"
                            f"{token}_display({{{MIME!r}: {token}_result}}, raw=True)"
                        )
                        probe = nbformat.v4.new_code_cell(code)
                        nb.cells.append(probe)
                        client.execute_cell(probe, len(nb.cells) - 1)
                        payloads = [o.get("data", {}).get(MIME) for o in probe.outputs]
                        payload = next((p for p in payloads if p and p.get("name") == name), None)
                        if payload and "snapshot" in payload:
                            run["observations"][name] = payload["snapshot"]
                        else:
                            run["capture_errors"][name] = (payload or {}).get(
                                "error", "Probe emitted no observation"
                            )
        except Exception as exc:  # noqa: BLE001 - startup/protocol errors must not become a pass
            run["status"] = "error"
            run["error"] = {
                "cell": "kernel",
                "type": type(exc).__name__,
                "message": str(exc)[:1500],
            }
        finally:
            if km.has_kernel:
                run_sync(km.shutdown_kernel)(now=True)
        # Only original cells/outputs are persisted; runtime paths and connection
        # details in the injected probe/bootstrap are not part of the artifact.
        executed = nbformat.from_dict(json.loads(nbformat.writes(notebook)))
        by_id = {c["id"]: c for c in run["cells"]}
        for cell in executed.cells:
            if cell.cell_type == "code":
                cell.outputs = by_id.get(cell.id, {}).get("outputs", [])
                cell.execution_count = None
        nbformat.write(executed, output / "executed.ipynb")
    run["seconds"] = time.monotonic() - started
    (output / "run.json").write_text(json.dumps(run, indent=2, allow_nan=False) + "\n")
    return run


def run_matrix(notebook_path, contract_path, reference_python, candidate_python, output, repeats=2):
    if not 2 <= repeats <= 10:
        raise ValueError("Use 2 to 10 repeats per runtime")
    output = Path(output)
    if output.exists():
        raise ValueError("Output already exists; choose a fresh directory to preserve evidence")
    notebook_path = Path(notebook_path)
    notebook = nbformat.read(notebook_path, as_version=4)
    contract = load_contract(contract_path, notebook)
    files = input_files(notebook_path.parent, contract)
    manifest = source_manifest(notebook, files)
    manifest["contract_sha256"] = digest(json.dumps(contract, sort_keys=True).encode())
    output.mkdir(parents=True)
    nbformat.write(notebook, output / "source.ipynb")
    (output / "contract.json").write_text(json.dumps(contract, indent=2) + "\n")
    for relative, data in files:
        path = output / "inputs" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    groups = {"reference": [], "candidate": []}
    # Interleaving reduces systematic order effects. Each run has its own kernel.
    for i in range(repeats):
        for label, python in (("reference", reference_python), ("candidate", candidate_python)):
            print(f"{label} {i + 1}/{repeats}: {notebook_path.name}", flush=True)
            groups[label].append(
                execute(notebook, contract, python, files, output / f"{label}-{i + 1}", label)
            )
    result = {
        "schema": 1,
        "title": contract.get("title", notebook_path.stem),
        "manifest": manifest,
        "contract": contract,
        "runs": groups,
        **evaluate_runs(groups["reference"], groups["candidate"], contract),
    }
    result["environment_delta"] = package_delta(groups)
    (output / "report.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    from .report import render

    (output / "report.html").write_text(render(result))
    return result


def package_delta(groups):
    a = groups["reference"][0].get("environment", {}).get("packages", {})
    b = groups["candidate"][0].get("environment", {}).get("packages", {})
    return [
        {"package": k, "reference": a.get(k), "candidate": b.get(k)}
        for k in sorted(a.keys() | b.keys())
        if a.get(k) != b.get(k)
    ]

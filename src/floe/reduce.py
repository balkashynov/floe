"""Bounded cell deletion with a preserved, repeat-checked observation witness."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import nbformat

from .compare import compare
from .runner import digest, input_files, run_matrix, source_manifest


def reduce_report(report_directory, name, reference, candidate, output, budget=12):
    root, output = Path(report_directory), Path(output)
    if not 1 <= budget <= 100:
        raise ValueError("Reduction budget must be between 1 and 100 trials")
    if output.exists():
        raise ValueError("Reducer output already exists")
    report = json.loads((root / "report.json").read_text())
    target = next((f for f in report["findings"] if f["name"] == name), None)
    if not target or target["status"] != "changed":
        raise ValueError("Reduce one stable changed observation, not an inconclusive result")
    notebook = nbformat.read(root / "source.ipynb", as_version=4)
    original_contract = report["contract"]
    files = input_files(root / "inputs", original_contract)
    manifest = source_manifest(notebook, files)
    manifest["contract_sha256"] = digest(json.dumps(original_contract, sort_keys=True).encode())
    if manifest != report.get("manifest"):
        raise ValueError("Saved source, inputs or contract do not match the report manifest")
    contract = dict(original_contract)
    contract["observations"] = [w for w in contract["observations"] if w["name"] == name]
    output.mkdir(parents=True)
    trials = []

    def check(cells):
        trial = output / f"trial-{len(trials) + 1}"
        trial.mkdir()
        nb = nbformat.v4.new_notebook(cells=cells)
        nbformat.write(nb, trial / "notebook.ipynb")
        (trial / "contract.json").write_text(json.dumps(contract, indent=2))
        for value in contract.get("inputs", []):
            relative = Path(value)
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("Invalid captured input path")
            destination = trial / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(root / "inputs" / relative, destination)
        result = run_matrix(
            trial / "notebook.ipynb",
            trial / "contract.json",
            reference,
            candidate,
            trial / "evidence",
            repeats=2,
        )
        finding = result["findings"][0]
        preserved = finding["status"] == "changed"
        # A different failure is not a successful reduction. Preserve both sides
        # exactly, even if the original comparison policy permits tolerance.
        for side in ("reference", "candidate"):
            for run in result["runs"][side]:
                observed = run["observations"].get(name)
                preserved = bool(
                    preserved
                    and observed is not None
                    and compare(target[side], observed)["equal"]
                    and not run.get("error")
                )
        trials.append(
            {
                "trial": len(trials) + 1,
                "cell_ids": [c.id for c in cells],
                "preserved": preserved,
                "verdict": result["verdict"],
            }
        )
        return preserved

    current = list(notebook.cells)
    # First verify the saved witness in the supplied current environments.
    if not check(current):
        raise ValueError(
            "Original witness did not reproduce in these environments; trials retained"
        )
    complete = False
    while len(trials) < budget:
        removed = False
        for cell in list(current):
            if cell.cell_type != "code" or cell.id == target["cell"]:
                continue
            if len(trials) >= budget:
                break
            proposal = [c for c in current if c.id != cell.id]
            if check(proposal):
                current = proposal
                removed = True
                break
        else:
            complete = True
            break
        if not removed:
            break
    final = output / "reproducer"
    final.mkdir()
    nbformat.write(nbformat.v4.new_notebook(cells=current), final / "notebook.ipynb")
    (final / "contract.json").write_text(json.dumps(contract, indent=2) + "\n")
    for value in contract.get("inputs", []):
        destination = final / value
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / "inputs" / value, destination)
    summary = {
        "schema": 1,
        "observation": name,
        "original_code_cells": sum(c.cell_type == "code" for c in notebook.cells),
        "remaining_code_cells": sum(c.cell_type == "code" for c in current),
        "cell_deletion_minimal": complete,
        "budget": budget,
        "trials": trials,
        "claim": "One-cell-deletion minimal under this witness oracle"
        if complete
        else "Budget-limited witness-preserving reduction; minimality not established",
        "limits": "Preserves only the selected observations; other outputs and side effects may change.",
    }
    (output / "reduction.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary

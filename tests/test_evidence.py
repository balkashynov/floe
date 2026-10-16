import json
from pathlib import Path

import nbformat
import pytest

from floe.capture import Recorder, snapshot
from floe.cli import main
from floe.compare import evaluate_runs
from floe.reduce import reduce_report
from floe.runner import digest, source_manifest


def test_environment_drift_refuses_upgrade_claim():
    runs = [
        {
            "environment": {"python": "3.12", "packages": {"pandas": v}},
            "observations": {"x": snapshot(1)},
        }
        for v in ("2.3.3", "3.0.0")
    ]
    contract = {"observations": [{"name": "x", "cell": "c", "variable": "x"}]}
    assert evaluate_runs(runs, runs, contract)["verdict"] == "inconclusive"
    del runs[0]["environment"]
    assert evaluate_runs(runs, runs, contract)["environment_errors"]


def test_recorder_to_cli_and_mismatched_source(tmp_path):
    paths = []
    for i in range(4):
        recorder = Recorder(
            source_id="notebook-and-data-v1", label="reference" if i < 2 else "candidate"
        )
        recorder.observe("x", 1 if i < 2 else 2)
        p = tmp_path / f"capture-{i}.json"
        recorder.write(p)
        paths.append(str(p))
    contract = tmp_path / "contract.json"
    contract.write_text(
        json.dumps({"schema": 1, "observations": [{"name": "x", "cell": "c", "variable": "x"}]})
    )
    args = [
        "compare-captures",
        "--reference",
        *paths[:2],
        "--candidate",
        *paths[2:],
        "--contract",
        str(contract),
    ]
    assert main([*args, "--output", str(tmp_path / "comparison")]) == 1
    report = json.loads((tmp_path / "comparison/report.json").read_text())
    assert report["verdict"] == "changed" and "caller-attested" in report["provenance"]
    capture = json.loads(Path(paths[3]).read_text())
    capture["source_id"] = "different-input"
    Path(paths[3]).write_text(json.dumps(capture))
    assert main([*args, "--output", str(tmp_path / "invalid")]) == 2
    assert not (tmp_path / "invalid").exists()


def report_fixture(root):
    root.mkdir()
    nb = nbformat.v4.new_notebook(cells=[nbformat.v4.new_code_cell("x = 1", id="c")])
    nbformat.write(nb, root / "source.ipynb")
    contract = {"schema": 1, "observations": [{"name": "x", "cell": "c", "variable": "x"}]}
    manifest = source_manifest(nb, [])
    manifest["contract_sha256"] = digest(json.dumps(contract, sort_keys=True).encode())
    target = {
        "name": "x",
        "cell": "c",
        "status": "changed",
        "reference": snapshot(1),
        "candidate": snapshot(2),
    }
    (root / "report.json").write_text(
        json.dumps({"contract": contract, "manifest": manifest, "findings": [target]})
    )
    return nb


def test_reducer_rejects_changed_artifact_before_execution(tmp_path):
    root = tmp_path / "saved"
    nb = report_fixture(root)
    nb.cells[0].source = "x = 999"
    nbformat.write(nb, root / "source.ipynb")
    with pytest.raises(ValueError, match="manifest"):
        reduce_report(root, "x", "unused", "unused", tmp_path / "reduced")
    assert not (tmp_path / "reduced").exists()


@pytest.mark.parametrize("value,error", [(3, None), (2, {"type": "NameError"})])
def test_reducer_does_not_accept_different_change_or_error(tmp_path, monkeypatch, value, error):
    root = tmp_path / "saved"
    report_fixture(root)
    fake = {
        "verdict": "changed",
        "findings": [{"status": "changed"}],
        "runs": {
            "reference": [{"observations": {"x": snapshot(1)}}] * 2,
            "candidate": [{"observations": {"x": snapshot(value)}, "error": error}] * 2,
        },
    }
    monkeypatch.setattr("floe.reduce.run_matrix", lambda *a, **kw: fake)
    with pytest.raises(ValueError, match="did not reproduce"):
        reduce_report(root, "x", "unused", "unused", tmp_path / "reduced")

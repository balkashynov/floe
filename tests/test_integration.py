import json
import sys

import nbformat

from floe.runner import run_matrix


def execute_case(tmp_path, source, *, timeout=10, inputs=None):
    notebook = tmp_path / "test.ipynb"
    nbformat.write(
        nbformat.v4.new_notebook(cells=[nbformat.v4.new_code_cell(source, id="c")]), notebook
    )
    contract = tmp_path / "contract.json"
    contract.write_text(
        json.dumps(
            {
                "schema": 1,
                "timeout": timeout,
                "inputs": inputs or [],
                "observations": [{"name": "x", "variable": "x", "cell": "c"}],
            }
        )
    )
    return run_matrix(notebook, contract, sys.executable, sys.executable, tmp_path / "result")


def test_new_kernel_and_disposable_input_files(tmp_path):
    (tmp_path / "data.txt").write_text("original")
    result = execute_case(
        tmp_path,
        "from pathlib import Path\nx = Path('data.txt').read_text()\nPath('data.txt').write_text('changed')",
        inputs=["data.txt"],
    )
    assert result["verdict"] == "match"
    assert (tmp_path / "data.txt").read_text() == "original"
    assert all(
        r["observations"]["x"]["value"]["v"] == "original"
        for group in result["runs"].values()
        for r in group
    )


def test_timeout_is_evidence_not_a_pass(tmp_path):
    result = execute_case(tmp_path, "import time\ntime.sleep(30)\nx = 1", timeout=1)
    assert result["verdict"] == "inconclusive"
    assert all(
        r["error"]["type"] == "CellTimeoutError" for group in result["runs"].values() for r in group
    )


def test_unsupported_capture_not_silently_equal(tmp_path):
    result = execute_case(tmp_path, "x = object()")
    assert result["verdict"] == "inconclusive"
    assert all(
        "Unsupported" in r["capture_errors"]["x"]
        for group in result["runs"].values()
        for r in group
    )

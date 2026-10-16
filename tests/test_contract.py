import json

import nbformat
import pytest

from floe.runner import input_files, load_contract, source_manifest


def contract(tmp_path, variable="x", **extra):
    data = {
        "schema": 1,
        "observations": [{"name": "x", "cell": "c", "variable": variable}],
        **extra,
    }
    p = tmp_path / "contract.json"
    p.write_text(json.dumps(data))
    return p


def notebook():
    return nbformat.v4.new_notebook(cells=[nbformat.v4.new_code_cell("x = 1", id="c")])


@pytest.mark.parametrize("expression", ["x()", "x[0]", "x.y", '__import__("os")', "class"])
def test_probes_are_variables_not_executable_expressions(tmp_path, expression):
    with pytest.raises(ValueError):
        load_contract(contract(tmp_path, variable=expression), notebook())


def test_cell_id_validation(tmp_path):
    nb = notebook()
    nb.cells[0].id = "other"
    with pytest.raises(ValueError):
        load_contract(contract(tmp_path), nb)


def test_input_boundary_and_hashes(tmp_path):
    (tmp_path / "input.csv").write_text("a\n1\n")
    inputs = input_files(tmp_path, {"inputs": ["input.csv"]})
    assert len(inputs) == 1
    with pytest.raises(ValueError):
        input_files(tmp_path, {"inputs": ["../secret"]})
    (tmp_path / "link").symlink_to(tmp_path / "input.csv")
    with pytest.raises(ValueError):
        input_files(tmp_path, {"inputs": ["link"]})
    a = source_manifest(notebook(), inputs)
    b = source_manifest(notebook(), [(inputs[0][0], b"a\n2\n")])
    assert a["inputs"] != b["inputs"]


def test_unknown_options_and_zero_limits(tmp_path):
    with pytest.raises(ValueError):
        load_contract(contract(tmp_path, timeout=0), notebook())
    with pytest.raises(ValueError):
        load_contract(contract(tmp_path, typo=True), notebook())

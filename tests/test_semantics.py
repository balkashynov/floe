import json
import math
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from floe.capture import CaptureError, Recorder, snapshot
from floe.compare import compare, evaluate_runs, validate_policy
from floe.report import render


def snap(value):
    return snapshot(value)


@pytest.mark.parametrize(
    "a,b",
    [
        (2**60, 2**60 + 1),
        (None, float("nan")),
        (pd.NA, None),
        (True, 1),
        (Decimal("1.1"), 1.1),
        ("1", 1),
    ],
)
def test_distinct_values_are_not_collapsed(a, b):
    assert not compare(snap(a), snap(b))["equal"]


@pytest.mark.parametrize(
    "value",
    [
        float("nan"),
        float("inf"),
        -float("inf"),
        pd.NA,
        pd.NaT,
        Decimal("0.100000000000000001"),
        [1, None],
        {"a": [1, 2]},
    ],
)
def test_json_roundtrip(value):
    encoded = snap(value)
    restored = json.loads(json.dumps(encoded, allow_nan=False))
    assert compare(encoded, restored)["equal"]


def test_explicit_tolerance_and_infinity():
    assert not compare(snap(1.0), snap(1.0001))["equal"]
    assert compare(snap(1.0), snap(1.0001), {"atol": 0.001})["equal"]
    assert not compare(snap(float("inf")), snap(1e100), {"rtol": 1})["equal"]


def test_key_alignment_requires_explicit_policy():
    frame = pd.DataFrame({"id": [1, 2], "value": [4, 5]})
    reordered = frame.iloc[::-1].reset_index(drop=True)
    assert not compare(snap(frame), snap(reordered))["equal"]
    assert compare(snap(frame), snap(reordered), {"keys": ["id"]})["equal"]
    reordered.loc[0, "value"] = 99
    result = compare(snap(frame), snap(reordered), {"keys": ["id"]})
    assert not result["equal"] and result["difference_count"] == 1


@pytest.mark.parametrize("ids", [[1, 1], [1, None], [1, np.nan]])
def test_ambiguous_keys_never_pass_even_when_identical(ids):
    frame = snap(pd.DataFrame({"id": ids, "value": [4, 5]}))
    assert compare(frame, frame, {"keys": ["id"]})["invalid"]


def test_missing_identity_and_duplicate_columns():
    frame = snap(pd.DataFrame([[1, 2]], columns=["id", "id"]))
    assert compare(frame, frame, {"keys": ["id"]})["invalid"]
    frame = snap(pd.DataFrame({"id": [1]}))
    assert compare(frame, frame, {"keys": ["other"]})["invalid"]


def test_category_domain_and_dtype_are_part_of_contract():
    a = pd.DataFrame({"x": pd.Categorical(["a"], categories=["a", "b"])})
    b = pd.DataFrame({"x": pd.Categorical(["a"], categories=["a"])})
    assert not compare(snap(a), snap(b))["equal"]
    assert compare(snap(a), snap(b), {"check_dtype": False})["equal"]


def test_row_loss_not_hidden_by_alignment():
    a = pd.DataFrame({"id": [1, 2], "value": [4, 5]})
    assert not compare(snap(a), snap(a.iloc[:1]), {"keys": ["id"]})["equal"]


def test_index_metadata_matters():
    a = pd.DataFrame({"a": [1, 2]})
    b = a.rename_axis("changed")
    assert not compare(snap(a), snap(b))["equal"]
    assert compare(snap(a), snap(b), {"check_index": False})["equal"]


def test_array_shape_and_dtype_are_checked():
    assert not compare(snap(np.array([1, 2])), snap(np.array([[1, 2]])))["equal"]
    assert not compare(snap(np.array([1], dtype="int32")), snap(np.array([1], dtype="int64")))[
        "equal"
    ]


def test_no_silent_truncation_or_opaque_repr():
    with pytest.raises(CaptureError):
        snapshot(pd.DataFrame({"x": range(10)}), max_values=5)
    with pytest.raises(CaptureError):
        snapshot(object())
    cycle = []
    cycle.append(cycle)
    with pytest.raises(CaptureError):
        snapshot(cycle)


@pytest.mark.parametrize(
    "policy",
    [
        {"atol": -1},
        {"rtol": math.inf},
        {"atol": True},
        {"keys": ["id", "id"]},
        {"check_dtype": "false"},
        {"typo": 1},
    ],
)
def test_invalid_policies_rejected(policy):
    with pytest.raises(ValueError):
        validate_policy(policy)


def result(values, candidate, policy=None):
    def runs(vs):
        return [
            {"observations": {"x": snap(v)}, "environment": {"python": "3.12", "packages": {}}}
            for v in vs
        ]

    contract = {
        "observations": [{"name": "x", "cell": "c", "variable": "x", "policy": policy or {}}]
    }
    return evaluate_runs(runs(values), runs(candidate), contract)


def test_repeat_variation_does_not_indict_runtime():
    assert result([1, 2], [3, 3])["verdict"] == "inconclusive"
    assert result([1, 1], [3, 4])["verdict"] == "inconclusive"
    assert result([1, 1], [2, 2])["verdict"] == "changed"


def test_tolerance_nontransitivity_checked_all_pairs():
    assert result([1.0, 0.94, 1.06], [1.0, 1.0], {"atol": 0.1})["verdict"] == "inconclusive"


def test_cross_comparisons_straddling_boundary_are_inconclusive():
    assert result([0.0, 0.05], [0.10, 0.15], {"atol": 0.11})["verdict"] == "inconclusive"


def test_one_run_cannot_certify_repeatability():
    assert result([1], [1])["verdict"] == "inconclusive"


def test_report_escapes_notebook_content():
    report = result([1, 1], [2, 2])
    report["title"] = "<script>alert(1)</script>"
    assert "<script>" not in render(report)
    assert "&lt;script&gt;" in render(report)


def test_recorder_export(tmp_path):
    recorder = Recorder(source_id="fixture-v1", label="reference")
    recorder.observe("x", 2**60 + 1)
    with pytest.raises(CaptureError):
        recorder.observe("x", 1)
    recorder.write(tmp_path / "capture.json")
    assert json.loads((tmp_path / "capture.json").read_text())["observations"]["x"]["value"][
        "v"
    ] == str(2**60 + 1)

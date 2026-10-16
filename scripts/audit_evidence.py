"""Exact displayed-output baseline and local bounded-capture cost, not a tool benchmark."""

import json
import platform
import statistics
import time
import tracemalloc
from pathlib import Path

import pandas as pd

from floe.capture import snapshot
from floe.compare import compare

root = Path(__file__).resolve().parents[1]
rows = []
for case in json.loads((root / "examples/cases.json").read_text()):
    report = json.loads((root / "evidence" / case["id"] / "report.json").read_text())
    groups = report["runs"]
    outputs = {
        side: [[c["outputs"] for c in run["cells"]] for run in group]
        for side, group in groups.items()
    }
    rows.append(
        {
            "case": case["id"],
            "floe": report["verdict"],
            "execution_only_pass": all(not r["error"] for g in groups.values() for r in g),
            "first_pair_displayed_outputs_equal": outputs["reference"][0]
            == outputs["candidate"][0],
            "displayed_outputs_repeat_stable": all(g[0] == g[1] for g in outputs.values()),
            "environment_delta": report["environment_delta"],
        }
    )
(root / "evidence/baseline.json").write_text(
    json.dumps(
        {
            "method": "Exact original-cell output objects, excluding execution counts; first pair cross comparison plus repeat equality. Includes warnings. No nbval/pytest-notebook benchmark or normalization claim.",
            "cases": rows,
        },
        indent=2,
    )
    + "\n"
)
costs = []
for size in (1000, 10000, 50000):
    frame = pd.DataFrame({"id": range(size), "value": [1.25] * size})
    durations, peaks = [], []
    for _ in range(3):
        tracemalloc.start()
        start = time.perf_counter()
        a = snapshot(frame, max_values=250000)
        result = compare(a, a, {"keys": ["id"]})
        assert result["equal"] and not result["invalid"]
        durations.append(time.perf_counter() - start)
        peaks.append(tracemalloc.get_traced_memory()[1])
        tracemalloc.stop()
    costs.append(
        {
            "rows": size,
            "columns": 2,
            "median_seconds": statistics.median(durations),
            "max_traced_bytes": max(peaks),
            "json_bytes": len(json.dumps(a).encode()),
        }
    )
(root / "evidence/capture-cost.json").write_text(
    json.dumps(
        {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "pandas": pd.__version__,
            "method": "Three repeats of capture plus key-aligned self-comparison; tracemalloc enabled, input creation excluded. Python allocator peak, not RSS. This is a local cost characterization, not a speedup claim.",
            "measurements": costs,
        },
        indent=2,
    )
    + "\n"
)
print(json.dumps({"baseline": rows, "capture_cost": costs}, indent=2))

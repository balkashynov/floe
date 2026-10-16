import json
import sys
import time
from pathlib import Path

from floe.runner import run_matrix

root = Path(__file__).resolve().parents[1]
output = Path(sys.argv[1])
cases = json.loads((root / "examples/cases.json").read_text())
started = time.monotonic()
summary = []
for case in cases:
    result = run_matrix(
        root / f"examples/{case['id']}.ipynb",
        root / f"examples/{case['id']}.json",
        root / ".venv/bin/python",
        root / ".runtimes/pandas3/bin/python",
        output / case["id"],
        repeats=2,
    )
    summary.append(
        {
            **case,
            "actual": result["verdict"],
            "passed": result["verdict"] == case["expected"],
            "seconds": sum(r["seconds"] for group in result["runs"].values() for r in group),
        }
    )
    print(case["id"], result["verdict"], flush=True)
report = {
    "cases": summary,
    "wall_seconds": time.monotonic() - started,
    "execution_count": len(cases) * 4,
    "all_expected": all(x["passed"] for x in summary),
}
(output / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
raise SystemExit(0 if report["all_expected"] else 1)

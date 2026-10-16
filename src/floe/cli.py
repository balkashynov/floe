from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(description="Floe: notebook upgrade evidence")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="Execute a trusted notebook in two Python environments")
    run.add_argument("notebook")
    run.add_argument("--contract", required=True)
    run.add_argument("--reference", required=True, help="Reference Python executable")
    run.add_argument("--candidate", required=True, help="Candidate Python executable")
    run.add_argument("--output", required=True)
    run.add_argument("--repeats", type=int, default=2)
    render = sub.add_parser("report", help="Render a saved report.json without executing code")
    render.add_argument("input")
    render.add_argument("--output", required=True)
    compare = sub.add_parser(
        "compare-captures", help="Compare captures exported from existing kernels"
    )
    compare.add_argument("--reference", nargs="+", required=True)
    compare.add_argument("--candidate", nargs="+", required=True)
    compare.add_argument("--contract", required=True)
    compare.add_argument("--output", required=True)
    reducer = sub.add_parser(
        "reduce", help="Delete cells while preserving one observed upgrade change"
    )
    reducer.add_argument("report_directory")
    reducer.add_argument("--name", required=True)
    reducer.add_argument("--reference", required=True)
    reducer.add_argument("--candidate", required=True)
    reducer.add_argument("--output", required=True)
    reducer.add_argument("--budget", type=int, default=12)
    args = parser.parse_args(argv)
    try:
        if args.command == "reduce":
            from .reduce import reduce_report

            summary = reduce_report(
                args.report_directory,
                args.name,
                args.reference,
                args.candidate,
                args.output,
                args.budget,
            )
            print(json.dumps(summary, indent=2))
            return 0
        elif args.command == "run":
            from .runner import run_matrix

            result = run_matrix(
                args.notebook,
                args.contract,
                args.reference,
                args.candidate,
                args.output,
                args.repeats,
            )
        elif args.command == "report":
            from .report import render as render_html

            result = json.loads(Path(args.input).read_text())
            Path(args.output).write_text(render_html(result))
            return 0
        else:
            from .compare import evaluate_runs
            from .report import render as render_html

            contract = json.loads(Path(args.contract).read_text())
            groups = {
                label: [json.loads(Path(p).read_text()) for p in paths]
                for label, paths in (("reference", args.reference), ("candidate", args.candidate))
            }
            all_runs = groups["reference"] + groups["candidate"]
            if any(r.get("schema") != 1 for r in all_runs):
                raise ValueError("Capture schema must be 1")
            source_ids = {r.get("source_id") for r in all_runs}
            if len(source_ids) != 1 or not next(iter(source_ids)):
                raise ValueError("Captures must share an explicit nonempty source_id")
            result = {
                "schema": 1,
                "title": contract.get("title", "Imported captures"),
                "contract": contract,
                "runs": groups,
                "source_id": next(iter(source_ids)),
                "provenance": "Imported captures: source_id is caller-attested; execution and inputs are not verified",
                **evaluate_runs(groups["reference"], groups["candidate"], contract),
            }
            destination = Path(args.output)
            destination.mkdir(parents=True, exist_ok=False)
            (destination / "report.json").write_text(json.dumps(result, indent=2) + "\n")
            (destination / "report.html").write_text(render_html(result))
        print(f"{result['verdict']}: {args.output}")
        return {"match": 0, "changed": 1, "execution_failure": 1, "inconclusive": 2}[
            result["verdict"]
        ]
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f"floe: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

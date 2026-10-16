"""Typed comparison with explicit tolerances and identity-key alignment."""

from __future__ import annotations

import itertools
import json
import math


def validate_policy(policy):
    if not isinstance(policy, dict):
        raise TypeError("Comparison policy must be a JSON object")
    unknown = set(policy) - {"rtol", "atol", "check_dtype", "check_index", "keys"}
    if unknown:
        raise ValueError(f"Unknown policy options: {sorted(unknown)}")
    for key in ("rtol", "atol"):
        value = policy.get(key, 0)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < 0
        ):
            raise ValueError(f"{key} must be a finite nonnegative number")
    for key in ("check_dtype", "check_index"):
        if key in policy and not isinstance(policy[key], bool):
            raise ValueError(f"{key} must be boolean")
    keys = policy.get("keys", [])
    if (
        not isinstance(keys, list)
        or not all(isinstance(k, str) for k in keys)
        or len(set(keys)) != len(keys)
    ):
        raise ValueError("keys must be distinct column-name strings")


def compare(left, right, policy=None, max_diffs=12):
    policy = policy or {}
    validate_policy(policy)
    differences = []
    count = 0

    def add(path, reason, a, b):
        nonlocal count
        count += 1
        if len(differences) < max_diffs:
            differences.append({"path": path, "reason": reason, "reference": a, "candidate": b})

    def walk(a, b, path):
        if a == b:
            return
        if isinstance(a, dict) and isinstance(b, dict):
            if a.get("t") == b.get("t") == "float":
                x, y = float(a["v"]), float(b["v"])
                if math.isnan(x) and math.isnan(y):
                    return
                if math.isclose(x, y, rel_tol=policy.get("rtol", 0), abs_tol=policy.get("atol", 0)):
                    return
                add(path, "numeric value changed", a, b)
                return
            for key in sorted(a.keys() | b.keys()):
                if key not in a or key not in b:
                    add(f"{path}/{key}", "field missing", a.get(key), b.get(key))
                else:
                    walk(a[key], b[key], f"{path}/{key}")
        elif isinstance(a, list) and isinstance(b, list):
            if len(a) != len(b):
                add(path + "/length", "length changed", len(a), len(b))
            for i, (x, y) in enumerate(zip(a, b)):
                walk(x, y, f"{path}/{i}")
        else:
            add(path, "value or type changed", a, b)

    if left.get("kind") != right.get("kind"):
        add("/kind", "observation type changed", left.get("kind"), right.get("kind"))
    elif left.get("kind") in ("DataFrame", "Series"):
        walk(left["columns"], right["columns"], "/columns")
        if policy.get("check_dtype", True):
            walk(left["dtypes"], right["dtypes"], "/dtypes")
        keys = policy.get("keys", [])
        if keys:

            def keyed(frame):
                labels = frame["columns"]
                positions = []
                for key in keys:
                    encoded = {"t": "str", "v": key}
                    if labels.count(encoded) != 1:
                        raise ValueError(f"Identity column {key!r} must appear exactly once")
                    positions.append(labels.index(encoded))
                rows = {}
                for i, row in enumerate(frame["rows"]):
                    atoms = [row[j] for j in positions]
                    if any(
                        x.get("t") in ("null", "NAType", "NaTType")
                        or (x.get("t") == "float" and x.get("v") == "nan")
                        for x in atoms
                    ):
                        raise ValueError("Identity keys cannot contain missing values")
                    key = json.dumps(atoms, sort_keys=True, separators=(",", ":"))
                    if key in rows:
                        raise ValueError("Duplicate identity key; refusing an ambiguous alignment")
                    rows[key] = (row, frame["index"][i])
                return rows

            try:
                a, b = keyed(left), keyed(right)
            except ValueError as exc:
                return {
                    "equal": False,
                    "invalid": str(exc),
                    "differences": [],
                    "difference_count": 0,
                }
            for key in sorted(a.keys() | b.keys()):
                if key not in a or key not in b:
                    add("/rows/" + key, "identity row missing", a.get(key), b.get(key))
                else:
                    walk(a[key][0], b[key][0], "/rows/" + key)
                    if policy.get("check_index", False):
                        walk(a[key][1], b[key][1], "/index/" + key)
        else:
            walk(left["rows"], right["rows"], "/rows")
        if policy.get("check_index", not bool(keys)):
            walk(left["index_names"], right["index_names"], "/index_names")
            if policy.get("check_dtype", True):
                walk(left["index_dtypes"], right["index_dtypes"], "/index_dtypes")
            if not keys:
                walk(left["index"], right["index"], "/index")
    elif left.get("kind") == "ndarray":
        walk(left["shape"], right["shape"], "/shape")
        if policy.get("check_dtype", True):
            walk(left["dtype"], right["dtype"], "/dtype")
        walk(left["values"], right["values"], "/values")
    else:
        walk(left, right, "")
    return {
        "equal": count == 0,
        "invalid": None,
        "differences": differences,
        "difference_count": count,
    }


def evaluate_runs(reference, candidate, contract):
    """All pairwise repeat checks precede cross-runtime comparison.

    Approximate equality is not transitive. Comparing only to the first repeat
    would miss a pair straddling the tolerance window, so test all pairs.
    """
    environment_errors = []
    for label, group in (("reference", reference), ("candidate", candidate)):
        environments = [r.get("environment") for r in group]
        if any(
            not e or not e.get("python") or not isinstance(e.get("packages"), dict)
            for e in environments
        ):
            environment_errors.append(f"{label}: environment metadata is missing")
        elif any(e != environments[0] for e in environments[1:]):
            environment_errors.append(f"{label}: environment changed between repeats")
    findings = []
    for watch in contract["observations"]:
        name, policy = watch["name"], watch.get("policy", {})
        values = [
            [run.get("observations", {}).get(name) for run in group]
            for group in (reference, candidate)
        ]
        finding = {
            "name": name,
            "cell": watch["cell"],
            "variable": watch["variable"],
            "policy": policy,
            "reference": values[0][0] if values[0] else None,
            "candidate": values[1][0] if values[1] else None,
        }
        if environment_errors:
            finding.update(status="inconclusive", reason="; ".join(environment_errors))
        elif any(len(v) < 2 for v in values):
            finding.update(
                status="inconclusive",
                reason="At least two independent runs per runtime are required",
            )
        elif any(v is None for group in values for v in group):
            missing = []
            for label, group in zip(("reference", "candidate"), (reference, candidate)):
                for i, run in enumerate(group):
                    if name not in run.get("observations", {}):
                        missing.append(
                            {
                                "runtime": label,
                                "repeat": i + 1,
                                "reason": run.get("error")
                                or run.get("capture_errors", {}).get(name)
                                or "Observation missing",
                            }
                        )
            finding.update(status="inconclusive", reason="Observation unavailable", missing=missing)
        else:
            checks = [
                (label, compare(a, b, policy))
                for label, group in zip(("reference", "candidate"), values)
                for a, b in itertools.combinations(group, 2)
            ]
            invalid = next((c["invalid"] for _, c in checks if c["invalid"]), None)
            unstable = sorted({label for label, c in checks if not c["equal"]})
            if invalid:
                finding.update(status="inconclusive", reason=invalid)
            elif unstable:
                finding.update(
                    status="inconclusive", reason="Repeat variation in " + " and ".join(unstable)
                )
            else:
                cross = [compare(a, b, policy) for a in values[0] for b in values[1]]
                invalid = next((c["invalid"] for c in cross if c["invalid"]), None)
                changed = [c for c in cross if not c["equal"]]
                if invalid:
                    finding.update(status="inconclusive", reason=invalid)
                elif changed and len(changed) != len(cross):
                    finding.update(
                        status="inconclusive",
                        reason="Cross-runtime comparisons disagree at the policy boundary",
                    )
                elif changed:
                    finding.update(
                        status="changed",
                        reason="Stable observations violate the comparison policy",
                        **changed[0],
                    )
                else:
                    finding.update(
                        status="match",
                        reason="All repeat and cross-runtime comparisons satisfy the policy",
                    )
        findings.append(finding)
    errors = {
        label: [r.get("error") for r in group if r.get("error")]
        for label, group in (("reference", reference), ("candidate", candidate))
    }
    if environment_errors or errors["reference"]:
        verdict = "inconclusive"
    elif errors["candidate"]:
        verdict = "execution_failure"
    elif any(f["status"] == "changed" for f in findings):
        verdict = "changed"
    elif not findings or any(f["status"] == "inconclusive" for f in findings):
        verdict = "inconclusive"
    else:
        verdict = "match"
    return {
        "verdict": verdict,
        "findings": findings,
        "execution_errors": errors,
        "environment_errors": environment_errors,
        "scope": "Observed values only. A match is not proof of notebook equivalence.",
    }

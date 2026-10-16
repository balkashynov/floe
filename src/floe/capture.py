"""Dependency-free capture, also usable inside an existing notebook kernel.

Only already-materialized pandas/NumPy objects are supported. Never collects a
Snowpark dataframe or executes SQL implicitly. Unsupported/oversize values fail.
"""

from __future__ import annotations

import datetime
import decimal
import importlib.metadata
import json
import platform
import sys


class CaptureError(ValueError):
    pass


class Encoder:
    def __init__(self, limit=100_000):
        self.remaining = limit
        self.active = set()

    def atom(self, value):
        self.remaining -= 1
        if self.remaining < 0:
            raise CaptureError("Observation exceeds max_values; select a bounded result explicitly")
        if value is None:
            return {"t": "null"}
        module, name = type(value).__module__, type(value).__name__
        if module.startswith("pandas") and name in ("NAType", "NaTType"):
            return {"t": name}
        if isinstance(value, bool):
            return {"t": "bool", "v": value}
        if isinstance(value, int):
            return {"t": "int", "v": str(value)}
        if isinstance(value, float):
            return {"t": "float", "v": repr(value)}
        if isinstance(value, str):
            return {"t": "str", "v": value}
        if isinstance(value, decimal.Decimal):
            return {"t": "decimal", "v": str(value)}
        if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
            return {"t": name, "v": value.isoformat()}
        if isinstance(value, datetime.timedelta):
            return {"t": name, "v": str(value)}
        if module.startswith("numpy") and hasattr(value, "item"):
            if name.startswith(("datetime64", "timedelta64")):
                return {"t": name, "dtype": str(value.dtype), "v": str(value)}
            return self.atom(value.item())
        if isinstance(value, (list, tuple, dict)):
            oid = id(value)
            if oid in self.active:
                raise CaptureError("Cyclic values are not supported")
            self.active.add(oid)
            try:
                if isinstance(value, dict):
                    if not all(isinstance(k, str) for k in value):
                        raise CaptureError("Mapping keys must be strings")
                    return {"t": "dict", "v": {k: self.atom(value[k]) for k in sorted(value)}}
                return {
                    "t": "tuple" if isinstance(value, tuple) else "list",
                    "v": [self.atom(x) for x in value],
                }
            finally:
                self.active.remove(oid)
        raise CaptureError(f"Unsupported value type: {module}.{name}")

    def dtype(self, value):
        result = {"name": str(value)}
        if hasattr(value, "categories"):
            result.update(
                categories=[self.atom(x) for x in value.categories], ordered=bool(value.ordered)
            )
        return result

    def snapshot(self, value):
        module, name = type(value).__module__, type(value).__name__
        if module.startswith("pandas") and name in ("DataFrame", "Series"):
            frame = value.to_frame() if name == "Series" else value
            if frame.size + len(frame.index) + len(frame.columns) > self.remaining:
                raise CaptureError("Observation exceeds max_values; no sample was compared")
            index = frame.index
            index_dtypes = (
                [self.dtype(level.dtype) for level in index.levels]
                if hasattr(index, "levels")
                else [self.dtype(index.dtype)]
            )
            return {
                "kind": name,
                "columns": [self.atom(c) for c in frame.columns],
                "dtypes": [self.dtype(d) for d in frame.dtypes],
                "index_names": [self.atom(n) for n in index.names],
                "index_dtypes": index_dtypes,
                "index": [self.atom(i) for i in index],
                "rows": [
                    [self.atom(x) for x in row] for row in frame.itertuples(index=False, name=None)
                ],
            }
        if module.startswith("numpy") and name == "ndarray":
            if value.size > self.remaining:
                raise CaptureError("Array exceeds max_values; no sample was compared")
            return {
                "kind": "ndarray",
                "shape": list(value.shape),
                "dtype": str(value.dtype),
                "values": [self.atom(x) for x in value.flat],
            }
        return {"kind": "value", "value": self.atom(value)}


def snapshot(value, max_values=100_000):
    return Encoder(max_values).snapshot(value)


def environment():
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "implementation": sys.implementation.name,
        "packages": dict(
            sorted(
                (d.metadata["Name"].lower(), d.version)
                for d in importlib.metadata.distributions()
                if d.metadata.get("Name")
            )
        ),
    }


class Recorder:
    """Capture explicit local variables in an existing kernel, without executing code."""

    def __init__(self, *, source_id, label, max_values=100_000):
        self.data = {
            "schema": 1,
            "source_id": source_id,
            "label": label,
            "environment": environment(),
            "observations": {},
        }
        self.max_values = max_values

    def observe(self, name, value):
        if name in self.data["observations"]:
            raise CaptureError(f"Duplicate observation: {name}")
        self.data["observations"][name] = snapshot(value, self.max_values)

    def write(self, path):
        from pathlib import Path

        Path(path).write_text(json.dumps(self.data, indent=2, allow_nan=False) + "\n")

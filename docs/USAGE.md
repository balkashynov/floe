# Floe usage guide

**Your notebook ran. Did the answer change?**

Floe compares explicit notebook observations across two Python environments. It reruns each environment in fresh kernels, checks repeatability, compares typed values under a declared policy, and produces inspectable JSON and HTML evidence. A bounded reducer can turn a large example into a smaller notebook preserving the same observed change.

The motivating example runs successfully in pandas 2.3.3 and 3.0.0. Mutating a selected Series changes its parent table in the reference, but not the candidate: the observed price changes from **99 to 10**. Floe captures that table even when the notebook does not display it.

This is an independent project by Ivan Balkashynov. No Snowflake affiliation or endorsement is implied. The browser presentation replays saved local executions; it does not execute a backend notebook.

## Try the complete example

Requires Python 3.12 for the pinned examples, and `uv` (or equivalent virtual environments). macOS ARM64 was exercised. Python >=3.11 is the package's declared range, not a claim of multi-platform certification. The candidate environment needs pandas 3.0-compatible Python.

From the extracted source directory:

```sh
uv venv --python 3.12 .venv
uv pip sync --python .venv/bin/python examples/reference-requirements.txt
uv venv --python 3.12 .runtimes/pandas3
uv pip sync --python .runtimes/pandas3/bin/python examples/candidate-requirements.txt
uv pip install --python .venv/bin/python --no-deps .

.venv/bin/floe run examples/copy-on-write.ipynb \
  --contract examples/copy-on-write.json \
  --reference .venv/bin/python \
  --candidate .runtimes/pandas3/bin/python \
  --output comparison
```

A `changed` result exits **1** intentionally. Open `comparison/report.html` and inspect `comparison/report.json`. Run `copy-fixed.ipynb` with `copy-fixed.json` into a **new** directory to see the repaired assignment pass. Existing output directories are refused to protect previous evidence. Windows users must adapt executable paths; Windows execution has not been validated.

To use your own existing environments, install this package in the driver (`python -m pip install .`). Each target needs `ipykernel` and the notebook's dependencies. Floe injects its standalone capture module; target environments do not need Floe installed.

## Declare the intended result

Choose stable notebook cell IDs and existing local variables:

```json
{
  "schema": 1,
  "inputs": ["orders.csv"],
  "timeout": 60,
  "max_values": 100000,
  "observations": [{
    "name": "orders",
    "cell": "calculate",
    "variable": "orders",
    "policy": {"keys": ["id"], "rtol": 0.000001}
  }]
}
```

An observation runs immediately after its named code cell. Variables only: arbitrary expressions and function calls are not accepted. Omit `inputs` for self-contained notebooks. Declare relative regular files next to the notebook; each run receives disposable copies. Native SQL cells, extensions and remote data are not automatically reproduced.

Supported values include Python scalars/containers, Decimal and datetime, NumPy arrays, and already-materialized pandas Series/DataFrames. Floe preserves integer precision, null distinctions, category domains, dtype and index metadata. It refuses opaque objects, cyclic containers and values exceeding the explicit bound. It never silently samples a larger table or collects a Snowpark dataframe.

Comparison is strict by default. `atol` and `rtol` apply to floating values, not Decimal or integer types. `check_dtype: false` explicitly accepts schema differences. `keys` aligns unique nonmissing table identities; with keys, index comparison defaults off. Without keys, row order and index metadata matter. `check_index` overrides that default. These policies encode the user's decision, not a claim that one result is correct.

## Read a verdict

| Verdict | Meaning | Exit |
| --- | --- | --- |
| `match` | All captured repeat/cross pairs satisfy the policy | 0 |
| `changed` | A repeat-stable observation violates the policy across environments | 1 |
| `execution_failure` | Reference completes; candidate execution fails | 1 |
| `inconclusive` | Repeat variation, missing evidence, broken reference, environment drift or ambiguous identity | 2 |

An overall `changed` report may also contain inconclusive observations. Inspect every finding. A match covers selected observations only; it does not prove whole-notebook equivalence, determinism or correctness. Two repeats provide evidence, not a statistical guarantee. When both environment metadata and execution fail, the result remains inconclusive.

## Reduce a stable change

```sh
.venv/bin/floe reduce comparison --name prices \
  --reference .venv/bin/python --candidate .runtimes/pandas3/bin/python \
  --output reduced --budget 12
```

The reducer validates saved source/input hashes, re-establishes the witness, then tries deleting code cells. Every trial runs four kernels. Both sides of the selected observation must remain exactly the same, with no execution errors. A different exception or different changed value is rejected. `reduction.json` distinguishes a budget-limited result from one-cell-deletion minimality under this oracle. It does not claim global minimality or preservation of other side effects.

## Existing or hosted kernels

Use the dependency-free `Recorder` to export selected materialized values and compare captures locally. See [SNOWFLAKE.md](../SNOWFLAKE.md) for the complete path and the unvalidated hosted boundary. Source/data identity is caller-attested in imported captures.

## Inspect and reproduce

- [Validation and limitations](../VALIDATION.md), including all 12 designed cases and an exact-output baseline.
- [Engineering decisions](../ENGINEERING.md), including nontransitive tolerance and reduction semantics.
- `evidence/`: original notebooks, contracts, executed notebooks, per-run metadata, all reports and reduction trials.
- `PYTHONPATH=src .venv/bin/python -m pytest -q`: semantic, provenance and real-kernel error/timeout tests.
- `PYTHONPATH=src .venv/bin/python scripts/validate_matrix.py fresh-evidence`: 48 real kernel executions.
- `python -m http.server 8741 --directory site/dist`: browser evidence explorer after `PYTHONPATH=src .venv/bin/python scripts/package_release.py`.

The pinned fixtures are original examples of documented pandas migration behavior, not newly discovered pandas bugs or a customer benchmark. Existing [nbval](https://nbval.readthedocs.io/en/latest/) and [pytest-notebook](https://pytest-notebook.readthedocs.io/en/latest/) are strong choices for displayed-output regression testing. Explicit assertions can be simpler for a known invariant. Floe combines typed in-memory observations, repeat checks, policy and reduction in one reviewable workflow.

## Execution and data boundary

Run trusted notebooks only. A fresh kernel and temporary working directory are **not a security sandbox**: code retains the host user's filesystem and network permissions. Only a small environment-variable allowlist is forwarded, but code can still read accessible files or use network data. Kernel startup has nbclient's separate startup deadline; the configured timeout is per cell, not a whole-run wall-time budget. Captures may contain sensitive observed values. Review artifacts before sharing them. The default value limit is an element budget, not a byte or RSS limit.

MIT licensed. This package has not been published to a registry.

# Snowflake integration boundary

Floe's intended user is an engineer reviewing a notebook runtime/dependency upgrade. Snowflake already provides [runtime pinning and package management](https://docs.snowflake.com/en/user-guide/ui-snowsight/notebooks-in-workspaces/notebooks-in-workspaces-packages-runtime), [custom runtime images](https://docs.snowflake.com/en/developer-guide/snowflake-ml/custom-runtime-images) and [headless notebook execution](https://docs.snowflake.com/en/sql-reference/sql/execute-notebook-project). Floe proposes a result-inspection layer after execution, not a replacement for these capabilities.

**Validated here:** local Python 3.12 kernels, pandas 2.3.3 versus 3.0.0, declared file inputs, standalone Recorder export and local comparison.

**Not validated here:** Snowflake account connectivity, Workspaces runtime images, native SQL cells, Snowpark distributed execution, warehouse behavior, permissions or headless job orchestration. No Snowflake service credentials were used. The examples are not an emulator of Snowflake.

## Lowest-friction evaluation path

Copy `src/floe/capture.py` into an accessible file in an existing Python notebook environment. The module itself uses only the standard library; it inspects pandas/NumPy values already present. A local test validates this export/import format. Hosted upload/package policy is a separate integration step requiring the team's own environment.

Run the same notebook and pinned data snapshot independently at least twice in each actual runtime. Capture an explicitly materialized, bounded result:

```python
from capture import Recorder

recorder = Recorder(
    source_id="notebook-sha256:data-snapshot-id:contract-v1",
    label="reference-1",
)
# `prices` must already be a local pandas object or supported value.
recorder.observe("prices", prices)
recorder.write("reference-1.json")
```

The label is descriptive. Supply files to the correct side of the CLI yourself. Never reuse one file as two independent executions. A shared nonempty source ID is required, but the ID and independent execution are **caller-attested** for imported captures. Include code, data snapshot and contract identity in that ID; Floe cannot verify hosted inputs.

Export reference-1, reference-2, candidate-1 and candidate-2 JSON files using the environment's approved artifact path. Then, locally:

```sh
floe compare-captures \
  --reference reference-1.json reference-2.json \
  --candidate candidate-1.json candidate-2.json \
  --contract examples/copy-on-write.json --output hosted-comparison
```

Open `hosted-comparison/report.html`. A match refers only to the observed values under the contract. No SQL is executed by Floe, and no Snowpark dataframe is collected implicitly. If a result is too large, the caller must choose a meaningful bounded aggregation explicitly. Results observed from mutable remote tables cannot establish an upgrade difference without a fixed snapshot.

The automatic reducer currently needs executable standard Python notebooks and two local Python environments. Imported hosted captures alone cannot drive reduction. A future hosted executor adapter would require authenticated execution, immutable dataset references, separate artifact storage, reproducible native SQL semantics and actual end-to-end service validation. Those are proposed follow-on work, not implemented features.

A useful first feedback question for a runtime owner: would a repeat-checked typed comparison of selected notebook results be useful during runtime qualification, or is that already covered by internal test contracts?

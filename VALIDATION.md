# Validation record

2026-10-15. Python 3.12.11, macOS 27.0.1 ARM64, pandas 2.3.3 versus 3.0.0, NumPy 2.3.5. Full environment manifests are included in every `run.json`. Across the final matrix the only recorded package-version delta is pandas. Dependency lists are frozen in `examples/reference-requirements.txt` and `examples/candidate-requirements.txt`.

## Core and real-kernel checks

**53 tests passed in 11.36 seconds.** The suite exercises typed JSON roundtrips, large integers, null distinctions, explicit floating tolerance, category and index metadata, strict schema and row identity, missing/duplicate keys, nontransitive tolerance, cross-pair boundary disagreement, repeat variation, environment drift, manifest integrity, changed-witness rejection, import/export and HTML escaping. Real-kernel tests check fresh disposable input copies, a one-second timeout for a 30-second sleeping cell, and unsupported captures returning inconclusive.

The first timeout test failed and exposed a synchronous kernel-manager problem. The corrected async manager was tested by the same real sleeping-cell check before the final suite and evidence matrix. Startup failures observed inside a restricted sandbox were retained as failures, never counted as successful executions.

**12/12 designed cases matched their expected verdicts, across 48 kernel executions, in 32.978 seconds.** Each case used two independent kernels per environment. These are original controlled fixtures, not a randomly sampled corpus or an estimate of customer failure rates.

| Case | Expected and observed | Why it exists |
| --- | --- | --- |
| category-loss | changed | Unobserved categorical group disappears |
| category-fixed | match | Explicit observed=False preserves the result |
| copy-on-write | changed | Selected Series mutation no longer changes parent |
| copy-fixed | match | Direct parent assignment preserves the result |
| string-schema | changed | Unprinted inferred dtype changes object to str |
| string-policy | match | Explicit dtype policy accepts that change |
| removed-alias | execution_failure | Removed M frequency alias |
| stable-numeric | match | Unchanged numerical control |
| unstable | inconclusive | Random value varies within each runtime |
| row-order | match | Explicit unique keys align reordered rows |
| duplicate-keys | inconclusive | Ambiguous identity refused |
| baseline-error | inconclusive | Reference already fails |

Inspect [summary.json](evidence/summary.json) and each case's full report, source, contract and executed notebooks. The pandas behaviors are documented in the [3.0 release notes](https://pandas.pydata.org/docs/whatsnew/v3.0.0.html) and [string migration guide](https://pandas.pydata.org/docs/user_guide/migration-3-strings.html).

## Baselines and interpretation

The [baseline audit](evidence/baseline.json) independently compares saved original-cell output objects and checks execution success. It includes warnings and checks output repeatability; it is **not a benchmark of nbval or pytest-notebook** and does not apply their normalization features.

Execution-only checks pass all three semantic-change cases. Exact displayed-output comparison sees the categorical warning difference, but the Copy-on-Write and string-schema cases have identical displayed output while typed observations change. Warnings contain per-run details, so raw output equality itself varies in the categorical and removed-alias fixtures. A tool with normalization could suppress that noise. Printing the selected values or adding assertions would make those values testable with existing tools; Floe's contribution is the combined explicit policy, repeat evidence and reduction workflow.

The unprinted random-value fixture also has identical displayed output. Floe correctly reports its observation inconclusive instead of assigning a stable upgrade regression. No output-only baseline is claimed to certify semantics it never observes.

## Reduction

The [recorded reducer run](evidence/reduction/reduction.json) started from five code cells, performed eight trials with four fresh kernels each, and kept two code cells. The exact original reference and candidate snapshots were preserved. The final result is one-cell-deletion minimal under the selected observation oracle. This excludes global minimality and preservation of unobserved side effects. All 32 trial executions are included; the separate source case adds four executions. Attempts producing missing-variable failures were rejected.

## Bounded capture costs

Three repeats of capture plus explicit key-aligned self-comparison, with tracemalloc enabled and input construction excluded:

| Rows × columns | Median elapsed | Peak traced Python allocation | Snapshot JSON |
| --- | ---: | ---: | ---: |
| 1,000 × 2 | 0.033 s | 1.12 MB | 0.083 MB |
| 10,000 × 2 | 0.357 s | 11.38 MB | 0.848 MB |
| 50,000 × 2 | 1.944 s | 58.44 MB | 4.328 MB |

These are one-machine cost measurements, not speedups. Traced Python allocation is not process RSS. The capture value bound was explicitly raised to 250,000. Reports include multiple snapshots and can be much larger than one snapshot. The browser import limit is 5 MB; use CLI reports for larger artifacts. The tool is intended for selected bounded results. [Full measurements](evidence/capture-cost.json).

## Packaging and presentation

The wheel was built and installed into a clean virtual environment. Its `floe` entry point was exercised through a complete repaired-notebook comparison using the two target environments. Static presentation replays the real reports and provides the full source/evidence download. Desktop and 390-pixel phone layouts were inspected in the real browser. All twelve case controls returned the expected verdict; a real imported report rendered correctly, and a malformed table was rejected while preserving the prior view. Static evidence/download links were checked. The source archive was extracted, all included content hashes matched, and its 50 non-kernel tests passed. Contact research, environments and hosting credentials are excluded from the bundle.

## Material limits

No hosted Snowflake runtime, native SQL cell, Snowpark distributed execution or external customer notebook was exercised. The original frozen evidence is from macOS; the public release also passed Ubuntu CI as recorded below. Windows remains unvalidated. Python versions other than 3.12 were not tested in this build. Runtime package pins reproduce the Python dependency set, not the OS/native-library environment. Two repeats cannot prove determinism; observation policies can intentionally hide changes. Imported provenance is caller-attested. Fresh kernels are not a security sandbox. There is no confirmed Snowflake adoption interest.

## Public release preparation

The public release replaces the absolute developer environment prefix in five recorded error artifacts with `<candidate-runtime>`. Notebook sources, inputs, observed values, verdicts and timings are unchanged. The exact-output baseline flags were checked again after this path redaction and remain identical. Private originals are retained outside the public package. The source archive now includes the presentation source, usage guide and CI workflow; regenerate it with `python scripts/package_release.py`.

## Hosted publication check

[GitHub Actions run 38845165824](https://github.com/balkashynov/floe/actions/runs/38845165824) verified source commit `24fdee31ca1cdb8ca027d4f01e6fdb463aaa02a2` on Ubuntu with Python 3.12: all 53 tests passed, and all 12 designed cases matched their expected verdicts across 48 fresh-kernel executions. The source/demo packaging and GitHub Pages deployment also passed. This is additional Linux execution evidence, not live Snowflake validation. The browser continues to display the original recorded macOS runs; CI does not replace those artifacts.

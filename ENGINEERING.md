# Engineering notes

Floe starts with a small contract: a trusted `.ipynb`, declared relative input files, two Python executables, stable cell IDs, observed variables and comparison policies. It deliberately uses existing environment managers and Jupyter execution rather than recreating them.

## Execution and provenance

The driver uses nbformat/nbclient with **AsyncKernelManager**, executing one original cell at a time. A separate capture module is injected into each fresh kernel; observations emit a private MIME payload after the named cell. The saved executed notebook contains original cells and outputs, not bootstrap code or connection files. Each repeat gets a temporary working directory and its own copies of declared inputs. Interleaving reference/candidate runs reduces a systematic ordering effect but does not control the host scheduler or external services.

The artifact includes SHA-256 of source cells/metadata, declared input bytes and the observation contract; package versions and Python/platform are captured inside each kernel. The same side must retain identical environment metadata across repeats. Different interpreter builds, settings, native libraries or remote state can still matter without appearing in the package list. Artifacts are evidence, not cryptographically signed attestations; imported files are not authenticated.

The timeout integration test exposed a synchronous-manager mistake: synchronous kernel polling prevented the async timeout from taking effect. The corrected async manager interrupts/stops timed-out kernels and persists a `CellTimeoutError`. This is why a real sleeping-cell test accompanies semantic unit tests.

## Typed observation policy

Values use a JSON-safe typed encoding. Integers are decimal strings to avoid JavaScript precision loss. NaN, null, pandas NA/NaT, bool, strings, Decimal and time values remain distinct. Tables carry column names, dtypes/category domains, row values and index metadata. No repr comparison or automatic sampling is used.

Each within-runtime pair is checked before any cross-runtime claim. Approximate equality is not transitive: values 0.94, 1.00 and 1.06 with absolute tolerance 0.1 cannot all be declared stable merely by comparing to the middle value. Floe checks every pair. Cross-runtime comparisons must agree as well; a tolerance-boundary disagreement is inconclusive.

Identity-key comparison is explicit. Keys must exist once, be unique and nonmissing. Duplicate keys are inconclusive even when both inputs are identical. Structural rows/columns remain checked; alignment does not hide missing rows. Numeric tolerance applies only to floating atoms, with `math.isclose`'s symmetric scaling. Other types remain strict. Differences are counted in full, with at most 12 detailed paths in each finding.

For n bounded values and r repeats, capture is O(n); each table identity comparison builds O(n) lookup state, then sorts keys in O(n log n). Pair checks are O(r²). Captures and reports keep full bounded values, so artifact size and memory grow with n and r. This is a pre-upgrade inspection tool for selected results, not a streaming billion-row comparator. See `evidence/capture-cost.json` for actual local costs with the measurement method.

## Witness-preserving reduction

The reducer verifies the report's source/input/contract manifest, then repeats the original example under the supplied environments. It greedily tries removing one non-observation code cell at a time. A trial is accepted only if both selected snapshots exactly match their original sides and all executions succeed. Using exact preservation for this oracle prevents a different change from being accepted just because it also violates a loose tolerance.

Deletion restarts after every accepted edit. If a complete sweep cannot delete a remaining eligible cell, the result is one-cell-deletion minimal **under this particular witness**. Reaching the trial budget yields a smaller reproducer without a minimality claim. The process is not a dependency analyzer, does not minimize source lines and does not preserve unobserved effects. Every attempted notebook, run and result is retained.

## Fair alternatives

[nbval](https://nbval.readthedocs.io/en/latest/) and [pytest-notebook](https://pytest-notebook.readthedocs.io/en/latest/user_guide/tutorial_config.html) already offer notebook regression testing and normalization. Printing an important value or asserting its invariants may be all a team needs. [nbdime](https://nbdime.readthedocs.io/) provides notebook-aware diffs; [Papermill](https://papermill.readthedocs.io/) handles parameterized execution. Floe does not claim these tools cannot be extended to implement its workflow, nor that notebook regression testing is new.

The proposed adoption path is one selected notebook in a runtime-upgrade review. Keep the existing executor/editor/environment manager. Add typed observations for results whose semantics matter, review the evidence, and decide whether to accept a changed policy or fix the notebook. Whether a Snowflake team wants this layer remains unconfirmed.

## Presentation

The static browser viewer is a replay of checked-in JSON reports. It never claims to execute Python. Import reads a local report in browser memory; it is display-only, and values are rendered with textContent. The CLI HTML renderer escapes user content. Contact research and drafts are excluded from the source release and Site assets.

# Independent Phase 0 claims review

This review covers `docs/reference-contract.md`, the reference build and instrumentation records, benchmark and differential scripts/reports, raw failed bootstrap outputs, the synthetic profile, and PHLASH deliverables. Initial review took place while the parent author corrected the benchmark gates. Final review also inspected `docs/phase-0-decision.md`, `README.md`, and the regenerated reports. Historical findings and their final dispositions are distinguished below; generated reports remain authoritative for executed checks.

## Overall assessment

The work establishes a pinned C reference, a substantial source contract, reproducible bootstrap materialization, instrumentation checks, a synthetic profiling path, and CPU/custom-GPU PHLASH feasibility. It does not establish a new inference engine, a successful full 30-round bootstrap workload, scientific accuracy, or an acceleration. The reference contract correctly separates strict, equivalent, and research modes and acknowledges that the user did not demand byte-identical output.

The recommendation to retain vanilla C as the oracle and consider numerically equivalent legacy acceleration remains technically reasonable. It should be described as a provisional development direction. Without real-workload inputs and the user's scientific output requirements, these results do not establish that writing a new engine is preferable to using or repairing an existing method. The user's already-parallel bootstraps make ordinary process parallelism an inadequate basis for the target speedup.

## Material findings

### 1. Full-trajectory acceptance remains unresolved

An independent scan of all preserved K=23, N=30 outputs confirmed the same three nonfinite replicates in each of eight complete batches:

| Replicate ID | First affected round | First affected record | Nonfinite records per output |
|---:|---:|---|---:|
| 16 | 28 | QD | 53 |
| 26 | 26 | LK | 79 |
| 28 | 23 | RI | 8 |

The ninth batch was interrupted: eight output files existed, and replicate 07 contained only two optimizer/iteration records. The expected round-zero RI exception was excluded from this scan. All eight complete batches had 30 optimizer records per fit, demonstrating that exit status and iteration count alone do not certify a valid finite trajectory.

The failure record is `bench/failed-23state.json`, with raw evidence under `bench/raw/failed-23state`. These are failures on small random synthetic inputs; they are not evidence that the user's genome failed or that all legacy PSMC inference is unstable. Conversely, identical NaNs across worker counts establish reproducibility of the pathology, not successful inference.

The rejected exploratory K=4, N=30 run is recorded separately in `bench/exploratory-4state.json`, with nonfinite output in 28 of 30 replicates. The final smoke retains K=23 and uses five rounds only. `bench/baseline.json` explicitly reports `partial_trajectory_smoke_passed_full_gate_failed`: its 270 measured fits completed five rounds, passed the finite-output check, and retained per-replicate output identity across concurrency settings. Batch medians were 2.023788, 1.043177, and 0.550352 seconds at one, two, and four workers. This validates harness mechanics and early trajectories. Reducing rounds does not repair the N=30 failures or pass the full-trajectory gate, and its runtime is not evidence for the target acceleration.

### 2. The benchmark must fail closed

At initial review, `bench/run.py` labeled a batch passed using byte hashes, exit codes, and 30 IT records, without checking finiteness. Final source review confirms that measured batches and single fits now check finiteness, successful exit, and iteration counts derived from the selected configuration. A failed batch records evidence and stops. The final report's scope and status preserve the unresolved full-trajectory failure; obsolete four-state success wording was removed.

Failed and interrupted K=23/N=30 outputs remain separately retained and excluded from successful timing summaries. The timeout-polling measurements are explicitly superseded; the final measurements use blocking process completion with a separate watchdog. This corrects timing overhead, not PSMC inference. These safeguards must remain in place for future workloads.

### 3. Differential checks have a narrow but useful meaning

The initially inspected report recorded 51 checks passing; the regenerated final report records 52 passing and zero failed harness checks. They establish instrumented-C versus vanilla-C output parity, ordered bootstrap replay, and tiny independent inference checks using C-generated model matrices. They do not independently validate demographic parameter-to-matrix construction, a Rust implementation, production equivalent-mode tolerances, or every finite EM trajectory.

The final rerun confirms explicit classification of nonfinite parity cases, 36 exact untouched-HMM_TINY cell checks, independent ordered aggregation and entropy-normalizer calculation, 49,968 finite candidate-Q checks, and a separately required finite 23-state/30-round unsplit fit. Invalid candidate categories are retained. The full bootstrap N=30 failures remain relevant even though the unsplit 30-round fit is finite.

### 4. Profiling is valid within its declared fixture

`bench/profile.json` reports finite K=64, N=5 output for a 52,800-bin synthetic fit and one materialized bootstrap. It records complete stdout parity between vanilla, instrumented, and gprof builds; matching optimizer-call counts; and bootstrap replay agreement. Final vanilla wall times were approximately 1.508095 seconds and 1.454017 seconds, with peak RSS 27,308 and 3,728 KiB respectively. These supersede the initial measurements after the timing-wait correction. The source and binary identities are recorded separately.

This supports investigation of forward, backward, expectation accumulation, and the M-step. It does not identify the dominant cost of the user's real job. Do not transfer its percentages directly to K=23/N=30 or whole genomes. The reported phase timers overlap: M-step includes model and objective work; they cannot all be added. Gprof sampling and instrumented timings perturb execution, and unresolved shared-library allocation/I/O costs remain limitations. Only vanilla totals are baseline timings.

The decision report's Amdahl illustration is supported by these instrumented values: forward plus backward account for approximately 43.88% of EM time, so removing only their cost gives a hypothetical ceiling of about 1.782x for this profile. It is correctly labeled as a bound on this example, not a forecast for the real workload.

### 5. PHLASH remains an alternative, with a pin-specific defect to resolve

The PHLASH audit distinguishes posterior approximation from resampled legacy fits and successfully exercises the RTX 5060 Ti custom CUDA likelihood. Its approximately six-second, two-iteration runs are setup-heavy feasibility checks. JAX stayed on CPU; no claim about full-GPU performance or posterior convergence is warranted.

The reproduced chunk-tail omission at the pinned PHLASH commit is material: with 10,000 bins, chunk size 2,000, and overlap 500, the final 1,500 bins vanish. Resolve and regression-test this behavior before scientific use. This defect is specific to the audited implementation and is potentially repairable. It does not invalidate Bayesian inference or, by itself, justify building a new legacy engine. PHLASH's VCF missingness/mask limitations independently favor validated PSMCFA/callability inputs for any future comparison.

### 6. Public artifact path review

The PHLASH JSON contains two absolute local paths, both identifying the Python runtime executable used for the measured runs. The audit document and JSON contain no absolute private genome/input/source paths. Source repositories are public immutable GitHub links; synthetic fixture references are relative. Under the requested exception for environment provenance, no redaction is needed in these PHLASH deliverables. This was a targeted review of those two files, not a certification of every archived file in the entire workspace.

## Appropriate decision gate

Accept the useful Phase 0 audit and harness evidence with its failed and deferred cases visible. Do not certify the entire performance milestone, promise 10x, call the shorter smoke a validated full baseline, or start numerical acceleration merely because the harness exists. Before approving the next implementation stage, review the intended output contract, replace or obtain missing numerical-design documents, define acceptance tolerances, and decide how to investigate the retained full-trajectory failures. Obtain the authorized real inputs, actual commands, masks, and existing worker budget before estimating benefit or choosing between equivalent legacy inference and a separately validated modern method.

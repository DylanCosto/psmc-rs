# Phase 0 decision: retain the reference, resolve the gate before a port

**Status: Phase 0 deliverables prepared; acceptance remains pending. No Phase 1, accelerated CPU inference, or legacy CUDA backend has started. No speedup is established.**

The provisional recommendation is to preserve the existing PSMC statistical calculation, keep pinned vanilla C as the strict reference, and consider an equivalent accelerated implementation only after numerical requirements and full trajectories are validated. The present evidence justifies a reproducible investigation, not a claim that building a new engine is better than using an existing method.

## What the user actually established

The initial request was “let's begin,” accompanied by planning documents. We adopted their Phase 0 scope as the starting task. The user then confirmed that the 30 bootstraps already run **in parallel**, authorized tests with vanilla PSMC, and delegated the output recommendation. The user did not supply an existing repository, exact command, input, worker count, or a requirement for universally identical bytes. Attached instructions are project context, not evidence of those missing facts or approval for later phases.

All deliverables live in this local `psmc-rs` folder; temporary comparator source, runtime and logs also live under the workspace's `work/` directory. Supplied originals were left unchanged. No genomic input was opened or uploaded, no remote repository was modified, and no compute was purchased.

## The three distinct choices

| Choice | Meaning | Phase 0 disposition |
|---|---|---|
| Exact legacy compatibility | Preserve original numerical records at printed precision on a pinned stack. | Use the original C executable. The instrumented C copy matches whole stdout on tested fixtures, including explicitly classified pathological output. No independent strict backend exists. |
| Numerically equivalent legacy acceleration | Same model, full-count EM, normalized Q, optimizer behavior, iteration count, sequence boundaries, bootstrap occurrences and output meanings; reviewed tolerances. | Recommended eventual engineering target, conditional on the unresolved gates below. No numerical tolerance policy or accelerated implementation has been approved. |
| Different modern method | Different scientific inference and uncertainty, such as PHLASH posterior approximation. | Credible alternative if its output addresses the user's scientific need. The smoke tests are not converged inference or a substitute for 30 legacy bootstraps. |

A tolerance of 1e-10/1e-12 used in the independent tiny-path diagnostic is **not** an accepted tolerance for PSMC parameter estimates, optimizer trajectories, or an equivalent release. The supplied algebra JSON also cannot establish that contract.

## Reference and hardware

Original PSMC is pinned to [`82fa2ada83ee463fe1251b562ae3d60e82d7ad6a`](https://github.com/lh3/psmc/tree/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a). The complete source audit and immutable line references are in [reference-contract.md](reference-contract.md).

The build uses GCC 13.3.0, upstream `-O2`, explicit `-ffp-contract=off`, default double precision, and no fast-math. It dynamically links glibc/libm 2.39 and system zlib. Source/archive/header/library/executable hashes and full commands are in `reference/build-vanilla.json`. Two fresh builds produced identical PSMC, splitfa and fq2psmcfa executable hashes on this stack. This does not promise cross-machine identity.

Local hardware is an Intel i5-12600K (10 cores, 16 logical CPUs), approximately 31 GiB physical RAM, and NVIDIA RTX 5060 Ti reporting 16,311 MiB VRAM, driver 595.91.07. The host is shared with existing user processes and had substantial swap usage at inspection. The intended production machine is unknown. `nvcc` is absent; the physical GPU works through PHLASH's separately installed NVRTC runtime. No legacy CUDA kernel was tested. See `bench/environment.json` and `bench/phlash.json`.

System zlib development headers were missing. A matching Ubuntu package was extracted locally without a global installation. `perf` sampling was denied under `perf_event_paranoid=4`; GNU gprof sampling was used without changing system privileges or settings.

## Correctness evidence and failures

The strengthened differential suite passed **52 checks**, with 0 failed harness checks. Its scope is C-versus-instrumented-C parity, original bootstrap replay, and independent path/count/objective checks using matrices constructed by C. It does not validate a Rust parameter-to-matrix implementation.

- Complete stdout comparisons use an empty metadata allowlist. Numerical `MM` records and `IT` optimizer counts are preserved.
- A 23-state, 30-iteration **unsplit** synthetic fit remains finite after the expected initial `RI inf` and matches exactly.
- All 30 ordered bootstrap manifests match the instrumented original draw/accept/stop trace and vanilla inference on the corresponding materialized records. This proves replay mechanics; some deliberately small parity cases reproduce nonfinite original results.
- The independent path enumeration covers three small sequences, missing observations and length one. Ordered full counts and Q normalizer agree, 36 zero-contribution pseudocount cells are checked exactly, and invalid candidate categories are retained.
- The original `psmc2history.pl` consumes the finite 30-iteration output successfully. Plot rendering is `not_run` because gnuplot is unavailable.

The **full 30-iteration bootstrap numerical gate failed** on the synthetic 23-state workload:

| Replicate | First nonfinite record | Repetition evidence |
|---|---|---|
| 16 | `QD`, round 28 | Reproduced in all eight completed measurement batches |
| 26 | `LK`, round 26 | Reproduced in all eight completed measurement batches |
| 28 | `RI`, round 23 | Reproduced in all eight completed measurement batches |

The ninth batch was interrupted after this was discovered. Failed and partial outputs are retained in `bench/raw/failed-23state/`, with the original manifest in `bench/failed-workload-23states.json` and an explicit [failure record](../bench/failed-23state.json). Those timings are excluded from successful performance conclusions. A four-state exploratory probe also produced nonfinite results in 28 of 30 replicates and was rejected; it is retained in `bench/exploratory-4state.json`.

These failures concern generated synthetic observations and the pinned reference. They are not evidence that the user's real fits fail. They also cannot be silently corrected in a compatibility port. The next investigation must establish the valid supported input/parameter domain, capture the failure-causing model/optimizer behavior, and decide how pathological reference cases should be classified.

## What the synthetic measurements do show

The final bounded-concurrency smoke uses the same 13,200-bin synthetic source fixture, original 23-state pattern, identical 30 materialized replicates, and **five iterations only**. Replicate lengths vary under the original bootstrap stopping rule. It checks the measurement machinery and early trajectories. It does not replace the failed 30-iteration gate. Each worker count was measured three times in rotated order, with one excluded warmup. Timings include process launch, input/output and fit exit, but exclude bootstrap materialization, preprocessing and plotting.

| Vanilla workers | Median batch seconds | Observed range | Largest individual peak RSS KiB |
|---:|---:|---:|---:|
| 1 | 2.023788 | 2.006343–2.032567 | 3,052 |
| 2 | 1.043177 | 1.019303–1.045008 | 3,052 |
| 4 | 0.550352 | 0.541336–0.555725 | 3,052 |

All 270 measured outputs matched their own replicate across worker counts and repetitions, completed five iterations, and were finite apart from the expected initial RI. The raw optimizer evaluation counts are retained per fit. Concurrent total RSS was not sampled; the manifest records per-process peaks and a conservative worker-times-maximum bound. Ordinary serial-to-parallel ratios are available in the machine-readable file, but the user's workflow already has parallelism, so those ratios are **not** project acceleration.

An initial tiny-smoke measurement used Python's timeout polling wait, which added noticeable completion-detection delay. It is labeled superseded in `bench/baseline-wait-polling.json`. The final helper uses blocking `waitpid` and a separate deadline watchdog. This is a measurement correction, not a PSMC optimization.

For a larger, separately labeled 64-state/five-iteration profile, the generated observations total 52,800 bins. Vanilla fit wall time was **1.508095 s**, peak RSS **27,308 KiB**; the materialized bootstrap was **1.454017 s**, **3,728 KiB**. These are one-run diagnostics, not stable production estimates. Vanilla, gprof, and phase-instrumented outputs matched exactly and remained finite.

Instrumented fit phase times were forward 0.314 s, backward 0.378 s, full counts 0.371 s, and M-step 0.500 s. Model/Q times are included in the M-step and must not be added again. Internal allocation costs remain inside several phases; only sequence/count setup allocation is separately timed. Input startup is measured, output I/O is not isolated. GNU gprof collected approximately 120 fit samples and 119 bootstrap samples.

As a limited inference from this instrumented example, forward plus backward is about 43.9% of measured EM time. Making only those phases infinitely fast would cap whole-EM improvement near **1.78x** under Amdahl's law. This is a hypothetical upper bound for this synthetic profile, not a speed forecast. Full counts and repeated Q/model evaluations also matter. Nothing here establishes a route to 10x on the user's already-parallel workload.

## PHLASH: runnable alternative, separate validation required

The comparator was pinned to [`96a6e3f8e01053271e88d21c97862198422d9ae0`](https://github.com/jthlab/phlash/tree/96a6e3f8e01053271e88d21c97862198422d9ae0). Both the CPU and custom-CUDA likelihood paths executed on a 4,000-bin synthetic fixture, with four particles and two SVGD iterations. Fit times including loading/JIT were approximately 6.139 and 6.094 seconds. JAX remained on CPU in the GPU run; only the verified custom likelihood kernel used the GPU. No GPU speedup, convergence, biological validity, or bootstrap equivalence is claimed.

Source audit and a direct reproducer found that this pin's default-like chunk geometry can omit a trailing region: 10,000 bins, chunk length 2,000 and overlap 500 left the final 1,500 bins unrepresented. The smoke geometry did not trigger it. This pin-specific behavior requires repair or a validated workaround before scientific adoption, but is not an argument against Bayesian inference generally. Read [phlash-audit.md](phlash-audit.md) for settings, model/input differences, primary-source links, exact dependencies and the reproducer.

## Remaining gate and next permitted work

1. Record the actual PSMC commands including `-p/-N/-t/-r/-i/-I`, worker cap/scheduler, input hash/bin size/boundaries, splitting procedure, reference assembly/masks, production hardware and timing scope. Run exactly the same existing parallel workload and matched bootstrap inputs. The real baseline remains **`not_run`**.
2. Investigate the retained nonfinite reference cases. Do not treat fewer iterations, reduced states or a different method as a fix for compatibility.
3. Recover or replace the missing `MATH_AND_COMPATIBILITY.md`, `VALIDATION_AND_BENCHMARKS.md`, `LONG_READ_ROADMAP.md`, and `SOURCES.md`. Review equivalent-mode tolerances and strict-mode support, including optimizer branching and failure behavior.
4. Review this decision before Phase 1. If the actual scientific need favors posterior inference instead, first validate PHLASH's input coverage and an appropriate converged run on authorized data.

The next permitted work is completing this Phase 0 gate. After review, Phase 1 would be a literal dense f64 Rust oracle with the pinned C path retained. CPU acceleration, GPU promotion, VCF/long-read adapters and a new statistical method are later tasks.

## Deliverable and command inventory

Created `reference/` build/instrumentation scripts and pin records, `tests/fixtures/` synthetic inputs, `bench/` reproducible manifests/harness/results/raw evidence, and `docs/` source/PHLASH/review/decision reports. Updated the copied execution plan's progress, decisions and surprises; retained supplied context under `planning/`. There are no production Rust files.

Commands actually run include the pinned source clone/archive; local zlib package extraction; three `reference/build.py` variants; `bench/prepare.py`; `bench/differential.py`; bounded `bench/run.py`; `bench/profile.py`; the original `psmc2history.pl`; and isolated `bench/phlash_probe.py` CPU/custom-GPU probes. Exact argument vectors, compiler commands, dependencies and hashes are stored next to their results. [README.md](../README.md) provides the reproducible sequence. Source audits were independently reviewed; limitations and repairs are recorded in [harness-review.md](harness-review.md) and [phase-0-review.md](phase-0-review.md).

# CPU campaign release acceptance record

Version **0.3.1 is accepted** for the measured strict CPU workload envelope. Its
separate 64-state AVX message kernels deliver an 8.2% full-fit throughput gain
versus Phase 3a in the final benchmark, with exact compatibility and essentially
unchanged smaller-state controls. No universal optimum or 10x result is claimed.
The delivered executable is `bin/psmc-rs`, SHA-256
`b0fc39d7c31637221de1152fc0d502bb65c90d0a5b9d6672250fe3117f75bfa4`.

The strategy is to profile complete fits, prioritize measured costs, test each
candidate's exactness before timing, and accept only a demonstrated whole-workload
benefit. Kernel timing is diagnostic. One logical CPU at reduced priority is the
resource limit for all builds, tests, fits and packaging. No concurrent heavy
jobs, subagents or multiworker benchmarks are used.

The retained comparison is Phase 3a source `6a4d102`, binary
`8e417125208343026d56bae1b540b058371e4a0e949ca148a73c696b217f637b`.
The campaign starts from checkpoint `f16131e`; source digests in the final build
record identify the exact changes. Pinned vanilla remains commit
`82fa2ada83ee463fe1251b562ae3d60e82d7ad6a`. Rust 1.90.0, opt-level 2, one codegen
unit, no LTO, generic target plus runtime AVX detection, and the same system libm
remain the release configuration. Clippy was installed for the pinned toolchain;
its existing style warnings are retained, including the unchanged optimizer's
shadowed-radius diagnostic. No numerical rewrite is made to satisfy a style lint.

## Candidate decisions

| Candidate class | Decision and evidence |
|---|---|
| Log/objective caches | Exact screens, no consistent fit improvement; reject |
| Grid and model-invariant reuse | Exact reuse/nonfinite tests, no consistent fit improvement; reject |
| Generic 8/16-destination AVX loops | K64 gains but smaller-state regressions; specialize further |
| Fixed-64 loops inside generic functions | About 4% K23 regressions; reject |
| Separate fixed-64 functions | Accepted after complete exactness, integration and final timing gates |
| Per-record const specialization | New K23 bootstrap median ratio 0.946x; reject |
| Ordered count tiles | Correct but slower complete fits; reject |
| Masked tails | Kernel gains fail to translate to full fits; reject |
| opt3, LTO and PGO | No consistent gain on held-out fits; retain release profile |
| Structured message/Q algebra | Exact-bit counterexamples; quarantine, no tolerance relaxation |
| Checkpoint/recompute | Exact fixed-model messages/counts and much lower RSS, additional CPU cost; experimental memory option only |
| Finer setup/allocation/I/O work | Small diagnostic share in tested cases; defer further work pending representative larger inputs |

The [campaign experiment record](cpu-campaign-progress.md) contains measurements,
failed candidates, source derivations and all raw-report links. The
[64-state derivation](cpu-campaign-wide64-derivation.md) states the lane-order and
memory-safety proof. The dense oracle, model construction, Q and optimizer are
unchanged. No altered sampling, missingness, boundaries or count multiplicity is
used to obtain a speedup.

## Numerical contract and gate coverage

Only the single legacy `MM Version` line is excluded from output comparison.
All other output bytes, optimizer iteration/evaluation counts and metadata remain
part of the gate. Internal finite binary64 values and signed zero must match
exactly; nonfinite classes and event order are checked separately.

The new 64-state path passes the complete K64/N1 internal trace: 15,160 ordered
events and 36,956,397 finite numerical fields, with zero mismatches. This includes
7,577 objective callbacks as well as complete models, sequence messages, counts
and EM completion. It is an internal correctness gate, not a timed benchmark.
The retained independent Phase 1 enumeration trace and unchanged core-source
hashes supplement the newly repeated dense/CPU/scalar checks; exclusions are
explicit in the validation report.

The final dense/CPU/scalar differential suite passes all **340 checks**. Across
10 complete snapshot pairs, 37,789 ordered events and
43,513,458 finite numerical fields match with
zero discrepancies. Each path retains the original 27 finite bootstraps and
pathological replicates 16, 26 and 28. Debug and release unit suites each pass
32 tests; assembly inspection finds 51 packed AVX arithmetic instructions and
zero FMA/horizontal-reduction instructions in the executable.

The extended gate adds 66 exact matches: 39 finite fits and 27 retained reference
pathologies. The scheduler passes 60 full fits in forward/reverse submission order
with exactly one worker, including cache accounting and repeated occurrences.
All 38 CLI/dispatch checks pass. Runtime selection on this host uses AVX for the
measured 23/64-state workloads; the specialized message functions are selected
only at 64 states. The shape review exercises auto/off/forced AVX at 11 sizes:
auto selects scalar for 1–3 states and AVX for the remaining 8 sizes. Forced-off
runs stay scalar. Absent-AVX detection is simulated in unit tests, not a physical
hardware result. The CLI batch controls report the expected path for every replicate.

## Final uninstrumented measurements

Measured on an Intel Core i5-12600K, pinned to logical CPU 0 at nice 10. Each
single-fit result uses five measurements after a warmup, rotating implementation
order. Every measured output matches pinned C exactly. Values below are child
CPU seconds, median [minimum–maximum]; ratios above one favor 0.3.1.

| Case | Vanilla C | Phase 3a | 0.3.1 AVX | Phase 3a / new | C / new |
|---|---:|---:|---:|---:|---:|
| K23 / 30 rounds | 0.362 [0.345–0.688] | 0.252 [0.245–0.527] | 0.253 [0.242–0.573] | 0.995x | 1.430x |
| K64 / 5 rounds (partial) | 1.434 [1.408–1.447] | 0.998 [0.993–1.841] | 0.864 [0.857–0.892] | 1.155x | 1.659x |
| K64 / 30 rounds, mixed 50k | 7.818 [7.749–7.887] | 4.996 [4.985–5.074] | 4.616 [4.589–4.647] | 1.082x | 1.694x |
| K23 / 30 rounds, model-based bootstrap 10 | 1.722 [1.716–1.750] | 0.553 [0.550–0.561] | 0.547 [0.542–0.562] | 1.011x | 3.148x |

The full K64 case has separated measured CPU ranges and an 8.2% throughput gain
(7.6% less CPU time) versus Phase 3a. Earlier six-block ABBA/BAAB confirmation
found a 1.116x median paired ratio, positive in every block. Smaller-state controls
are effectively unchanged within the observed variation; no new K23 gain is
claimed. This is the measured envelope supporting the separate-function change.

| Case | New wall seconds, median [range] | New peak RSS KiB, median [range] |
|---|---:|---:|
| K23 / 30 rounds | 0.253 [0.242–2.805] | 5320 [5304–5348] |
| K64 / 5 rounds (partial) | 0.865 [0.857–0.892] | 26944 [26920–27028] |
| K64 / 30 rounds, mixed 50k | 4.617 [4.590–4.648] | 25260 [25216–25328] |
| K23 / 30 rounds, model-based bootstrap 10 | 0.547 [0.542–0.562] | 5080 [5048–5100] |

All implementations' wall/CPU/RSS samples remain in the [benchmark report](../bench/cpu-campaign-benchmark.json).
The K23 wall range includes substantial host interference; no sample was discarded.
The change adds no message arrays; full K64 peak RSS medians are 25,228 KiB for
Phase 3a and 25,260 KiB for 0.3.1, with overlapping ranges.

The final fixed-model kernel benchmark compares forced scalar with final AVX,
not with Phase 3a. Scalar/AVX section-wall ratios are 1.198x at K23, 2.319x at K64.
These sections include prepared-layout construction; exact checks run separately.
They do not imply the same complete-fit or bootstrap speedup.

## Serial bootstrap and remaining costs

The original 30-fit batch has one warmup and three measurements per executable.
It includes 27 finite trajectories and three reference pathologies, so the table
measures batch mechanics rather than 30 valid scientific results. All outputs
match the materialized vanilla replicates, and the Rust scheduler admits exactly
one worker. Its reported AVX selection is checked for every replicate.

| Implementation | CPU seconds, median [range] | Wall seconds, median [range] | Peak RSS KiB, median [range] |
|---|---:|---:|---:|
| vanilla | 11.226 [11.136–11.360] | 11.684 [11.595–11.829] | 3048 [3048–3048] |
| phase3a | 6.962 [6.948–7.005] | 6.963 [6.950–7.006] | 4060 [4028–4068] |
| simd | 6.773 [6.745–6.785] | 6.774 [6.747–6.786] | 4260 [4168–4372] |

C RSS is the maximum of sequential individual process peaks; Rust RSS covers
one scheduler process and its one numerical worker. The new/old Rust comparison
has the same scheduler scope. CPU ratios are 1.657x versus vanilla and 1.028x
versus Phase 3a. The small incremental K23 batch difference is not treated as a
reliable new bootstrap acceleration claim on this shared host; no K64 bootstrap
batch or parallel throughput gain is inferred. No run is discarded.

The separate final CPU diagnostic passes exact outputs against both frozen
Phase 3a and vanilla for all four cases. It instruments only a disposable source
copy, whose source hashes match the final build before timer injection.

| Case | Q / main CPU | Model / main CPU | Counts / main CPU |
|---|---:|---:|---:|
| k23-n30 | 34.6–35.1% | 21.1–21.5% | 18.7–18.8% |
| k64-n5 | 49.1–49.4% | 16.9–17.4% | 18.6–19.0% |
| mixed-k64-n30 | 44.1–44.2% | 16.6–16.8% | 25.0–25.2% |
| bootstrap-00-k23-n30 | 41.4–41.6% | 24.6–24.9% | 13.3–13.4% |

These fractions include timer overhead and are not uninstrumented speed claims.
Nested scopes overlap. Full K64 forward/backward together account for about 12.3%
of diagnostic main CPU, leaving limited return from more message-only tuning.
Q/model/count work dominates, but the tested exact alternatives did not improve
complete fits. Hardware counters remain unavailable; setup/validation and I/O
are grouped/residual costs rather than precisely measured allocation or I/O calls.
[Final diagnostic and all runs](../bench/cpu-campaign-final-profile.json).

## Evidence and reproduction

Production changes: `crates/psmc-cpu/src/simd.rs`, the two CLI version strings,
and workspace/lockfile version metadata. Dense core, CPU engine/cache and generic
workspace source hashes remain unchanged. Every numerical candidate has a linked
derivation, generated source, isolated tests and timings; rejected candidates
remain under the benchmark directory and never enter the inference binary.

The [build record](../bench/cpu-campaign-build.json) records source/compiler/library
hashes and configuration. [Cargo checks](../bench/cpu-campaign-cargo.json),
[full C gate](../bench/cpu-campaign-validation.json),
[extended cases](../bench/cpu-campaign-extended.json),
[scheduler](../bench/cpu-campaign-scheduler.json),
[CLI review](../bench/cpu-campaign-review.json) and
[assembly audit](../bench/cpu-campaign-assembly.json) preserve actual commands/results.
The gate orchestrator runs every stage sequentially:

```sh
taskset -c 0 nice -n 10 python3 bench/cpu_campaign_release_gates.py
```

Use an allowed logical CPU and first build the pinned C references as documented
in the reference build scripts. The Rust toolchain, Clippy and preserved Phase 3a
binary must be present; no external Cargo registry packages are required.
Historical experiment injection scripts require Phase 3a source, as described
in [packaging](../PACKAGING.md). The final archive excludes build caches and large
compressed snapshots, whose exact hashes and local paths remain in its omission
manifest. All included files receive SHA-256 checksums and archive verification.

The [delivery consistency audit](../bench/cpu-campaign-delivery-check.json) confirms
the delivered binary, source hashes, all required gate reports and preserved old
release hashes.

## Limits

The workload is synthetic and the machine is shared. CPU time excludes scheduling
delays but still reflects frequency/cache interference. Historical 10x acceleration
and real production throughput remain unproven. Original nonfinite vanilla cases
remain pathology controls, never valid scientific fits. No multicore speedup is
claimed. ARM/NEON, AVX-512 and physical unsupported-AVX hardware are not tested;
scalar dispatch is exercised on this AVX host. Real user inputs, commands,
splitting settings and hardware remain needed for production validation.

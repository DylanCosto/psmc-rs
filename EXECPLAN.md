# Execution plan: accelerated, legacy-compatible PSMC

Current status: v0.6.3 adds memory admission for strict single CPU fits. The prospective 200 Mb panel passed all primary-band and event checks; all 30 strict fits match pinned C. Strict remains default and equivalent opt-in. Whole-genome and actual-workload qualification remain open; hosted CI awaits a remote URL. See docs/known-truth-200mb-report.md.

Historical starting status: User explicitly approved building Rust on 2026-10-10. Phase 1 dense scalar Rust is implemented and passes its supported synthetic gate; see docs/phase-1-report.md. Real-workload baseline and reference-pathology investigation remain recorded limitations, not blockers to the newly authorized port. The user subsequently authorized optimization; Phase 2 CPU engineering and deterministic scheduling now pass the local synthetic gate; see docs/phase-2-report.md. The validated dense oracle remains unchanged. The original research/design completion checkboxes below were supplied with the plan and are not independent verification of the four missing companion documents.

## 1. Product definition and decision gates

The first product is a local command-line executable and reusable Rust library that accept existing `.psmcfa` data and reproduce the numerical meaning of the original PSMC output. It should reduce both single-fit latency and throughput time for 30 bootstrap replicates, without changing the scientific calculation to obtain that speedup.

A second product layer may convert modern VCF/gVCF/BCF and phased-assembly data into carefully validated PSMC inputs. A third, independently approved research track may exploit long-read phasing with multi-haplotype or genealogical methods. The three products have different compatibility claims and must not be conflated.

PHLASH is a required alternative-method comparator. It already supplies GPU acceleration and Bayesian uncertainty. Its existence does not eliminate a legacy-compatible performance project, but it changes the novelty and prevents a defensible claim of being the first GPU PSMC-like tool. Gamma-SMC is another useful technical comparator for decoding, not an output-equivalent substitute for PSMC fitting. [S11–S13]

## 2. Compatibility modes

Define and expose the modes before optimization:

| Mode | Contract | Permitted implementation |
|---|---|---|
| `strict` | Matching numerical records at the original printed precision on a pinned execution stack; byte-comparison after a small explicit metadata allowlist | Dense scalar path and only individually demonstrated parity-preserving optimizations |
| `equivalent` | Same model, preprocessing, EM procedure, iteration count and bootstrap samples; prospectively validated arithmetic; QU replaces QD under the later explicit user contract | Structured CPU scans, deterministic triangle margins and checkpointed messages; strict retains full-count EM |
| `research` | Explicitly different numerical or statistical procedure | Augmented EM, alternate optimizers, posterior inference, different emissions or long-read models |

Do not promise universal cross-architecture bitwise equality. A pure Rust port still may differ from C through libm, code generation, arithmetic contraction, or optimizer branch decisions. If strict mode cannot meet its own contract, label it unsupported on that stack and retain the pinned original executable as the external reproducibility oracle. The normal release cannot silently downgrade `strict` to `equivalent`. [S19, S20]

Initially make only the proven strict CPU path available. Promote a faster equivalent backend after validation and human approval of its numerical contract. Store mode, backend, numeric settings, and provenance outside or in explicitly additive metadata, without changing legacy field meanings.

## 3. Proposed architecture

Use a small Cargo workspace rather than a large general-purpose framework:

```text
psmc-rs/
  AGENTS.md
  EXECPLAN.md
  Cargo.toml
  Cargo.lock
  rust-toolchain.toml
  crates/
    psmc-core/       # model, parameters, legacy EM, backend interface
    psmc-io/         # psmcfa, bootstrap manifests, legacy output
    psmc-cpu/        # scalar oracle, structured F/B, count kernels, checkpointing
    psmc-cuda/       # optional CUDA kernels and cuBLAS bridge
    psmc-cli/        # fit, bootstrap, inspect, compare, provenance
    psmc-input/      # later: VCF/gVCF/BCF + callable-mask adapters
  reference/        # pin record, fetch/build scripts, minimal instrumentation patches
  tests/fixtures/   # synthetic and authorized small public fixtures
  experiments/      # algebra prototypes, not the production oracle
  bench/            # manifests, scripts, raw results, comparison reports
  docs/             # contracts, derivations, decisions, limitations
```

Proposed interfaces, to refine after source audit:

- `EncodedDataset`: immutable sequence observations, stable IDs, original boundaries, lengths, content digests, metadata. Store byte observations initially; pack to two bits only after profiling proves it useful.
- `LegacyParameters`: exact original parameter order and grouping map, including the maximum-time parameter and supplied time-grid behavior.
- `ModelSnapshot`: initial distribution, emissions, dense transition matrix, and validated structured factors for a specific parameter vector.
- `SequenceStats`: log likelihood, full expected transition counts, emission counts, initial-state counts, and required diagnostics. Initial-state counts are retained even where the original objective does not use them.
- `ExpectationBackend`: consumes a snapshot, an existing independent sequence, and reusable workspace; returns sequence statistics without changing parameter optimization.
- `BootstrapManifest`: ordered source block IDs for each replicate, RNG specification/state, input hash, splitting provenance, and expected lengths. It can materialize original-compatible input files for paired reference runs.
- `ExecutionPolicy`: total CPU worker budget, memory budget, backend, precision, deterministic-reduction policy, checkpoint size, and GPU batch configuration.

Keep the M-step CPU-based initially. Transfer one small parameter snapshot to an accelerator and return compact statistics, not the entire genome at every EM iteration. Keep observations resident when memory permits. CPU model construction also reduces opportunities for GPU transcendental-function differences.

Use Rayon for bounded CPU tasks and consider cudarc for CUDA/cuBLAS access. Use a mature format library such as noodles only in the later input module. Lock the actual tested versions; these are dependency candidates, not a guarantee that a specific version combination already works. [S21, S22]

## 4. Phase 0 — baseline, reference contract, and build-versus-use decision

### Tasks

Obtain the real workload description: exact commands and `-p/-N/-t/-r/-i/-I` settings; whether bootstrap processes already run concurrently; input type and hash; bin size; sequence lengths and boundaries; `splitfa` command; reference assembly; mask provenance; CPU/RAM/GPU; local or VM configuration; and whether preprocessing or plotting is included in the reported hours. Do not block all work on missing information: build small synthetic fixtures, but keep the real benchmark pending.

Fetch and pin a concrete `lh3/psmc` commit. Record compiler, flags, libm/libc, OS, architecture, and executable digest. Build one normal reference and, separately, a minimally instrumented test reference for internal-array snapshots and deterministic seeds. Instrumentation must not change the numerical algorithm. Keep the unmodified build for timing.

Audit `cli.c`, `core.c`, `khmm.c/.h`, `em.c`, `kmin.c/.h`, `aux.c`, `main.c`, `psmc.tex`, and preprocessing utilities. Read implementation behavior instead of assuming comments are accurate. Record every supported flag and every deliberate scope exclusion. Preserve upstream notices. [S01–S09]

Profile a representative fit and at least one bootstrap with a sampling profiler. Measure forward, backward, expectation accumulation, model construction, M-step objective evaluations, allocations, I/O, peak RSS, and total time. Save the number of optimizer evaluations per iteration, not just iteration count. Establish original serial and original bounded-parallel 30-replicate baselines.

Run a small, separately labeled PHLASH feasibility benchmark where suitable hardware/data are available. Record its posterior settings and runtime, not an artificial '30 bootstrap equivalent'. Evaluate whether the actual scientific need can be met without preserving legacy output. Inspect PHLASH's structured matvec/GPU approach for prior art; do not assume its parameterization and preprocessing match original PSMC. [S11, S12]

### Deliverables and gate

Produce `docs/reference-contract.md`, `bench/workload.json`, `bench/baseline.json`, and `docs/phase-0-decision.md`.

The decision must say whether to proceed with the compatibility engine, adopt an existing method, or prioritize input/QC tooling. The user's request to preserve outputs favors the compatibility engine, but the tradeoff must be explicit. **Human review before Phase 1.** No hypothetical 10x result may be recorded as measured.

## 5. Phase 1 — scalar Rust numerical oracle

Port the original calculation as literally as reasonably possible into flat, contiguous f64 arrays. Preserve loop direction and arithmetic grouping in this first version. Implement parsing, parameter grouping and initialization, transition/emission construction, scaled forward/backward, full expectation counts, the actual Hooke–Jeeves behavior, and output records.

Do not 'fix' scientific or numerical quirks during the port. In particular, use the observed endpoint rules, HMM_TINY initialization, objective normalization, optimizer callbacks and side effects, and iteration reporting order. Test supplied parameters and the optimized maximum-time parameter. Separate runtime safety improvements, such as rejecting malformed/empty input, from changed answers on inputs that the reference successfully processes.

Add small deterministic C-versus-Rust snapshot fixtures. Retain the generic structured-HMM algebra experiment as a check of identities, not as the reference for PSMC model construction. The production oracle must come from the pinned C source.

### Gate

All supported small fixtures pass parsing, matrix, likelihood, count, objective, first-M-step, and full-run comparisons. The legacy plotting/conversion scripts can consume the generated files. Any unsupported flag is rejected explicitly, not ignored. No CUDA work is permitted before this gate.

## 6. Phase 2 — CPU engineering and reproducible bootstrap scheduling

Eliminate repeated sequence copies and per-position heap allocations. Allocate reusable workspaces per worker. Precompute transition transposes and transition/emission products once per parameter snapshot. Use contiguous buffers and stable indices.

Parallelize independent bootstrap replicates and existing independent sequence records. Prefer one global, memory-aware work queue to nested pools. A run with many bootstrap replicates may use one or a few workers per replicate; a single fit may distribute chromosomes across the budget. Coordinate BLAS threads with Rayon; do not create `replicates × workers × BLAS threads` runnable threads.

For each replicate, compute sequence statistics in any scheduling order but merge them in recorded input order. An indexed collection followed by a deterministic merge is safer than an unconstrained parallel floating-point `reduce`. Bound in-flight results so long chromosomes do not exhaust RAM.

Represent bootstrap replicates as ordered block references, not copies of complete genomes. Preserve the actual `psmc_resamp` sampling and total-length stopping behavior; it is not necessarily 'draw exactly the original number of blocks'. Preserve splitting units and unequal terminal chunks. [S06, S09]

Cache a repeated block's statistics within the same parameter snapshot and add its contribution for every sampled occurrence. Include pseudocount contributions at the same multiplicity. Strict mode must preserve repeated-addition order rather than substituting a multiplication by the repeat count. Do not reuse cached statistics between replicates that have different parameter vectors, even if both are on the same EM iteration.

### Gate

Results are stable across worker counts and task order. Real or synthetic repeated-block and unequal-length bootstrap fixtures match the reference. Publish both serial and parallel speedups, peak memory, and cache hit rates. Speedup from ordinary bootstrap parallelism must be reported separately from kernel acceleration.

## 7. Phase 3 — exact-algebra CPU acceleration with full legacy statistics

Derive and implement the original transition matrix's lower-triangular rank-one, upper-triangular rank-one, and diagonal structure. Use exclusive prefix/suffix recurrences for matrix-vector products. This reduces forward and backward work from O(LK²) to O(LK) without a change to the real-arithmetic matrix. Derive factors from the audited original equations, preserve the diagonal separately, and test their positivity and reconstruction error over valid parameter ranges. [S02, S10]

Keep the full K×K expected transition-count matrix for the compatibility engine. Compute it with an optimized, tiled outer-product kernel or the matrix-product identity in `MATH_AND_COMPATIBILITY.md`. Benchmark both; a BLAS call for every genomic bin is not acceptable. The full-count step remains O(LK²) in arithmetic complexity, but is regular, vectorizable work that can be much better organized.

After full counts are available, compute the legacy entropy normalizer once and derive triangular count margins. Benchmark the factored O(K) candidate objective and model-factor construction during repeated M-step evaluations, without replacing the optimizer or dropping the normalizer. Preserve invalid-candidate handling and keep the dense objective as the strict reference. This optimization can matter if the M-step becomes the bottleneck; the algebra and numerical caveats are in `MATH_AND_COMPATIBILITY.md`.

Fuse backward traversal with expectation accumulation where it saves memory. Benchmark auto-vectorized loops before hand-written intrinsics. For multiple independent sequences sharing parameters, also test SIMD across sequences; this can avoid some across-state summation-order changes. Handle lengths and masked observations explicitly.

Implement checkpoint/recompute for long sequences: store selected forward messages, regenerate local forward/scaling arrays while moving backward, and carry exact boundaries between computational tiles. The output sequence must remain the same HMM sequence. Choose tile sizes by a measured time/memory sweep; do not encode one hardware-specific magic constant as universally optimal.

### Gate

Pass fixed-parameter numerical tests, full-count/objective comparisons, full EM trajectories, all user-requested bootstraps, and memory limits. Profile again. If full counts or the M-step now dominate, record the new bottleneck and apply Amdahl's law before writing GPU kernels.

## 8. Phase 4 — CUDA, but only for measured remaining bottlenecks

Build the optional GPU backend against the same `ExpectationBackend` contract. Start with genuine FP64 arithmetic. No implicit lower-precision tensor math or FP64 emulation should enter the compatibility baseline. Record math and cuBLAS modes explicitly. [S19–S21]

Prototype two mappings instead of assuming one is optimal:

- Thread-per-independent-sequence, with serial state scans, as a low-synchronization candidate. Measure register/local-memory pressure.
- Warp/cooperative-block-per-independent-sequence, with parallel state work and exclusive state scans. Benchmark both 64-state specialization and generic K. Measure synchronization overhead and occupancy.

Here 'sequence' means an original independent chromosome/record or a bootstrap block already defined by the reference input. Do not break a chromosome into new statistical sequences to obtain more GPU work. Computational tiles may be scheduled after their required messages are available.

Batch sequence/replicate tasks and bucket by length and K to reduce padding. Terminated/padded lanes must be exact no-ops, not artificial observations or added transitions. Different replicate parameter vectors are separate snapshots; never accidentally share one transition matrix across all bootstraps.

Keep observations and reusable buffers resident. Build parameters on CPU initially. Accumulate per-task compact statistics and transfer these back for the existing CPU M-step. Use bounded tile workspaces, explicit stream ownership, deterministic reduction order, and reproducible cuBLAS configuration. Avoid one host kernel launch per bin and avoid floating-point atomic summation into one global count matrix.

For full transition counts, test CUDA tiled outer products against cuBLAS DGEMM on time tiles. Include packing, device transfers, synchronization, checkpoint recomputation, and reduction cost. Do not benchmark only the GEMM. Use Nsight Systems/Compute to inspect spills, launch gaps, bandwidth, compute saturation, and CPU M-step idle periods. Optimize those measured issues, not theoretical peak TFLOPS.

Treat FP32/mixed precision as a later research feature requiring explicit approval; it is not the route to the initial 10x claim. FP64 hardware throughput varies substantially, so the GPU may not beat the optimized CPU on the available machine. [S19, S20]

### Gate

CUDA must pass the same numerical/EM/bootstrap suite and beat the optimized CPU end-to-end on a declared target workload. Otherwise retain CPU as default. Missing accelerator access blocks promotion of the CUDA backend, not the rest of the project. Add an explicit memory-budgeted fallback that is visible in provenance and included in timings.

## 9. Phase 5 — release and reproducibility

Implement legacy-compatible command aliases only for supported flags. Add explicit modern commands such as `inspect`, `bootstrap`, and `compare`; mark them as new interfaces. Use atomic checkpoint/output replacement and fail-safe resume. A checkpoint includes input and model hashes, bootstrap manifest, current parameters, iteration/optimizer state needed for the chosen resume granularity, backend, numeric mode, and tool versions. Initially resume only between EM iterations, not halfway through the optimizer.

Bundle small synthetic regression fixtures, source-pin records, benchmark scripts, the exact tolerance policy, and documented limitations. Record whether the final decoded results are available or were intentionally not requested. Use existing plotting scripts for compatibility validation before adding new plotting functionality.

Release only after the complete benchmark matrix and failures are reviewed. A worthwhile CPU-only release is preferable to an unverified GPU claim. Separate software compatibility validation from population-genetic interpretation and any future clinical/commercial validation.

## 10. Phase 6 — long-read input layer; separate approval for a new method

Implement the input and QC roadmap in `LONG_READ_ROADMAP.md`. Preserve original `.psmcfa` compatibility as a stable baseline. Do not change the core emissions to accept structural variants, repeats, or uncertain genotypes without naming and validating a new model.

A phase-aware demographic/ARG extension requires a new research plan, simulation study, and comparisons to existing methods. It must not delay completion of Phases 0–5.

## 11. Performance definitions and stopping conditions

Primary target: 10x faster end-to-end completion of the same 30 materialized bootstrap replicates versus the user's recorded workflow. Report separately the ratio against optimally bounded parallel original PSMC. Also report single-replicate single-core speed, all-core speed, GPU-versus-optimized-CPU speed, and peak host/device memory.

A speedup that requires fewer iterations, different bootstrap draws, smaller masks, fewer states, or different uncertainty estimation is not this project's compatibility speedup. Original reference compilation must be reasonably optimized and must not be deliberately disadvantaged.

Stop and investigate on a numerical-gate failure, inconsistent random replay, changed sequence boundaries, apparent speedup caused by skipped work, unexplained optimizer branching, or results dominated by fallback. Redirect effort when profiling shows that the proposed optimization cannot deliver a meaningful end-to-end improvement.

## Progress

- [x] Primary-source review and design prepared.
- [x] Independent algebra experiment prepared; see its result JSON.
- [x] Phase 0 reference: pinned vanilla C build, instrumentation, source contract, synthetic manifests, differential harness, sampling profiles, PHLASH feasibility audit.
- [x] Phase 0 evidence: 52 mechanics/parity checks; finite unsplit30-iteration fit; bounded five-iteration smoke; full30 bootstrap failures retained.
- [ ] Phase 0 acceptance: actual-workload baseline, numerical failure investigation, missing companion documents, and decision review.
- [x] Phase 1: dense Rust oracle; 115 exact differential checks, 30 full bootstrap trajectories, isolated and internal snapshot gates, conversion, review and measured baseline complete on the pinned Linux stack.
- [x] Phase 2: strict CPU workspaces, exact repeated-block cache and bounded bootstrap queue; 226 differential checks, 180 schedule-invariant fits, 17 review controls and equal-worker measurements complete on the pinned synthetic stack.
- [x] Phase 3a: strict single-thread AVX SIMD, generic fallback, 340 differential checks, 32 debug/release unit tests, 38 CLI controls and serial benchmarks.
- [x] Phase 3: structured CPU/objective acceleration, linear equivalent E-step and prospective human-panel validation; strict full counts retained.
- [x] Current follow-up: exact shared-record scheduler, complete paired strict/equivalent timing gate and v0.6.1 installation.
- [ ] Phase 4: optional CUDA promotion.
- [x] Phase 5: local CPU releases and public human-panel validation through v0.6.0; broader hardware/scientific generalization remains unclaimed.
- [ ] Phase 6: long-read input layer.

## Decisions and surprises

Initial: preserve legacy EM rather than silently adopting augmented EM. Preserve full counts because the original objective includes a full-count entropy normalizer. PHLASH is pre-existing GPU prior art. Long-read assembly support already exists through the original documented dipcall route. Subsequent changes must be appended with evidence and date.

Current follow-up: the user explicitly authorizes QU and margins-only equivalent counts. The linear E-step passed its prospective C-calibrated gate and reduced median batch time by 67.71%. Scheduling must independently preserve every mode's output; measured policy screens rejected all-core and six-physical-core fit ownership in favor of testing twelve P-thread owners. Details and preserved evidence are appended below.


## Session decisions — Phase 0

- The direct user clarification establishes that 30 bootstrap processes already run in parallel. Original bounded-parallel throughput is the required eventual comparator; serial scheduling gains are not a project acceleration claim.
- The user delegated the output recommendation. Prefer the same legacy statistical calculation with a reviewed equivalent numerical contract, retaining pinned vanilla for strict reproduction. This is provisional, not approval of Phase 1 or proof that a new engine is preferable.
- Source pinned to `82fa2ada83ee463fe1251b562ae3d60e82d7ad6a`; GCC13.3, O2, explicit no contraction, glibc2.39. See `reference/build-vanilla.json`.
- All work is in a new local Phase 0 project; no intended existing repository or real input was supplied. Synthetic fixtures and exact input hashes are recorded.
- Shortened five-iteration runs test the harness only. They do not resolve30-iteration failures or contribute a compatibility speedup claim. See `docs/phase-0-decision.md`.

## Session surprises and unresolved issues

- Actual C excludes the last site's emission count, initializes per-sequence counts with1e-25, keeps the full-count Q normalizer, and leaves final live parameters at the last optimizer callback. The source contract records these behaviors without correcting them.
- Original K23/N30 synthetic bootstrap replicates16,26,28 produced nonfinite output, reproduced in eight completed measurement batches. The ninth was interrupted. A smaller-state exploratory probe also failed and was rejected; all failures remain in the evidence bundle.
- The finite K23/N30 unsplit fixture and52 passing harness checks do not supersede those failures. The current harness explicitly separates pathologic output parity from finite trajectories.
- Kernel sampling through perf is blocked by host policy. GNU gprof sampling and separate monotonic phase timers work; no privileges or machine settings were changed.
- A subprocess timeout polling delay affected the first tiny-smoke wall-time measurement. The final harness uses blocking waitpid plus a deadline watchdog. Superseded measurements are retained and excluded from current conclusions.
- PHLASH CPU and hybrid custom-CUDA smoke tests execute on the RTX5060Ti; they are not output-equivalent or converged inference. The inspected pin can omit trailing observations under particular chunk geometries; resolve this before scientific adoption.
- Four referenced companion documents, exact real command/input/worker budget, and real preprocessing/mask provenance remain unavailable. Tenfold speedup, independent Rust compatibility, legacy GPU execution, and real-data inference are untested.


## Phase1 authorization and working decision —2026-10-10

The user said, "Great, let's go ahead and build with rust." This is the review/authorization to begin the dense Rust milestone despite the outstanding real-workload and reference-pathology evidence. Do not request the same approval again. Preserve those limitations and all previous evidence; do not infer approval of acceleration or CUDA.

The original missing math/validation companion files were not recovered. New explicitly labeled `MATH_AND_COMPATIBILITY.md` and `VALIDATION_AND_BENCHMARKS.md` document a literal source-backed port and exact comparison policy before Rust results are inspected. The missing long-read roadmap and source bibliography remain deferred; no long-read code is being built.

Workspace initially consists of core numerical library, input library and CLI. Rust1.90.0 is pinned because it is installed and verified locally; no registry dependencies are introduced. Platform libm supplies log/exp and libc supplies legacy float formatting. Input gzip support uses a small audited zlib boundary. Inference, model construction, EM, optimizer and parsing are Rust code.

## Phase 1 completion — 2026-10-10

- The delivered final executable e112ed9a…e65dd0 passes all 115 differential checks, 17 unit tests in each of debug/release, 76 isolated model/optimizer cases (70,408 exact binary64 values), and 11 CLI review controls. Five complete internal snapshot pairs compare 122,725 events and 42,642,569 finite numeric fields exactly. Only the honest program/version output record is excluded.
- All 30 materialized K23/N30 bootstrap outputs match vanilla. Twenty-seven are finite; 16, 26 and 28 reproduce the original recorded nonfinite cases and are not scientific-validity successes. Nonfinite optimizer trials are retained. Runtime warnings are supplemental: RI-only NaNs can occur without a warning.
- Upstream history and plotting-data scripts consume Rust output and generate identical data. Rendering is not_run without gnuplot. Clippy is not_run because the pinned component is absent.
- Single-fit median times: C/Rust 0.383/0.485 seconds (K23/N30) and 1.563/2.072 seconds (K64/N5). Rust is slower; the 10× target remains unproven. No scheduling/CPU-algebra/CUDA acceleration was implemented. Exact raw time/RSS/provenance is in bench/phase-1-benchmark.json.
- Review fixes protect input/output aliases, propagate final snapshot flush errors and warn on nonfinite initial/live model arrays. A shared rebuild invalidated an early concurrent test attempt; executable hash guards blocked mixed evidence. The final complete suite ran successfully against an immutable copy. Interrupted/superseded evidence is preserved and excluded from passing counts.
- Full final snapshots remain local; the compact package includes their hashes and reproducer, ordinary raw output, source, Linux binary and reports. Phase 0 archive/evidence remains retained.
- Next milestone: CPU workspace/memory engineering and deterministic scheduling while retaining the dense oracle. Real command/input/splitting/worker budget and reference-pathology interpretation are still outstanding. Later method changes and GPU promotion keep their own gates.

## Phase 2 authorization and working decision — 2026-10-10

The user said, "Great, let's start optimizing." This authorizes the next CPU engineering milestone. Retain the original dense HMM/model/optimizer and Phase 1 executable as oracles. Add a separate strict CPU backend with reusable message/model scratch, per-snapshot repeated-record caching, ordered reductions and a bounded independent-bootstrap runner. Do not change the model, optimizer, full-count Q, summation order, precision, observation boundaries or number of iterations. No CUDA or Phase 3 algebra in this milestone.

Parallelism across bootstrap fits is measured separately because the user's existing workflow already parallelizes. New external numerical dependencies are unnecessary. Use standard-library scoped threads, no nested pools. Add explicit estimated memory admission, seeds, ordered block indices and run statistics. Snapshots require all messages and therefore visibly bypass count-only caching while still running CPU workspace kernels.

The original Phase 1 math/validation sections remain historical; this authorization extends their exact comparison and finite/pathology policy to the new CPU backend. No tolerance is loosened. Performance promotion requires before/after measurements and all supported gates.

## Phase 2 completion — 2026-10-10

- Final Rust 0.2 executable fd866573…abb59a retains the unchanged dense HMM/model/optimizer and Phase 1 binary. Reusable HMM/model buffers, per-expectation exact-byte caching, borrowed bootstrap records and one bounded independent-fit pool preserve binary64 operation and contribution order. The optimized path is explicit `--backend cpu`; dense remains default.
- Both backends pass 113 inherited checks each. Six complete internal snapshot pairs compare 15,086 events and 4,371,374 finite numeric values exactly; 27 unit tests pass in debug and release. All 180 full fits across workers 1/2/4 and forward/reverse task order match C outputs and samples. Cache on/off and message-snapshot bypass, post-bootstrap random initialization and all 17 independent review controls pass.
- Cache totals: 11,730 visits, 7,740 evaluations and 3,990 hits per 30-fit batch (34.02%). No repeated statistical contribution is dropped. The same three reference pathologies remain classified separately; RI-only printed nonfinite diagnostics are now covered.
- Median complete-fit C/Phase1/CPU times are 0.385/0.486/0.306 seconds for K23/N30 and 1.581/2.106/1.391 seconds for K64/N5. CPU is 1.51–1.59× faster than Phase 1 and 1.14–1.26× faster than vanilla on these fixtures. K64/N5 is explicitly a partial trajectory.
- Equal-worker C/CPU 30-fit batch medians are 12.027/8.132, 6.088/4.003 and 3.124/2.081 seconds at 1/2/4 workers: 1.48–1.52×. These batches include 27 finite and three pathological outputs and describe execution mechanics. Ordinary concurrency is reported separately. Full-genome/real-workload/10× claims remain unsupported.
- Model scratch initially regressed; exact-length safe slices resolved it. Independent review fixed validation-before-truncation and expanded admission to include worst-case sampled indices and all retained metadata. Admission remains an estimate, not an OS memory cap, and follows input loading. Initial failures and exploratory timings are retained.
- Harness review added explicit checks for admitted workers, every C process exit and mutually exclusive benchmark selectors. Post-run audit confirms the measured invocation was unaffected: all 360 C child exits zero, all 12 Rust manifests use requested workers. Immutable measured runner/report retained. No production source changed after the final gate.
- Separate section timing puts M-step work at about 44–48% of optimized timed sections; HMM speed alone cannot establish 10×. Next permitted milestone: Phase 3 structured CPU/full-count algebra with independent numerical gates. CUDA, new input methods, checkpointing and production validation remain later work.
- Source, isolated derivations/tests/timings, final build and exact comparison evidence are delivered together in the Phase 2 archive. Phase 0 and Phase 1 archives remain unchanged; large full snapshots remain local with explicit omission hashes.

## Phase 3a authorization and resource policy — 2026-10-10

The user explicitly requested a comprehensive goal and implementation after the
SIMD discussion, adding: "keep it single threaded for now, I have other processes
using CPU." Build a strict SIMD milestone before structured algebra. No subagents,
concurrent jobs or parallel bootstrap measurements. Heavy commands and descendants
are pinned to one allowed logical CPU at reduced scheduling priority; Cargo jobs
and Rust test threads are one. All fits use one numerical thread and batch tests,
if run, use one worker. Shared-host timings are diagnostic and retain variation.

Preserve the dense oracle, Phase 2 binary and prior archives. Inspect existing
compiler vectorization first. Implement runtime-dispatched AVX on independent
count/destination lanes with scalar tails and fallback, preserving every lane's
binary64 operation order. Do not use FMA, horizontal reassociation, approximate
math, altered Q/log functions, structured recurrences, fewer iterations or GPU.
ARM NEON requires actual ARM validation and remains not_run in this milestone.

Acceptance requires isolated message/count bit comparisons (NaNs by class),
forced scalar/AVX and automatic selection controls, complete pinned-C trajectories
and all 30 existing bootstraps run sequentially, source/binary provenance,
single-thread before/after timings, documentation and a source/evidence commit
and package. Keep Phase 3's broader structured-algebra checkbox open.

## Phase 3a completion — 2026-10-10

- User-requested one-CPU resource policy honored for builds, tests and measurements: logical CPU 0, nice 10, Cargo jobs=1, Rust test threads=1, bootstrap workers=1. No subagents or parallel throughput tests.
- Version 0.3 adds private guarded AVX forward/backward/count lanes, scalar tails and runtime auto/off/avx selection. Every lane preserves binary64 operation order; no FMA, horizontal sum, reduced precision or changed Q/optimizer. Dense remains default; generic CPU and the exact Phase 2 binary remain available.
- All 340 differential controls pass, including 90 complete materialized bootstrap comparisons across dense/auto/generic paths. Ten complete snapshot pairs compare 37,789 events and 43,513,458 finite numeric fields exactly. Debug/release each pass 32 unit tests; 38 CLI selection/safety controls and 60 one-worker forward/reverse scheduler fits pass. Original nonfinite cases 16/26/28 remain separate from finite validation.
- Compiler inspection confirms existing Phase 2 SSE2 and new AVX instruction sites, with no FMA/horizontal adds in the specialized functions. Safe wrappers, tail remainders, unaligned slices, subnormals, signed zeros and nonfinite classes are tested. Absence-of-AVX selection is simulated in unit tests; ARM and physical no-AVX machines are not_run.
- Under shared-host contention, median child CPU-time speedups over preserved Phase 2 are 1.122× (K23/N30) and 1.312× (K64/N5). Both are about 1.47× versus vanilla in this run. K64/N5 remains a partial trajectory.
- Serial 30-fit batch result is neutral versus Phase 2: CPU ratio 1.005× with overlapping ranges, wall ratio 0.936× (slower median). No new bootstrap improvement is claimed. SIMD/vanilla ratio 1.634× CPU time largely retains existing Phase 2 gains. All measured output remains exact. Multiworker SIMD throughput is untested by user request.
- Separate E/M wall samples are too contention-sensitive for a precise new attribution; unchanged M-step varied substantially. Preserve these diagnostics and report ranges/CPU time rather than selecting favorable wall results. The source/derivation/tests/timings are committed together and the prior releases remain intact.
- Next permitted work remains real-workload profiling and Phase 3 structured/full-count/objective optimization with exact gates. SIMD does not establish the 10× objective.

## CPU optimization campaign — authorized goal, 2026-10-10

The user requested a comprehensive goal and strategy to maximize CPU optimization.
The previous one-CPU restriction remains in force. This is a campaign plan, not a
claim that any new implementation or benchmark has passed. Baseline: commit
`6a4d102` and the preserved Phase 3a executable. The active goal records the full
acceptance and completion contract.

### Resource and numerical contract

Heavy commands and descendants use one allowed logical CPU at reduced priority;
Cargo jobs, test threads and bootstrap workers remain one. No simultaneous heavy
jobs, subagents, multicore benchmarks or GPU work. Retain dense Rust and pinned C,
old archives and executable hashes. Preserve full binary64 precision, strict
operation/reduction order, optimizer callbacks and side effects, full counts and
Q normalizer, initialization, iterations, input boundaries, masks, sampling and
repeated-block multiplicity. No fast-math, approximate logarithms, fewer iterations,
changed optimizer or tolerance relaxation.

### Acceptance-gated work queue

- [x] Freeze Phase 3a inputs/binaries and obtain CPU-time attribution for messages,
  counts, model construction, Q/logarithms, preparation/cache, allocation and I/O;
  retain optimizer evaluation counts and shared-host variation. Estimate attainable
  whole-workload gains before choosing the first implementation.
- [x] Extend finite synthetic coverage across state sizes, sequence lengths,
  masking, repeated blocks and complete bootstrap trajectories. Retain all existing
  fixtures and nonfinite controls separately. Select fixtures by workload properties,
  not measured speed. Real workload validation remains pending user inputs/settings.
- [x] Optimize measured model/Q bottlenecks using exact invariant reuse and reduced
  repeated work, preserving every observable callback and live-model side effect.
- [x] Evaluate AVX register scheduling, independent-lane unrolling, count tiling,
  layout/preparation and allocation improvements while retaining each cell's
  original accumulation order. Profile again after each accepted change.
- [x] Evaluate compiler optimization level, LTO and profile-guided optimization
  sequentially. PGO training and held-out evaluation inputs must be distinct;
  every promoted build configuration must pass the complete numerical gate.
- [x] Derive and prototype structured message recurrences and factored objectives
  from actual C equations. Compare exact internal values and optimizer trajectories.
  Failed strict candidates remain isolated experiments; equivalent-mode promotion
  requires explicit review of a prespecified contract. Algebraic identity alone
  does not establish binary64 compatibility.
- [x] Assess long-record memory improvements: backward/count fusion and forward
  checkpoint/recompute. Preserve sequence boundaries, scaling, tiny initializers,
  per-cell addend order and message values. Measure RSS versus runtime and retain
  the existing path when strictness or useful performance cannot be established.
- [x] Run final sequential unit, isolated, pinned-C full-fit/snapshot, all 30 existing
  bootstrap, cache/scheduler and dispatch/safety gates. Run repeated uninstrumented
  comparisons against Phase 3a and vanilla; retain CPU/wall medians and ranges,
  RSS, exact output checks, fallback counts and all provenance.
- [x] Commit accepted source, derivations, tests and timings together; update the
  report and deliver a verified source/binary archive with prior releases intact.

The queue is reordered by profiling evidence, with one milestone in flight. A
candidate must demonstrate exactness and useful performance before promotion;
ambiguous timing is not a win. Kernel, complete-fit and bootstrap ratios are
reported separately. Reference pathology parity remains distinct from finite
scientific validation. Do not infer parallel throughput from serial measurements.

### Completion and stopping rule

Finish when the prioritized candidate classes have been accepted, rejected with
evidence, or explicitly deferred for unavailable data/hardware or an unapproved
numerical contract; quantify remaining bottlenecks and diminishing returns where
measurements permit. Deliver the fastest validated strict release within the
measured workload envelope. If nothing earns promotion, retain Phase 3a and deliver
the investigation evidence. No claim of a universal CPU optimum or 10x speedup is
implied. Real production validation, ARM/NEON, AVX-512 and physical no-AVX testing
remain pending suitable inputs/hardware; multicore and CUDA are outside this goal.

### Decisions and known uncertainties

- Prioritize model/objective work alongside profiling: SIMD improved finite
  unsplit fits but did not establish an incremental serial-bootstrap gain.
- Earlier M-step attribution motivates investigation, but the last shared-host
  wall samples cannot establish a reliable current fraction or speedup ceiling.
- Strict algebra may fail because floating-point grouping changes; do not silently
  substitute an equivalent numerical contract.
- Checkpointing may reduce memory while costing time; record that tradeoff rather
  than classifying every memory improvement as a speed improvement.

### Campaign progress — initial profiling and candidate screen

- Separate one-thread CPU instrumentation passes exact output checks against
  Phase 3a and vanilla. Hardware performance counters are blocked by the host;
  no global permission was changed. Q accounts for about 35–46% of instrumented
  main CPU time, model construction about 16–25%; timer overhead and allocation,
  cache and I/O residuals are explicitly reported, not hidden as precise attribution.
- Added 35 mixed/long/masked cases: all outputs exact, 9 finite (7 bootstraps),
  remaining cases retained as vanilla pathology controls. Added an independent
  PSMC-model-generated 100,000-bin fixture: unsplit and 29/30 bootstraps finite,
  all 31 outputs exact. Bootstrap 20's vanilla pathology remains recorded.
- Three strict Q experiments pass isolated controls and output screening but
  establish no consistent end-to-end benefit. Positional and direct-map log caches
  are not promoted; the flat-loop K64 result does not override K23 regressions.
- Compiler/LTO/PGO screen completed with independently generated training
  observations and 144 exact warmup/measured outputs. Shared-host ranges and
  inconsistent ratios support no promotion; original compiler settings remain.
  Broader internal gates are reserved for a candidate that earns promotion.
- Literal reconstruction of the 23-state C model is exact; the direct triangular
  factor rewrite changes 164 matrix entries, all three forward-vector comparisons
  and one normalized Q example. This strict counterexample keeps the formulation
  experimental; no tolerance is relaxed and no failed candidate is timed as a win.
- Production numerical source, delivered binary and previous releases are unchanged.
- See docs/cpu-campaign-progress.md for attribution, derivation links, counts,
  timing ratios, limits and remaining acceptance work. The full goal remains active.

### Campaign progress — SIMD, model reuse and memory

- Wide 8/16-destination kernels and ordered 64/256-site count tiles pass isolated
  and full-output screens. Tiles regress complete fits and are rejected. Generic
  unrolling has mixed results; separate fixed-64 message kernels demonstrate a
  repeated full-fit K64/N30 gain and proceed to final acceptance screening.
- Exact grid/lambda/tau model reuse passes isolated reuse/poison/nonfinite and
  output controls but offers no consistent whole-fit gain; neither cache is promoted.
- Masked tails pass lane and protected-page tests but regress whole-fit controls;
  retain the original scalar tails.
- Checkpoint/recompute preserves every regenerated message and ascending per-cell
  count order. Long-record RSS falls dramatically, at additional CPU cost. It
  remains a measured memory experiment, not a released CPU acceleration.
- Preparation plus workspace setup is at most about 1.1% in the diagnostic cases;
  main outside EM is at most about 0.94%. Further setup/I/O work is deprioritized
  within this synthetic envelope, without claiming precise per-allocation profiles.
- Full final gates, final uninstrumented timing, source commit and packaging remain
  outstanding. Candidate screens do not constitute release acceptance.

### Campaign acceptance — 0.3.1

- Accepted separate fixed-64 AVX message functions after 340 dense/CPU/scalar
  differential checks, 66 extended cases, 60 scheduler fits, 38 CLI controls and
  32 unit tests in each build mode. Ten snapshot pairs compare 43,513,458 finite
  fields and 37,789 ordered events with zero mismatches. The standalone K64 trace
  contains 36,956,397 finite fields. Signed zero and callback order remain exact.
- Final full K64/N30 CPU medians are 4.996 seconds for Phase 3a and 4.616 seconds
  for 0.3.1: 1.082x throughput, with separated ranges. Earlier balanced confirmation
  found 1.116x. K64/N5 is 1.155x but is explicitly a partial trajectory. K23 controls
  are effectively unchanged; the small 1.028x serial K23 batch change is not claimed
  as a reliable incremental bootstrap gain. Raw CPU/wall/RSS ranges remain visible.
- The original batch retains 27 finite and three pathological reference outputs;
  the 66 added cases retain 39 finite and 27 pathological outputs. Nonfinite parity
  is not valid inference. No seeds or measurements were discarded.
- Reprofiling shows Q/model/count work dominates. Full K64 message passes account
  for about 12.3% of diagnostic main CPU; instrumentation overhead prevents a
  precise uninstrumented ceiling. The explored exact alternatives did not improve
  full fits. Further tiny setup/I/O work is deferred pending larger real inputs.
- Hardware performance counters, actual user workloads/settings, ARM/NEON, AVX-512
  and physical no-AVX tests remain unavailable/not_run. Multicore and CUDA remain
  outside scope. Structured algebra requires a separately approved numerical
  contract after exact counterexamples; no tolerance has been relaxed.
- Delivery consistency audit passes; current executable SHA-256 is
  b0fc39d7c31637221de1152fc0d502bb65c90d0a5b9d6672250fe3117f75bfa4.
  Dense core, CPU workspace/cache and old release hashes remain unchanged.
- See docs/cpu-campaign-report.md for accepted/rejected decisions, complete
  measurements, remaining limits and reproduction. Accepted source/tests/timings are committed together as `7ee5271`;
  the portable archive passes CRC and every-member SHA-256 verification.


### Campaign completion audit

All campaign queue items are resolved: profiling and expanded fixtures completed;
separate fixed-64 AVX functions accepted; Q caches, model reuse, count tiles,
masked tails and compiler/PGO variants rejected with complete-fit evidence;
structured algebra quarantined by exact counterexamples; checkpointing retained
as a measured memory/CPU tradeoff outside the release. Final correctness,
scheduler/cache/dispatch, matched timing, reprofiling and delivery consistency
checks pass. No unexplored candidate is silently marked successful.

The accepted numerical source, isolated tests, derivation and timings share commit
`7ee5271`. The package contains the new executable, preserved prior binaries,
source, fixtures and reports, with all 18,952 initial members hash-verified.
Packaging metadata is committed separately and the final archive is regenerated
and reverified after this completion record. CHECKSUMS.sha256 covers every included
file except itself; the archive's sibling .sha256 records its final digest.
Old archives and all exact local snapshot streams remain intact.

Remaining items are explicit scope limits, not passed tests: real production
inputs/settings, physical ARM/NEON/AVX-512/no-AVX hardware, precise hardware-counter
attribution, and any alternative numerical contract. Future work starts with a
representative workload or such hardware/contract authorization; no 10x or
universal CPU optimum is asserted. Everything in this campaign used one allowed
CPU at reduced priority, one build/test/bootstrap worker and no subagents.

## Multicore bootstrap milestone — newly authorized 2026-10-10

The user now authorizes full-core parallel optimization, superseding the prior
one-CPU execution restriction for this milestone. Historical reports retain their
original one-CPU scope. Use the currently allowed CPU set, a bounded memory budget,
and independent replicate workers; no nested numerical pools or subagents.

- [x] Freeze 0.3.1 and compare worker scaling through all 16 allowed logical CPUs,
  including the 10-physical-core topology and matched parallel vanilla workloads.
- [x] Test deterministic heavy-first queue ordering based on bootstrap input work;
  preserve seed/index identity, original occurrence order and callback order.
  Keep rejected scheduling experiments out of the default release.
- [x] Validate all 30 original and 30 model-based bootstraps against pinned C at
  multiple worker counts/orderings, including cache-off/random-initialization and
  memory-admission controls. Preserve finite/pathology classifications.
- [x] Record wall/CPU time, sampled aggregate process RSS, actual worker admission,
  source/input hashes and shared-host variability. Distinguish scaling over serial
  Rust from advantage over already-parallel vanilla.
- [x] Commit source, proof/tests and timing evidence together; provide a measured
  full-core run configuration and verified package while preserving old artifacts.

Real user inputs remain unavailable. No scientific model changes, within-sequence
parallel reductions, tolerance changes, GPU work or hardware-affinity defaults
are implied by the new authorization.

### Progress, decisions and surprises

Scaling and paired vanilla comparisons complete: 16 workers were fastest observed,
with 7.29x/7.12x scaling over one-worker Rust and 1.73x/2.77x advantage over already
parallel vanilla on the original/model-based synthetic batches. All 3,600 timed
fit comparisons passed; all 60 distinct fits retain their C finite/pathology
classification (56 finite, four pathological).

The heavy-first candidate passes 300 additional seeded C comparisons, 33 debug
and 33 release unit tests, draw-order and memory controls. It is slower in all
four paired timing medians, so it is rejected and kept only as experimental
evidence. No production source or binary changes. Estimated unique input work
was not a useful queue priority on these workloads; the reason is not proven.

See docs/parallel-report.md for commands, hashes, CPU/wall/RSS ranges, validation,
limits and the 16-worker example. Full K64 parallel timings and production data
remain future work. Delivery integrity passes. The first separate package verified all 31,117 members
by CRC and SHA-256; old releases remain intact.

### Multicore delivery completion

Experimental source generator/test, derivation, validation and timings are
committed together in `65d1d87`. The unchanged production executable and all
source hashes pass bench/parallel_delivery_check.py. The milestone is complete: the
16-worker configuration is documented, the slower candidate is rejected, and
the distinct full-core package preserves prior archives. Packaging metadata and
this completion record are committed separately, then the final package is
regenerated and every member verified again. Its sibling .sha256 records the
final digest without a self-referential embedded archive hash.

## Public human PSMC test — authorized 2026-10-10

The user has no production file available and requests an HG test. Use the public
upstream NA12878 chromosome 22 PSMC fixture, pinned by source commit and SHA-256.
This is the complete supplied chromosome fixture, not an actual whole-genome
benchmark. Preserve encoded masks and document incomplete raw-calling provenance.
The separate prospective upstream GRCh38 acquisition manifest does not establish
provenance for this bundled test input. Keep downloaded input local and uncommitted.

- [x] Pin and inspect all input bytes; split with pinned C splitfa at an explicit
  50,000 bins so this chromosome has ten resampling blocks; retain every bin.
- [x] Compare a full unsplit 64-state, 30-iteration Rust fit with vanilla C.
- [x] Run all 30 fixed bootstraps, compare exact output and finite classification,
  and benchmark matched parallel C/Rust without dropping samples or rounds.
- [x] Screen worker counts, record elapsed/CPU/memory and profile a representative
  slow fit; retain all raw evidence and report limitations, hashes and commands.
- [x] Commit runners and measured evidence with a human-input milestone report.

No production numerical changes are planned before bottlenecks are measured.
Full-core authorization remains active; independent benchmark groups run serially.

Progress: all 508,185 supplied bins are retained (116,551 missing, 356,491
homozygous, 35,143 heterozygous). The unsplit full K64/N30 fit is finite and matches
C exactly except the version line: first observed wall times 58.22 s C and
18.15 s Rust. These are single-run pilot measurements, not repeated medians.
The 30-bootstrap matrix uses a 4096 MiB admission estimate so all 16 workers can
be admitted with these larger blocks. Eight- and ten-worker runs are exploratory
single screens; the repeated matched C/Rust comparison is fixed at 16 workers
with one warmup plus three measurements, retaining every seed.

Measured batch results: one warmup and three paired 16-worker measurements are
complete. Median wall time is 69.616 s Rust versus 255.305 s parallel vanilla
(3.667x); respective ranges are 66.840–70.179 and 252.131–257.880 s. All 30
canonical C bootstraps and all subsequent outputs are finite; 180 Rust outputs
match the 30 canonical C fits across 8/10/16-worker runs. Ninety repeated C outputs
also match. No underflow warnings occurred in completed batches. Exploratory
8/10-worker Rust batches took 79.213/73.814 s, using less CPU/RSS. Their single
screens do not establish a universal worker optimum.

Median sampled aggregate RSS is higher for Rust: 1,316,596 KiB versus 970,256 KiB
for parallel C. This is live-process RSS sampled every 20 ms, not physical PSS or
a hard memory cap. The result supports further allocation profiling. The release
binary and scientific/numerical source remain unchanged.

Completion: the source-verified diagnostic build matches C on both the unsplit
input and bootstrap 01 (selected by maximum optimizer evaluations). Expected
count accumulation is the largest measured exclusive section: 52.9% and 47.5%
of diagnostic main CPU time. Next permitted optimization: exact count-kernel
work plus measurement of workspace capacity/allocation, with full human and
existing synthetic/internal exactness gates and repeated whole-batch timings.

bench/hg_report.py rechecked all 270 subsequent outputs, the unsplit pair, both
diagnostic outputs, input/binary/source hashes, 30/30 finite bootstrap outcomes,
zero underflow warnings and timing summaries. bench/hg-delivery-check.json passes.
Runners, provenance, complete measured reports and docs/hg-benchmark-report.md are
committed together. The human fixture and materialized samples remain local under
ignored work/hg-input; ordinary raw results remain under ignored bench/hg. No
previous archive is replaced and no production source or executable is changed.
This completes the public human chromosome milestone; whole-genome and actual
user-workload claims remain untested.

## Ordered-count and workspace campaign — 2026-10-10 (complete)

User authorized continued optimization after the HG001 chromosome milestone.
One gated milestone: retain exact f64 site order while reducing transition-count
memory traffic, and prevent amortized message-buffer growth on unequal blocks.
Freeze v0.3.1 before experiments; retain all previous runners/results unchanged.

- [x] Build isolated memory-only, fixed K64, and register-blocked site-tile candidates.
- [x] Run isolated exactness tests and rotated complete human fit screens.
- [x] Measure any survivor against frozen v0.3.1 in complete 30-bootstrap batches.
- [x] Pass existing internal/C, pathological fixture, scalar/dense and scheduler gates.
- [x] Record derivation, timings, memory, source/binary hashes and limitations together.

Decision: each transition cell starts with its original tiny initializer and adds
sites in ascending order using exactly (f * ae) * b, then count + contribution.
Register tiles change traversal of independent cells only, never HMM boundaries,
model parameters, repeated-record weights, masking or optimizer behavior. Emission
counts and initial counts remain independent ordered operations. Allocation changes
preserve lengths, initialized values and lifetime of borrowed results.

Screen decision: all four candidate debug/release suites pass. All 20 full human
K64/N30 screen outputs are finite and exact versus retained C. Eight-site tiling
has the best repeated median and advances to complete gates; fixed K64 and
32-site tiling remain rejected screen candidates. The memory change is included
but its batch RSS benefit remains unproven until concurrent measurements.


Completion: v0.3.2 accepts the eight-site, sixteen-destination ordered K64 AVX
count kernel, plus exact-capacity growth. Human 30-bootstrap/16-worker matched
medians are 69.149560 s baseline and 50.154561 s candidate (27.469% less wall
time; 1.378729x throughput), with ranges 65.676700–69.909035 and
50.131555–52.940902 s. CPU medians fall from 905.708411 to 669.227921 s.
All three workloads have one warmup and three alternating measured pairs.

Surprise: lower Vec capacity did not lower sampled resident memory materially:
human RSS medians are 1,316,428 and 1,316,132 KiB. The standalone capacity replay
shows 51,201,024 versus 29,791,232 bytes per growing K64 message buffer, but this
is a capacity observation, not physical-memory usage. Exact reservation is kept
for its tighter capacity bound; no RSS or isolated CPU benefit is claimed. Growing
record lengths may require more reallocations; whole-genome behavior is untested.
K23 original/model-based batch wall medians are respectively 1.54%/3.37% slower,
with overlapping ranges and little change in CPU medians. No K23 speedup is claimed.

Acceptance: 35 debug and 35 release unit tests, 340 full dense/CPU/scalar cases
including exact internal snapshots, 66 extended cases (39 finite/27 pathological),
forward/reverse scheduler and cache controls, 38 CLI/dispatch checks, and no FMA
or horizontal reductions in assembly. All 720 timed batch outputs and two unsplit
human controls match retained C (version-only exclusion). All 240 human batch
outputs are finite; synthetic pathologies are retained. Every batch draw trace
matches independent original-sampler replay. bench/counts-delivery-check.json
rechecks all 722 outputs, current source/build hashes and published binaries.

Decision: promote the complete measured candidate as v0.3.2. bin/psmc-rs and
target/release/psmc-rs have SHA256
24d47084c2914aa44109040b7f5593efb7353621cb0d36ccdb28cd1a060f4c83.
bin/psmc-rs-v0.3.1 preserves the previous release; all previous archives and
reports remain unchanged. Source, isolated generator/tests, derivation, rejected
screens and before/after timings are committed together. The accepted source is
identified by complete build hashes in bench/counts-build.json and this milestone's
commit; the baseline is bdd1a4309502251f78ced5085f5d7aa498a200de. Raw evidence stays
locally under ignored work/counts-* and the existing validation directories.

Next permitted work: profile the accepted kernel on a larger documented public
workload before generalizing to whole-genome performance. The 10x target remains
unproven. ARM/NEON, GPU and the actual user's genome remain not_run. C output is
reused as an exact oracle; C timing is not repeated or newly claimed here.


## CPU headroom campaign — 2026-10-10 (complete)

Goal: finish an evidence-gated CPU campaign against frozen v0.3.2, with a fresh
profile, larger public human validation where obtainable, investigation of K23
controls, ordered-kernel experiments and renewed worker scaling. A measured
no-promotion outcome is valid; unmeasured speedups or a guaranteed 10x are not.
Baseline source: 4ab9ff5; executable SHA256
24d47084c2914aa44109040b7f5593efb7353621cb0d36ccdb28cd1a060f4c83,
frozen at work/cpu-next/baseline. Preserve previous reports and releases.

Plan and acceptance sequence:
- [x] Establish fresh v0.3.2 CPU attribution on full HG001 K64/N30 and K23 controls,
      using disposable instrumentation with outputs checked against pinned C.
- [x] Research a larger public human encoded PSMC input. Pin source, hash, license,
      encoding/missingness, original boundaries and fixed bootstrap procedure.
      No VCF reference imputation, whole-cohort downloads or private input uploads.
      Record any provenance/access limitation; duplicated chr22 is not a human genome.
- [x] Derive and build isolated ordered kernel candidates guided by the profile;
      include controls to distinguish allocation/dispatch effects in K23. Test
      finite bits, signed zero, nonfinite classes, tails, tile boundaries and reuse.
- [x] Screen complete N30 fits with fixed CPU affinity and rotated repeated runs.
      Validate held-out input before accepting a winner. Reject kernel-only gains
      that do not survive whole fits; keep all failed/rejected evidence.
- [x] Re-evaluate 8/10/16 workers (physical-core affinity where useful), then repeat
      best configurations. Keep independent groups sequential and count all 30
      replicates, every repeated block and all reference pathological outcomes.
- [x] Validate any final candidate through complete dense/CPU/scalar internal and
      C gates, extended fixtures, scheduler/cache and CLI checks. Audit assembly.
- [x] Run matched uninstrumented before/after complete batches, one warmup plus
      at least three alternating measurement pairs. Record wall/CPU/RSS, hashes,
      commands, ranges and limitations; confirm larger-input exactness if acquired.
- [x] Publish the measured decision, preserve binaries, commit source/proof/tests/
      timings together, and close the goal only after the delivery audit passes.

Decision: full-core authorization remains active for independent fits. Per-fit
arithmetic stays single-threaded, ordered f64. No model/optimizer/grid/iteration
changes, FMA, fast-math, dropped seeds/masks/duplicates or new HMM boundaries.
Do not rerun previously rejected compiler/cache/scheduler ideas without new
profile evidence. ARM/NEON and GPU remain untested on this x86-64 host.

Completion criterion: either promote a candidate with repeatable full-workload
benefit and all exactness gates, or document why the current release remains best
within the tested search. Larger data are an external availability dependency,
not permission to substitute undocumented or artificial whole-genome evidence.

Progress: the fresh profile passes all 12 C-output checks. Five isolated candidates
(count destinations 32/sites 8 or 4, message destinations 32, allocation control,
and outer count dispatch) pass debug/release suites before timing. No production
source has changed. Full-fit repeated screens are running on CPU 0.

Larger fixture: pinned GIAB HG002 GRCh38/NIST v4.2.1 VCF plus high-confidence BED,
with the upstream explicit homozygous-reference contract. Converted whole chr1
has 2,489,565 bins (N=307,821; T=2,038,125; K=143,619). A/M/N are state placeholders,
not reconstructed bases. The pinned C converter exactly matches independent
binning, including its partial-tail behavior. Raw files stay ignored locally.
Full fitting remains pending; this is not whole-genome validation.

Decision: advance combined 32-destination message/count kernels (eight count sites)
to final gates as a provisional v0.3.3 candidate. Confirmation medians: baseline
10.1171 s, messages-only 9.8745 s, combined 9.7782 s. All 12 confirmation fits
match C; combined suites pass. Baseline had one slower round, so final acceptance
still requires alternating complete batches. Allocation/dispatch remain unchanged.

Progress: provisional v0.3.3 (f0c3282e87e3eed0cc31c63a438429c19ad47cedec4c56c1150cc8520838e305)
passes 35 debug and 35 release tests; 340 dense/CPU/scalar full regression cases;
66 extended cases; ordered scheduler/cache checks; and 38 CLI checks. Assembly
contains 99 packed AVX arithmetic instructions, zero FMA and zero horizontal
reductions. Full original HG002 chr1 C/baseline/candidate fits are running next.
Fifty original 50,000-bin blocks and 30 seeds 20261101..20261130 are also pinned
for future HG002 bootstraps, explicitly prepared_not_fitted in this campaign.

Larger-input gate passed: complete original HG002 chr1 K64/N30 outputs are finite
and byte-exact to pinned C except version metadata for both v0.3.2 and the
provisional v0.3.3. Single descriptive times are C 272.762 s, baseline 69.434 s,
candidate 65.700 s; these are not repeated speed estimates. Rust peak RSS is
2,514,988/2,514,996 KiB. Neither a whole genome nor 30 HG002 fits is claimed.

Decision before seeing the final primary pair: the first two human pairs disagree
on wall and CPU direction (candidate wall +2.1% / -4.4%, CPU -3.3% / +2.9%).
Add exactly one confirmation block: one warmup plus three pairs with opposite
ordering. Pool all six measured pairs; retain every result. Do not keep sampling
until a favorable result appears. This extra block resolves a material uncertainty
rather than repeating an already-established performance result.

Confirmation acceptance rule, recorded before its measurements: promote only if
all exactness gates remain passed, pooled human median wall time improves by at
least 2%, pooled median CPU time improves, and at least four of six paired human
comparisons improve each metric. This is a practical release threshold, not a
statistical significance claim. The first three paired signs are 2/3 positive
for each metric. Otherwise retain v0.3.2 and commit the measured no-promotion
result with the larger fixture/provenance and all rejected candidate evidence.
No further performance repetitions will be selected based on the confirmation.

Completion decision: accept v0.3.3. The fixed confirmation passes the predeclared
rule: pooled human wall medians 51.288713 s baseline vs 50.218111 s candidate
(2.0874% lower, 1.02132x throughput); total CPU medians 674.952512 vs 655.978632 s
(2.8111% lower). Five of six paired comparisons improve each metric. Wall ranges
49.705025–53.185080 and 48.711773–51.697088 overlap; this is a modest measured
shared-host gain, not a formal significance or cross-machine guarantee.

Worker screen: paired mean seconds 59.1704 (8), 52.4418 (10 physical-core),
49.6976 (16). Fresh repeated confirmation uses 16 for both releases. Ten workers
use less total CPU time but take longer. K23 original/model-based wall medians
change by +0.90%/-0.36%, with overlapping ranges; no K23 gain or memory reduction
is claimed. The allocation/dispatch controls were rejected without production
changes. No new scheduling behavior is introduced.

All 960 primary/confirmation batch outputs and 180 worker-screen outputs match
retained C, with independently replayed bootstrap draws; all 480 human batch
outputs are finite. All synthetic reference pathologies remain. Two unsplit
HG001 controls and the larger HG002 controls also pass. The delivery audit
regenerates all six isolated candidate sources and rechecks 1,241 outputs.
Published bin/psmc-rs and target/release/psmc-rs are
f0c3282e87e3eed0cc31c63a438429c19ad47cedec4c56c1150cc8520838e305;
bin/psmc-rs-v0.3.2 preserves the previous executable. Previous reports/archives
remain unchanged. docs/cpu-next-optimization.md and bench/cpu-next-*.json retain
source hashes, actual commands, all timings, rejected candidates and limitations.

Next permitted milestone: whole-genome/user-workload validation and fresh
profiling before another CPU campaign. ARM/NEON, GPU and actual user data remain
not_run. The prepared HG002 bootstrap samples are not fitted; no whole-genome or
10x claim is made. This bounded campaign is complete; no further repetitions are
selected to improve its result.

## Optional CUDA feasibility milestone — 2026-10-10

User explicitly authorized a new goal and implementation. Baseline is v0.3.3,
commit 0905ea0, preserved as bin/psmc-rs-v0.3.3. CPU-only behavior stays available.

Plan and acceptance rule (recorded before GPU measurements):
- [x] Reprofile v0.3.3, pin GPU/compiler/driver/source and benchmark inputs.
- [x] Build an optional runtime-loaded CUDA count backend; isolate unsafe FFI,
      preserve every ascending count addition and multiply grouping, no FMA.
      Bound device buffers by computational site tiles, carrying count sums.
- [x] Test counts against dense/CPU at boundaries, masks, pathological values,
      arbitrary state sizes, repeated records and changing parameters.
- [x] Screen realistic counts including transfers. Only if promising, investigate
      resident forward/backward plus counts; record a negative result honestly.
- [x] Validate complete fits and ordered internal snapshots against pinned C,
      HG001/HG002 N30 and 30 fixed HG001 bootstrap replicates. Verify CPU builds
      with no CUDA installed, runtime errors, cache/memory/scheduler behavior.
- [x] Compare complete 30-bootstrap throughput with 16-worker CPU. Screen GPU
      worker counts before fixed alternating measurements (warmup + three pairs).
      Promote only with all exactness gates and >=5% median end-to-end improvement,
      with >=2/3 pairs faster; otherwise retain explicit experimental opt-in.
- [x] Document commands, hashes, timings, memory, failures, unsupported hardware,
      next milestone; commit implementation, proof, tests and measured decision.

Decisions: CUDA is optional behind a Cargo feature and explicit backend selection.
Linux runtime loading permits CPU-only compilation without CUDA headers/libraries.
Reuse the locally installed NVRTC if compatible; no new downloaded dependency.
Model construction, libm/log-likelihood, optimizer and record aggregation stay CPU.
GPU memory failures are explicit errors, never silent approximate substitutions.
The compatibility contract remains exact finite bits plus nonfinite class parity.

CUDA progress: optional runtime-loaded NVRTC 12.9 / CUDA Driver backend now
computes ordered transition counts. CPU messages and initial/emission counts
remain, with a separate GPU-buffer budget bounding bootstrap worker admission.
Unit gates include shapes 1..129, tile tails, masks, exact parameter changes,
repeated-record multiplicity, explicit nonfused PTX and concurrent uploads.

Surprise and repair: initial broader gate failed bootstrap 24 and 26 although
small tests and four internal snapshots passed. Pageable HtoD uploads on the
legacy default stream lacked a dependency before a nonblocking compute stream.
Explicit upload-stream completion now precedes launch. Both failing full N30
cases pass three repeated checks after repair. The original failed report and
initial timings remain archived; initial timings do not support acceptance.
The old harness's reject_cuda_backend case also fails by design for a CUDA build;
its replacement checks CPU-build rejection and CUDA runtime/argument errors.

Resident-message decision: an isolated strict CUDA F/B prototype exactly matches
all messages and scales for 257 and 50,001 sites. At 50,001 sites its kernels take
0.503 s versus 0.0364 s for CPU messages plus emission counts. This one-record
persistent-block design is rejected before production integration. It does not
prove every possible batched GPU message design is slow. Focus this milestone
on the hybrid count backend and complete-workload go/no-go evidence.


CUDA completion decision: retain experimental opt-in v0.4.0 and keep v0.3.3 CPU
recommended. All 113 C gates, 39,142,084 finite snapshot values, 35 existing plus
five CUDA release tests, 66 extended fixtures, 360 human batch outputs, unsplit
HG001/HG002 and nine error/scheduler controls pass. Missing hardware tests in the
default suite are explicitly ignored and separately executed on the actual GPU.
The final audit passes and the existing CPU executable is unchanged.

Fixed paired batch medians: CPU 49.562635 s vs CUDA
64.024233 s (29.18% longer CUDA); aggregate CPU time
650.06 vs 517.96 s (20.32% less CUDA).
GPU wins 0/3 pairs, so performance promotion is rejected without more timing
repetitions. Both selected configurations use 16 workers. The optional backend
is functional and exact on the tested stack; it is not a whole-GPU inference
implementation or a speedup claim. docs/cuda-report.md records all results,
limitations, commands, repaired failures and the next possible experiment.

## Remaining optimization exhaustion campaign — 2026-10-10

Explicit user request: exhaust optimization opportunities before release/reliability
work. This is a bounded, evidence-based search on the available machine, not a
proof about every possible algorithm, compiler or future hardware.

- [x] Inventory prior candidates, inspect current hotspots, and profile HG002 chr1.
- [x] Screen additional ordered CPU count tiles and joint-source SIMD reuse.
- [x] Probe CUDA stream-local pinned transfers, launch geometry and tile size;
      assess independent-record overlap only if the measured bounds justify it.
- [x] Investigate workload ordering and heterogeneous-core scheduling using all
      30 unchanged HG001 seeds; inspect scaling/limits on the larger input.
- [x] Revisit model/Q/compiler work only with a specific new mechanism or evidence.
- [x] Confirm promising combined candidates on complete workloads and held-out
      inputs, then run exact internal/C regressions for any production change.
- [x] Publish the opportunity ledger, reproducible outcomes, limitations, optimized
      deliverable or measured no-change decision, and commit before completion.

Decision before new timings: candidate screens use fixed repetitions (one warmup
and three measured rotations for complete single fits). Promotion requires all
exactness gates, >=2% lower median full 30-bootstrap wall time, lower median CPU
time, and >=2/3 faster alternating pairs following one warmup per configuration.
No optional repetitions to rescue a failed result. GPU promotion additionally
requires >=5% wall improvement versus the recommended CPU. Retain rejected
prototypes and failed tests in separate evidence. Large HG002 timings are a
held-out control; do not claim whole-genome results. Per-cell arithmetic and
per-fit record aggregation remain ordered. No approximate mode is authorized.

Progress: six initial CPU variants pass release differential units and 56 full
C-output screens. Best initial HG001 median is 9.6429s (joint two-source,
16-destination, 16-site counts) versus 10.0942s current-source CPU control.
Two exact HG002 profiles attribute ~44.5% to transition counts, ~25.2% forward,
~21.5% backward, ~4.1% other counts, and ~3.3% model/Q. Larger count tiles and
joint-source refinements are being measured with a fixed local search.

The additional full-fit screen passes 48 C comparisons. Explicit AVX forward
normalization improves K64 timing (9.6718s vs 10.1560s control); smaller-state
results do not justify extending the dispatch, so combined candidates will use
this only for K64. Native target codegen does not improve the main workload.
Full-model/Q memoization regresses K23 by 8–10% and adds memory; reject it for
production. Retained C traces have only 0.8–3.4% repeated parameter evaluations,
with no immediately repeated callbacks in the inspected traces.

Four CUDA pinned/stream-local variants pass all five hardware unit tests each,
including concurrency, tile boundaries, signed-zero/subnormal/nonfinite and PTX
checks. Their full-fit and complete-batch performance remains pending. Production
numerical source and published binaries remain unchanged during the screens.

Progress: retain the existing 16-worker CPU policy. Both complete 30-fit scheduling
rotations favor all 16 logical CPUs (49.34/49.88s); P-core-only and physical-only
controls are slower. All 300 outputs match C with original bootstrap draws.
The refined CPU tile gain is only ~0.8%, substantially below the initial screen.
Combined K64 normalization/joint-source/emission-tile fusion is the provisional
CPU candidate: full-fit median 9.7719s vs 10.0563s control; all screened outputs
and the new direct IEEE/tile/missing/final-site-omission tests pass. Manual source
unrolling regresses performance and is rejected. Provisional v0.4.1 source is
staged in the working tree for final gates; installed binaries remain unchanged.

GPU resident-message batching is exact for 1/8/16/32 records, but GPU kernels alone
remain ~0.62s; the matching 32-record CPU control is ~0.22s including emission
counts. A higher-occupancy 128-record control will bound that design further.
Stream-local pinned transfers fail the single-fit speed screen. Complete GPU
batches now test those variants, larger tiles, record lookahead, and CPU wait
policies. Yielding/blocking is a newly identified mechanism because default CUDA
synchronization may actively spin on a CPU core. Mixed CPU/GPU job allocation is
also tested explicitly; no backend switch is a failure fallback.

Search boundary: no new candidate families after the already prepared two/four-cell
CUDA kernels, 128-record occupancy control, and mixed-device batches. These close
the identified CPU/GPU mechanisms. Only a clearly promising measured combination
may receive one fixed follow-up screen before the predeclared acceptance gate.
This is an engineering exhaustion criterion for current hardware/strict arithmetic,
not a proof about every possible future algorithm or parameter combination.

Current GPU batch screens: CPU 48.95s, original CUDA 70.41s, pinned/stream variants
65.51–66.95s, large original tile 64.90s, record lookahead 71.07s or 62.83s with a
large tile, yielding waits 71.89s. All outputs remain exact. No GPU speed promotion
is justified by these screens. Blocking-wait and mixed-device results are pending.

One combined-device follow-up is predeclared before examining mixed-batch results:
blocking waits cut aggregate CUDA CPU use from 531.5s to 365.85s, despite remaining
slower in wall time (67.05s). Combine that CPU-resource saving with large-tile record
lookahead and the provisional CPU kernel, and screen fixed GPU job counts 0/8/15/30
once each. This explicitly tests whether CPU work can use the freed capacity.
No further combination families will be added. Any promotion still requires fresh
complete paired measurements against the fastest accepted CPU configuration.

Final search outcomes: the frozen v0.4.1 CPU candidate passes all three measured
30-bootstrap pairs: median 47.0875s vs 50.1408s, 6.09% less elapsed time and 6.71%
less aggregate CPU time, essentially unchanged RSS. All 240 outputs/draws match
C. Broader compatibility gates are running before installation.

The remaining GPU screens are rejected for speed. Two/four cells per thread take
66.45/67.23s vs CPU 48.90s. At 128 independent records, resident GPU messages take
0.908s in kernels alone vs CPU 0.611/0.635s with 10/16 workers. The combined
blocking/large-tile/lookahead prototype with 0/8/15/30 GPU jobs takes
46.41/45.70/53.38/61.60s. The best difference is 1.53%, below the 5% promotion
threshold; larger GPU shares save CPU consumption but increase elapsed time.
No more candidate families or optional timing repetitions will be added.

Completion: v0.4.1 passes 39 debug and 43 release unit tests (including all hardware
CUDA tests in release), 340 C regressions, ten ordered internal traces, 66 extended
fixtures, eight full human C-output controls, 60 synthetic scheduler fits and two
optional-CUDA full human controls. HG001/HG002 continuous-input two-pair means
improve 4.62%/8.40%; the primary 30-bootstrap gate remains the release decision.
The final audit rechecks 204 single-fit screen outputs and 1,230 full human batch
outputs/draws across 41 batches. No numerical mismatches occur.

Installed the frozen CPU v0.4.1 as bin/psmc-rs and bin/psmc-rs-v0.4.1; retained
v0.3.3. Updated the optional CUDA executable only for shared CPU normalization
and version text, preserving the original v0.4.0 binary; no experimental GPU
optimization is promoted. Full provenance is in bench/exhaust-audit.json and
bench/exhaust-install.json. docs/optimization-exhaustion.md closes the ledger.
All credible identified opportunities are implemented, measured/rejected or
bounded by explicit exactness/hardware/data constraints. Source, derivations,
tests and timings are committed together. Broader input validation/reliability
is the next permitted milestone; no new optimization family is left pending.


## Significant-optimization second look — 2026-10-10

The user explicitly reopens optimization after the completed campaign. Baseline
is clean commit 30efe0b and installed CPU v0.4.1; previous reports stay unchanged.

- [x] Inspect current code and prior exclusions for a distinct high-impact mechanism.
- [x] Measure exact message repetition and homogeneous-symbol runs on complete HG fits.
- [x] Prototype only mechanisms supported by that evidence; preserve every ordered
      per-cell addition, intermediate multiplication, boundary and optimizer call.
- [x] Screen complete fits with one warmup and three rotated measurements; a
      significant candidate must show at least 5% median full-batch wall reduction,
      lower aggregate CPU time and at least two of three faster fixed paired batches
      against v0.4.1. No optional timing repetitions to rescue a failed candidate.
- [x] Run full compatibility gates before any promotion; document a measured no-change
      conclusion if no candidate earns promotion, then commit the new evidence.

New hypotheses: exact (bitwise, not approximate) fixed points in forward/backward
messages may eliminate redundant matrix-vector evaluations within homogeneous
stretches. First measure frequency before introducing a path. Separately, a run
or uniform-tile count kernel can hoist unchanged emission-transition coefficients
while retaining all site additions in original order. This is distinct from the
previous tile-width/source-unrolling search. No lower precision, tree reduction,
new model, stopping tolerance, cross-fit count cache or GPU retry is authorized.

Predeclared full-batch screen: each uniform-coefficient variant once, between two
installed v0.4.1 controls, with all 30 unchanged seeds and 16 workers. Select only
a candidate with at least a 2% screen reduction and lower aggregate CPU time for
fresh fixed acceptance pairs; the significant-improvement acceptance bar remains
5%. A separate diagnostic full batch measures repetition across all 30 fits;
its instrumented elapsed time is not a performance result.

One final distinct mechanism is tested before closing this second look: collect
the same ascending forward scaling sum inside the K64 message kernel after each
32-state output group, then perform the original vector divisions. This lets the
processor overlap the first group's ordered scalar additions with independent
work on the next group and removes a separate normalization call. No sum is
reassociated. Screen one isolated candidate plus installed control; combine with
the count candidate only if each independently shows useful complete-fit or
full-batch gains. No further candidate families will be added in this second look.

The repetition diagnostic also samples short cycles (lags 2/3/4/8/16/32/64) at
every 64th interior site across complete HG001/HG002 fits. Adjacent equality alone
cannot reject periodic recurrence reuse. Homogeneous spans and full finite row-bit
equality are required; backward row equality remains only an upper bound pending
matching scale phases. This extends the existing repetition hypothesis rather
than introducing an approximate convergence test.

Audit-driven scope adjustment before further timing: the prior Q report contains
an overlooked 1.150x K64 flat-loop screen, rejected because K23 regressed. That is
concrete evidence for a K64-only objective dispatch, leaving other shapes on the
unchanged oracle path, with no log cache or RefCell. Test this focused variant;
it overrides the just-recorded family limit because the audit found a specific
untested way to address the earlier rejection. It does not repeat general log
caching. Any combined candidate still needs the same fresh 5% batch gate.

A forward-generator suffix assertion stopped before compilation because the
function ends in one newline rather than two. Preserved the untouched scratch
source and recorded the repair in bench/relook-repairs.json. No numerical gate
was relaxed and no numerical mismatch occurred.

Candidate selection: uniformwide takes 43.1824s versus surrounding installed
controls 44.5376/45.4638s (4.04% below their mean), with 4.32% less CPU time.
Uniform16 has essentially no batch elapsed gain; uniform64 raises CPU time.
Forward fusion yields only 0.61% on the full single fit; K64-guarded flat Q yields
0.34% and its K23 control regresses 4.86%. Do not combine or promote those paths.
Short-cycle/history probes find essentially no repetitions on HG002; HG001's
additional cycle coverage is small. Reject numerical recurrence reuse as a
significant general route on these measured inputs.

Provisional v0.4.2 contains only the wider homogeneous-coefficient count path and
its tests; installed v0.4.1 stays untouched. Freeze this reviewable final candidate,
then run the predeclared complete-batch acceptance. Reject and restore production
source if the 5% significance gate fails; no extra repetitions will rescue it.

Second-look completion: the frozen candidate passes 41 debug tests and all 45
release tests including hardware CUDA checks. Fixed complete-batch acceptance
finds 46.2849s installed median versus 45.3934s candidate, a 1.93% reduction;
aggregate CPU falls 3.14%, with two of three faster pairs and overlapping ranges.
This fails the predeclared 5% significance gate. No additional repetition or
combined candidate is used to rescue the result.

Retained v0.4.1. Restored only the four provisional production files and rebuilt
the ordinary target; source/configuration and installed/rebuilt binary hashes
match the original release exactly. The 340-case promotion regression was not
rerun because this candidate did not pass performance admission. The final audit
rechecks all 496 C-output comparisons and all batch draws, reproduces the frozen
candidate sources exactly, and verifies the no-change decision. There are no
numerical mismatches; the single generator assertion repair is preserved.

The opportunity assessment and all outcomes are in
docs/significant-optimization-recheck.md. Evidence, runners and derivations are
committed together. No candidate or run remains pending for this second look;
no claim of global optimality or untested-hardware performance is made.

## Structured equivalent mode — 2026-10-10

User explicitly authorizes building and validating structured mode while keeping
strict available. Preserve pre-existing user edits: CPU default, package-derived
version text and C golden tests. Contract and predeclared gates are in
`docs/equivalent-mode.md`; the strict contract remains unchanged.

- [x] Implement guarded structured model, messages and Q with original full counts.
- [x] Validate isolated algebra, invalid-candidate recovery and strict regressions.
- [x] Measure the two selected C builds on HG001/HG002 and paired bootstrap samples (resource amendment below).
- [x] Measure full equivalent fits and fixed paired throughput; publish limitations.

Decision: retain full transition counts and the full Q normalizer. Triangular
margins do not determine the entropy of the full expected-count matrix. Thus the
initial structured E-step still has quadratic count work. Factor positivity is
checked rather than assumed; diagnostic snapshots reject equivalent mode initially.

Progress: implemented opt-in equivalent CPU factors, linear forward/backward scans,
linear candidate model/Q, full optimized transition counts, matrix synchronization
before output, factor eligibility checks and literal fallback counters. Component
coverage spans 2–64 states, masks, short records, explicit times, divergence,
cache multiplicity and invalid candidate recovery; a 300-candidate parameter sweep
passes the declared model/Q tolerance. Strict golden and mode CLI tests pass.

Surprises: C compilation first failed because system zlib headers are absent;
reused the already-extracted local headers and runtime library, retaining the
failed log. The historical strict validation runner requires CPU pinning; its
first unpinned invocation exited before tests and was rerun pinned. Its old
CPU `reject_equivalent_mode` availability check is now obsolete and will be
reported separately, not classified as a numerical regression.

Preliminary full fits: original HG001 curve max difference ~1.53e-5 log units,
but bootstrap 13 changes its earliest grouped lambda from 845981 to 657562,
a ~22% difference (0.252 log units), despite very close theta/rho/likelihood.
This fails the predeclared exploratory curve screen. Do not relax the threshold
or claim scientific equivalence; retain opt-in experimental status while completing
the compiler-sensitivity, held-out HG002 and performance measurements.

Completed Rust validation: all original and 30 paired bootstrap fits for HG001 and
HG002 in both modes (124 fits), plus 24 scheduling/cache control fits. HG002 maximum
bootstrap curve change is ~0.001057 log units (~0.11%); the HG001 outlier persists.
The strict regression has 338 passes and exactly two obsolete CPU availability
rejections; all ten internal traces remain exact, with the original 27 finite /
3 pathological synthetic bootstrap classification on all strict backends.

A further same-parameter diagnostic checks 186 printed human-fit parameter
snapshots on a synthetic 2048-bin sequence, including the sensitive replicate.
All transition, message, count and Q comparisons pass the predeclared tolerances;
maximum relative Q error is 2.22e-13. No tolerance has been changed.

Resource amendment: chose the explicitly authorized two-build C sensitivity panel
(O2 contraction-off versus O2 native/FMA, 0 versus 15 verified FMA instructions).
Stopped the additional O0 HG001 diagnostic before completion and retained its
partial output. Full selected-build fit sizes and 30 bootstraps remain unchanged.
The initial baseline script and failed-header logs remain preserved; the resumption
runner avoids rerunning completed controls. This does not rescue any failed gate.

All 124 selected C sensitivity fits are complete. All 62 strict human outputs
match standard C exactly outside the version line. Final high-precision parameter
analysis: HG001 passes 27/31 exploratory screens and HG002 passes 31/31; only
7/31 and 6/31 meet every per-fit compiler-envelope criterion. Maximum curve
errors are 0.251957 and 0.001057 log units. Maximum error relative to pointwise
bootstrap SD is 5.18% and 0.0694%; no numerical-equivalence qualification.

Benchmark repair: the first attempt stopped during its first strict warmup when
the immutable-binary hash guard fired. GNU objcopy rewrites its input ELF when no
separate output file is given, even for --dump-section. Its machine-code sections
matched, but the container bytes changed. Preserved the attempt and rewritten
executables, restored the tested archive from the hash-matching strict regression
freeze, and rebuilt the target. The checker now supplies a distinct output ELF
and verifies the input hash remains unchanged. Restarted the fixed warmup/three-
pair protocol; no measured pairs had run, and no thresholds changed. Details are
in bench/equivalent-repairs.json.

Completion: fixed performance gate passes with 45.2498s strict versus 32.7541s
structured medians (1.3815x; 27.6% less wall and 30.0% less CPU), three of three
pair wins and similar ~1.25 GiB RSS. The v0.4.1 controls, 43.97/47.30s, overlap
new strict timings. All 300 acceptance/control outputs reproduce validated
numerical results and all mode-pair draws are independently replayed.

Final audit passes: 45 debug and 45 release tests (four GPU hardware tests not run),
338 applicable strict checks, ten exact traces, 62 exact C/strict human outputs,
124 Rust human fits, 24 scheduling controls and 186 trajectory component probes.
C sources/headers match the original pinned archive. Added a pinned GitHub Actions
workflow for fresh-C/golden/Rust checks; its four live-C cases pass locally.
Hosted CI is not run because no Git remote is configured.

Installed CPU v0.5.0 with the user's CPU default and strict numerical default;
preserved CPU v0.4.1 and the optional CUDA binary. Equivalent remains explicitly
experimental because its full-fit numerical gates fail. docs/equivalent-mode-report.md
and bench/equivalent-audit.json record the complete results. No inference jobs or
candidate experiments remain pending. Next permitted work is a separately justified
scientific-equivalence contract or broader validation; no default-mode switch is
justified by this milestone.

## Structured follow-up — user review, 2026-10-10

The user requests reconsidering numerical gates, diagnosing HG001 bootstrap 13,
lockstep SIMD across independent records, and fixing parameter coupling/counters/
scan allocation. Preserve historical reports and strict mode.

- [x] Reproduce distribution summaries and evaluate final likelihoods and common-count Q for bootstrap 13.
- [x] Make factor ownership explicit; correct update counters; reuse scan storage.
- [x] Implement four independent equal-length records per AVX vector, preserving scalar structured operation order and full counts/QD.
- [x] Differential tests, full paired human fits, and measured performance decision.

Decision before measurement: retain full entropy/QD in this milestone. q0 is
subtracted inside every optimizer comparison; dropping it is mathematically a
constant shift but changes binary64 ties. A margins-only backend is a separate
contract change, requiring eligibility/fallback design when factors are invalid.
Do not compare Q from different E-step posteriors as evidence of equal fits.
Use freshly evaluated observed likelihood and both candidate Q values on each
fixed expected-count matrix. Printed parameter precision is an explicit limitation.

The old 0.01 screen also rejects four vanilla-C HG001 fits. The per-fit compiler
envelope is descriptive, not a calibrated scientific equivalence test. Preserve
its failed results without interpreting them as proof of incorrect inference.
Distribution summaries and bootstrap-relative errors provide context; a new
scientific qualification must not be inferred from this already-inspected panel.

SIMD admission: require exact equality to scalar structured messages/counts and
old equivalent fit outputs (version metadata excluded), including masks, tails,
duplicates, cache off and observer bypass. Screen one full HG001 bootstrap batch
against installed v0.5.0, then freeze candidate and run one warmup plus three
alternating measured pairs, 16 workers, same inputs/options/draws. Promotion needs
>=5% median wall reduction and at least 2/3 pair wins; retain a slower SIMD path
only as a documented rejected experiment, not as the installed default.

First SIMD screen: four full interleaved histories exactly reproduce all 30
HG001 outputs and bootstrap draws, but take 54.06s versus 33.13s installed, with
RSS 4.43 versus 1.25 GiB. Reject this memory layout. Preserve candidate patch,
binary and runner in work/equivalent-followup/full-buffer-candidate. A second
specific candidate replaces the full histories with checkpoints and small
reconstructed blocks. Its arithmetic and count accumulation must remain exact;
use a fresh screen, then the same fixed acceptance protocol if admitted.

Bounded candidate screen: 31.7766s versus 34.2884s (7.33% less wall), CPU
388.85s versus 437.25s, RSS 1,070,032 versus 1,259,380 KiB. All 30 exact outputs
and draw sequences pass. Admit the bounded candidate to complete validation and
the previously declared fixed acceptance protocol. Provisional v0.5.1 adds no
new scientific-equivalence tolerance and keeps strict as default.

Numerical review reproduces all user medians/exceedance counts. A fresh strict
CPU re-evaluation of printed bootstrap-13 endpoint parameters gives LL delta
-0.00026635 and common-count Q deltas around -0.00018. Varying only the first
group's lambda changes LL by at most 2.59e-6 across the reported range, supporting
weak identification. No assertion of a global optimum or scientific equivalence.
Historical engineering gates remain recorded, with their limited interpretation
corrected in the report.

Completion: bounded lockstep passes the fixed acceptance, 34.9002s old versus
32.1995s new medians (7.74% lower wall, 8.03% lower CPU, 18.16% lower RSS), three
of three pair wins. Strict controls 49.259/47.228s do not show a regression but
are not a standalone speed claim. All 62 structured human outputs are identical
to v0.5.0 outside the version line. The audit verifies 510 bootstrap outputs,
338 applicable strict checks, ten exact traces, 47 full-workspace release tests
and final CPU message/count tests (24 debug/23 release). Four CUDA hardware tests
and ARM/NEON are not run. Counters remove 900 E-step refreshes per 30-fit dataset.

Promote v0.5.1 in the opt-in equivalent mode, preserving strict as default, the
full Q normalizer and all earlier binaries/evidence. Updated README and reports
correct the interpretation of the original numerical screens. No retrospective
scientific-equivalence threshold is adopted. Next milestone is margins-only
counts with an explicit objective-diagnostic contract and invalid-factor fallback.
No further optimization candidate or inference job is pending for this follow-up.

## Linear E-step milestone (in progress)

User-authorized priorities: segmented within-record SIMD and margins-only counts
with QU together, then deterministic shared record scheduling separately. No GPU,
reduced precision, changed observation boundaries or reduced iteration budget.

Decisions: predeclared C-calibrated distribution limits and 10% bootstrap-SD
budget in docs/linear-equivalent.md before running candidate fits. Both existing
C compiler panels pass. Strict remains the default. Valid literal fallbacks
reconstruct full counts lazily from the same frozen E-step posterior; invalid
candidates retain literal sentinel/NaN behavior. QU consistently omits the entropy
constant, including fallback. Observer diagnostics retain full-count evaluation.

Surprises: the first scalar surrounding loops hid nearly all scan gains; explicit
AVX normalization, emission and margin updates reduced the HG001 five-round
E-step screen from 1.90s to 0.52s. This screen is not the paired batch acceptance.
The supplied scratchpad prototype was not present in the available workspace or
Downloads; the implementation was independently derived and tested against the
retained dense/structured paths. Numerical validation and paired timing ongoing.

Linear milestone completion (9d1e89c): 62 equivalent fits passed the prospective
engineering gate and sample-13 ridge diagnostic; strict human originals plus
30 HG001 fits remained exact. Release 49 tests/CPU debug 26 passed, CUDA hardware
not_run. Paired batch medians 35.031s versus 11.310s, 67.71% reduction, three wins.
Installed v0.6.0 with strict default and preserved earlier binaries.

Shared record scheduling milestone in progress: fixed cooperative worker queue,
ordered results, optional single-fit record workers and Linux affinity confined
to inherited allowed CPUs. Predeclared exactness/performance gates are in
`docs/shared-record-scheduling.md`; measure rather than assume hybrid-core gains.

Shared-record milestone complete: final medians 10.047 → 9.477s equivalent
(5.67%) and 46.473 → 44.024s strict (5.27%), three favorable pairs in each mode.
Both improvement and non-regression gates pass. Earlier screens and paired
results are preserved, including the earlier equivalent 4.55% gate miss. Final
review corrected admission accounting for owned input copies and all uncached
result slots, then repeated human validation and timing on the final binary.
The audit verifies 570 human outputs, 32 synthetic comparisons, two single-fit
comparisons, 52 release/27 CPU debug tests, plus 338 applicable pinned-C checks
and ten traces on the identical arithmetic source before the admission-only fix.
Two obsolete equivalent-rejection checks remain explicit in the historical raw
regression status. Four CUDA tests, non-Linux/ARM hardware and hosted CI not_run.

Installed v0.6.1 with shared CPU batch scheduling, strict numerical default and
optional --record-workers for multi-record single fits. QU remains exclusive to
equivalent mode. Versions 0.6.0 and earlier are preserved. No inference jobs or
required checks remain for this milestone. Future tuning should profile the now
larger M-step share; neither global scientific equivalence nor CPU exhaustion
is claimed from these two chromosome panels.

## Qualification transition — user review after v0.6.1

Progress: fix Linux core classification and automatic single-fit CPU workers;
rewrite usage documentation; run a prospectively specified known-truth pilot;
archive ignored evidence with byte verification; publish CI when a remote is supplied.

Decisions: prefer disjoint, complete Linux hybrid PMU CPU lists within inherited
affinity; otherwise use >=85% maximum frequency, and retain unpinned fallback
when unknown. Automatic record workers apply only to ordinary single CPU fits;
explicit counts remain validated. Strict memory scales with concurrent records.
Keep strict the default numerical mode. No more speed campaign is planned.

Surprises: historical raw evidence occupies about 17.7 GiB and only about 5 GiB
was free initially. Archive separately, verify every member before removal, keep
tracked reports/scripts and active reference dependencies. No remote is configured;
actual user input, splitting and fit options remain unavailable. Asked for both.
The pinned history2ms script generates msHOT-lite output, so the standard ms
adapter explicitly changes only executable/output switches, with tested conversion.
Prospective simulation design and budgets: docs/known-truth-protocol.md.


Qualification transition results: 30 simulated datasets / 90 full fits completed;
all strict/C outputs exact, all three prospective relative-mode gates pass.
Absolute error remains substantial (maximum strict log RMSE 3.684), and four
post-hoc outliers exceed the earlier HG common-Q diagnostic budget. Full scientific
qualification remains open; no gate was relaxed and no case excluded.

Validation: 55 Rust release tests, four converter/scaling tests, four live-C
controls, 32 affinity-restricted bootstrap outputs, six final default-worker full
fits, all-feature compilation and formatting/diff checks. CUDA hardware ignored;
other CPU families/non-Linux and hosted CI not_run. v0.6.2 installed with strict
default and prior binaries preserved. No new numerical kernel or speed claim.

Space cleanup took priority at the user's request: suspended the simulation,
verified 87 archives / 90,993 members on the external backup drive, removed the
rebuildable debug cache, resumed and completed the same seeded panel. About
19 GiB reclaimed; about 24 GiB free. Incomplete first archive retained no data
loss. Compact source/reports remain in Git; restore raw historical paths using
the archive index. Panel timings include the suspension and are not benchmarks.

Remaining external inputs: remote repository URL for the requested push/hosted
CI, and the user's input/splitting/mask/command for real-workload qualification.
Those steps remain not_run. Larger known-truth studies and outlier investigation
are the next qualification work; optimization is paused by the user's direction.

## Strict memory admission — user whole-genome safety review

Completed v0.6.3 safety milestone: strict single CPU fits now admit workers within
half available memory by default, with --memory-mib override and cgroup headroom
where detectable. Reserve largest-record capacities including idle TLS and owner
workspaces; avoid a naive active-job token scheme that ignores retained memory.
Reuse the batch estimator's checked history formula. Equivalent worker defaults
and strict numerical arithmetic remain unchanged.

59 release tests passed. Eight distinct 1M-bin records reproduced previous serial
output exactly with requested 16 workers reduced to one at 2048 MiB and two at
3500 MiB; measured RSS about 995/1988 MiB. Too-small budgets reject before output
creation/truncation. Snapshot/decoding and checked-size cases remain covered.
Details: docs/strict-memory-admission.md and bench/strict-memory-rss.json.

Next milestone: the prospective 200 Mb known-truth protocol is written before
new simulation. Ten datasets for each of three histories, events moved into the
5k–80k window, prespecified time bands, relative and absolute accuracy budgets,
and event-direction checks. Original 20 Mb pilot gates remain unchanged. The
user's post-hoc band values are reproduced in bench/pilot-time-bands.json; recent
windows dominate error. Small likelihood gaps are reassuring fit-quality evidence,
not a universal significance threshold or proof of a particular ridge geometry.


## 200 Mb qualification results — 2026-10-10

Progress: all 30 datasets / 90 primary fits completed with no failures or
exclusions; all strict/C outputs exact. All six primary-band relative/absolute
checks and both event checks pass the protocol committed in 35b26e4 before
simulation. The audit verifies hashes, physical units, seeds, inputs, complete
outputs and summaries. Thirty additional instrumented equivalent replays match
the primary outputs exactly, with zero fallbacks in 3,634,535 model updates.
No band triggers the conditional 0.01 outlier screen.
A full N30 200 Mb strict memory check admits three workers under 512 MiB, peaks
at 304 MiB RSS and exactly reproduces serial output.

Decisions: preserve the original pilot's results and post-hoc amendment; report
all recent/ancient diagnostics. Keep equivalent opt-in and strict default. No
new speed claim or universal scientific equivalence claim. Raw simulations and
outputs remain in ignored work; compact results and audit are tracked.

Surprises: slow-core C controls approached the process timeout, so only this
harness and its children were restricted to allowed P-core threads. This
resource adjustment is recorded; binaries/data/options/gates stayed fixed.
No primary fit failed or was restarted/excluded. The 200 Mb bottleneck mean
errors remain larger than those of the constant/expansion histories despite
recovering the event direction; mode agreement is not exact truth recovery.

Next permitted milestone: predeclare a genome-scale truth panel; run the user's
actual input/splitting/mask/command when available; publish the existing CI after
a remote URL is supplied. These remain not_run. See the new report for scope,
test commands, admission limitations and retained numerical evidence.

## Genome-scale qualification goal — 2026-10-10

Objective: qualify the existing engines on continuous genome-scale simulated
inputs with criteria written before running and bounded memory/disk usage.
Progress: inspected clean b413690 and the current resource state; no prior genome
runner is active. New protocol: docs/known-truth-genome-protocol.md. Implement and
test a resumable resource-monitored runner, freeze source/binaries/protocol, then
execute 30 x 3 Gb datasets and all three engines. Audit/report all results and
perform the additional strict concurrent memory/order check before completion.
Decisions: retain the prior primary thresholds and event histories, use actual
250/120/110 Mb continuous chromosomes, two active datasets maximum, hard process
limits, verified compression and free-space/RAM stop thresholds. No production
numerical changes or speed claim. No reduced data substitute for genome scale.
Surprises: none yet; long continuous ms simulations may dominate run time. All
process failures or resource stops must remain visible and resumable under the
unchanged frozen design. Existing historical evidence is not removed.

Runner implemented with exclusive locking, frozen provenance, resumable hashed
stages, separate process groups, address-space/output limits, low priority and a
fail-closed resource monitor. Eleven Python tests pass, including actual child
limit enforcement, exact-stage reuse, corrupt-output rejection, chromosome
continuity/conversion, seed uniqueness and resource-floor rejection. No production
inference changes. Ready to freeze and launch the full predefined panel.

Launched under clean committed 41cff2e with frozen binaries/helpers/protocol.
The first two full 250 Mb chromosome simulations are live; no fitting result
exists yet. Session handle 61633 and work/qualification-genome/panel/run.lock
identify the live harness; bench/genome_status.py verifies its current process
and children before any resume. Resource samples are in resources.jsonl; raw
progress is in work/qualification-genome/run.log. Initial resource use is modest.
Prepared bench/audit_known_truth_genome.py to verify all 720 continuous chromosome
conversions, seed/unit/source provenance, all fits/gates and resource evidence.
The audit is not run/passed until the full report exists. Goal remains active.

Incremental chromosome audit added while the original simulations continue.
It independently checks ms command/seed echoes, single-replicate continuity,
heterozygous bin locations and encoding hashes as chromosomes finish, and is
also included in the final audit. Three added boundary/seed/tamper tests pass;
14 Python checks total. No completed chromosome yet, so this is verifier testing,
not scientific evidence. Frozen runner/protocol/binaries remain unchanged.

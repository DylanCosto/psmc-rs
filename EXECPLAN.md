# Execution plan: accelerated, legacy-compatible PSMC

Status: User explicitly approved building Rust on 2026-10-10. Phase 1 dense scalar Rust is implemented and passes its supported synthetic gate; see docs/phase-1-report.md. Real-workload baseline and reference-pathology investigation remain recorded limitations, not blockers to the newly authorized port. The user subsequently authorized optimization; Phase 2 CPU engineering and deterministic scheduling now pass the local synthetic gate; see docs/phase-2-report.md. The validated dense oracle remains unchanged. The original research/design completion checkboxes below were supplied with the plan and are not independent verification of the four missing companion documents.

## 1. Product definition and decision gates

The first product is a local command-line executable and reusable Rust library that accept existing `.psmcfa` data and reproduce the numerical meaning of the original PSMC output. It should reduce both single-fit latency and throughput time for 30 bootstrap replicates, without changing the scientific calculation to obtain that speedup.

A second product layer may convert modern VCF/gVCF/BCF and phased-assembly data into carefully validated PSMC inputs. A third, independently approved research track may exploit long-read phasing with multi-haplotype or genealogical methods. The three products have different compatibility claims and must not be conflated.

PHLASH is a required alternative-method comparator. It already supplies GPU acceleration and Bayesian uncertainty. Its existence does not eliminate a legacy-compatible performance project, but it changes the novelty and prevents a defensible claim of being the first GPU PSMC-like tool. Gamma-SMC is another useful technical comparator for decoding, not an output-equivalent substitute for PSMC fitting. [S11–S13]

## 2. Compatibility modes

Define and expose the modes before optimization:

| Mode | Contract | Permitted implementation |
|---|---|---|
| `strict` | Matching numerical records at the original printed precision on a pinned execution stack; byte-comparison after a small explicit metadata allowlist | Dense scalar path and only individually demonstrated parity-preserving optimizations |
| `equivalent` | Same model, preprocessing, EM procedure, iteration count, bootstrap samples, and output fields; prespecified numerical tolerances | Validated CPU/GPU transformations, deterministic reductions, full-count EM |
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
- [ ] Phase 3: broader structured CPU/full-count and objective acceleration.
- [ ] Phase 4: optional CUDA promotion.
- [ ] Phase 5: validation and release.
- [ ] Phase 6: long-read input layer.

## Decisions and surprises

Initial: preserve legacy EM rather than silently adopting augmented EM. Preserve full counts because the original objective includes a full-count entropy normalizer. PHLASH is pre-existing GPU prior art. Long-read assembly support already exists through the original documented dipcall route. Subsequent changes must be appended with evidence and date.


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

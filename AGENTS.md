# Repository instructions for Codex

## Objective

Implement a compatibility-first Rust PSMC engine. Target at least 10x acceleration of the user's 30-bootstrap workload, but make no performance claim without the benchmark protocol. Correctness and reproducibility take precedence over speed. Read `EXECPLAN.md`, `MATH_AND_COMPATIBILITY.md`, and `VALIDATION_AND_BENCHMARKS.md` before changing numerical code.

## Working rules

- Execute one acceptance-gated milestone at a time. Maintain the Progress, Decisions, and Surprises sections of `EXECPLAN.md`. Do not mark a task complete merely because code was written.
- First pin the original `lh3/psmc` source and compiler configuration; preserve its license notices. Read actual source, not only comments or this plan. Resolve discrepancies in writing.
- Keep a dense scalar f64 implementation as an oracle alongside the pinned C reference. Never replace it with an optimized backend.
- Keep the original model, discretization, fitted parameters, initialization, optimization sequence, iteration count, input boundaries, missing-data behavior, and output semantics in compatibility mode.
- Never enable f32, TF32, BF16, FP16, fast-math, new regularization, early stopping, coarser bins, fewer states, smaller datasets, or approximate state pruning to claim the compatibility speedup.
- Do not replace Hooke–Jeeves with another optimizer, remove the legacy Q normalizer, or adopt an augmented-state EM algorithm in compatibility mode.
- Parallelize only independent existing sequences and replicates. A computational tile is NOT an independent HMM sequence. Carry forward/backward boundary messages through tiles and gaps.
- Do not silently interpret absent VCF records as homozygous reference. Require documented callable reference evidence or an explicit VCF-plus-callability contract.
- Preserve every occurrence of repeated bootstrap blocks statistically. Cache computations, not observations. Cache keys include exact parameters and backend/precision; no reuse across different fitted parameter vectors.
- Use deterministic, explicitly ordered reductions. Avoid scheduling-dependent floating-point atomics. Never assume that thread-safe means numerically reproducible.
- Never weaken validation tolerances to make a test pass without explicit human review and a written numerical justification. Report all failed cases and fallback frequency.
- Each numerical optimization needs a derivation, isolated differential test, and before/after timings. Commit these together.
- Public test fixtures must be synthetic or redistribution-authorized. Never commit a user's genome, patient identifiers, tokens, absolute private data paths, or private cloud credentials. Do not upload genomic data to external services.
- Do not buy compute, initiate large paid jobs, or download whole cohorts without approval. Use small public/synthetic fixtures first.

## Implementation boundaries

Use Rust for parsing, model construction, reference CPU numerics, scheduling, checkpointing, manifests, and output. CUDA kernels and cuBLAS may be called through a small audited Rust FFI boundary. A Rust project need not insist that every GPU kernel be written in Rust. CUDA is optional: CPU-only builds must work without CUDA installed.

Pin dependency and toolchain versions only after checking the actual current documentation and target environment. Keep unsafe code localized with documented invariants. Prefer small flat buffers to general-purpose tensor abstractions in hot loops. Do not introduce a web service or GUI in the initial project.

## Completion evidence

Every milestone report must state: source commit and configuration; files changed; commands actually run; test results; measured timings and memory; untested hardware; unresolved issues; and the next permitted milestone. A missing GPU test is `not_run`, not `passed`.

If a backend fails the compatibility gate, leave it opt-in/experimental or disable it. If CUDA is slower than the optimized CPU, report that result and retain CPU as the default. Do not reclassify a method-changing implementation as legacy-compatible because the plotted curves look similar.

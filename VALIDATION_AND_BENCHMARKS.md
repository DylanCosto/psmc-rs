# Phase 1 validation policy — newly authored replacement

The originally referenced document was missing. This replacement records the
policy adopted before examining Rust results, following the user's explicit
authorization to build Rust on 2026-10-10. It is not a recovered attachment.

1. Compare the dense Rust implementation with pinned original C, first at model
   construction, then scaled messages, expected counts, Q/normalizer, callback
   sequence, first M-step and complete EM output. No numerical tolerance is to be
   relaxed to make a discrepancy pass.
2. The primary target on this Linux/glibc stack is exact finite f64 equality in
   internal snapshots and byte equality of numerical output. A narrow metadata
   exclusion is allowed only for an honestly identified program/version line.
   NaN payload identity is not scientifically meaningful: classify NaN/Inf and
   their appearance points separately; nonfinite reference parity does not pass
   a finite-inference check. If printed numerical output differs, strict mode is
   unsupported for that case and must not silently become equivalent mode.
3. Retain the independent Phase 0 path-enumeration diagnostic tolerance1e-10
   relative/1e-12 absolute. This already-existing diagnostic does not become a
   production equivalent-mode tolerance. Zero-contribution1e-25 count cells need
   exact comparisons.
4. Exercise ordinary/explicit supplied parameters, masks, aliases, independent
   boundaries, repeated records,23/64-state patterns,30 rounds, and all30 fixed
   bootstrap replicates. Reproduce retained nonfinite vanilla cases and report
   every mismatch. Test unsupported flags and invalid input rejection explicitly.
5. Keep existing C evidence intact. Place new comparisons, command/toolchain/input
   hashes, timings, memory and exclusions under `bench/phase-1*` or a separate
   raw directory. Validate output through upstream history conversion/plot data
   generation when available; rendered plots remain not_run without gnuplot.
6. Measure uninstrumented release Rust and unmodified C on identical synthetic
   inputs with identical options. Snapshot timings are diagnostic only. Real
   workload, optimized CPU, CUDA and10x claims remain not_run/unproven. The user's
  30 bootstrap processes already run in parallel, so no claim is made from adding
   ordinary process concurrency.

Phase 1 delivery must state supported options and stack, exact and failed gates,
finite/pathological case counts, measured runtime/memory, source/build provenance,
and remaining limitations. No Phase2/3 optimization or CUDA work in this milestone.

## Phase 2 extension — user-authorized CPU optimization

The user authorized optimization after Phase 1 completion. The exact numerical
policy remains in force. A separate CPU backend may reuse workspaces and invariant
transition layouts; it preserves each multiply/add and reduction order. Repeated
records may reuse counts only within one exact parameter snapshot. Add those
counts once for every occurrence, in input order, including tiny initializers.
Never reuse statistics across parameter updates or fits. Ordered bootstrap
references preserve original RNG draws and stopping; bounded replicate workers
do not alter per-fit reductions. Compare dense, CPU and original C on complete
trajectories and all 30 fixed bootstraps, across worker counts and task order.
Count/cache/profile metadata is additive and excluded from numerical output.
Record snapshot cache bypass explicitly. Preserve previous evidence separately;
no relaxed tolerance, changed algebra, reduced precision or CUDA is introduced.

## Phase 3a extension — strict single-thread SIMD

Run compiler inspection, isolated auto/off/AVX exactness and tail/dispatch tests,
then complete C/Rust output and snapshot gates sequentially. Preserve all prior
reports. Full 30-bootstrap comparisons are serial; multiworker validation and
throughput are explicitly not_run under the user's resource restriction. Pin
heavy jobs and descendants to one logical CPU, lower process priority, use one
Cargo job and one test thread. Record CPU time as well as wall-time variation on
the shared host. Strict parity remains exact; unavailable AVX and ARM require
explicit fallback/not_run classification, not fictitious hardware validation.

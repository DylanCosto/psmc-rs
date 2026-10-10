# Starting prompt for Codex

Read `AGENTS.md`, `EXECPLAN.md`, `MATH_AND_COMPATIBILITY.md`, `VALIDATION_AND_BENCHMARKS.md`, `LONG_READ_ROADMAP.md`, and `SOURCES.md`.

Start with **Phase 0 only**. Inspect the repository and available hardware without modifying user data. Pin the original PSMC source and document the exact command, compiler settings, input encoding, sequence boundaries, and bootstrap procedure. Establish a reproducible reference build and a workload manifest. Audit PHLASH as an existing GPU demographic-inference comparator; do not present its Bayesian output as the same output as legacy PSMC.

Create the differential-testing and profiling harness before implementing acceleration. The first deliverables are `docs/reference-contract.md`, `bench/workload.json`, `bench/baseline.json`, and `docs/phase-0-decision.md`. When actual sample inputs or GPU hardware are unavailable, use small synthetic fixtures, label real-workload results `not_run`, and record precisely what is missing. Do not invent sample timings or silently assume that the current bootstraps are serial.

In the decision report, distinguish: (1) exact legacy compatibility, (2) numerically equivalent accelerated legacy inference, and (3) a different modern inference method. Explain which remains justified by the benchmark and user's stated output constraint. Do not proceed beyond Phase 0 until that decision is reviewed.

After approval, implement the remaining milestones in order. Preserve the dense f64 Rust and pinned C reference paths throughout. Use the full-count structured-forward/backward route as the primary accelerated compatibility design. Do not start a new long-read statistical engine during the compatibility milestones.

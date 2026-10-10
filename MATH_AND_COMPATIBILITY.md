# Phase 1 working contract — newly authored replacement

The original attachment with this name was not supplied. This file is a new,
source-backed working contract for the user's 2026-10-10 authorization to build
the Rust implementation. It does not reconstruct the unseen original document.

The full audited mathematics and exact implementation behavior are in
`docs/reference-contract.md`, against original commit
`82fa2ada83ee463fe1251b562ae3d60e82d7ad6a`. Read that document and the actual C files
before translating each routine. Phase 1 is a literal dense scalar f64 port.

Preserve parameter order `[theta,rho,max_t,lambdas...,optional divergence]`, grouping,
time-grid endpoint 1000, initial distribution, emissions, and every matrix term's
parenthesization and loop order. Use the same platform libm for log/exp on the
tested Linux stack. No fused multiply-add, fast-math, reduced precision, changed
optimizer, repaired model formulas, or accelerated algebra is introduced.

Forward/backward use the original scaling convention. Missing bins retain their
transitions. Records restart the HMM; computational blocks cannot add boundaries.
Keep the final-site omission from expected emission counts, per-sequence1e-25
transition/emission initializers, aggregation order, omitted aggregate missing
emissions, and full-count Q entropy normalizer. Initial-state counts are retained
but excluded from Q. Preserve Hooke–Jeeves callback order, invalid-candidate
handling and final live callback side effects rather than restoring an optimum.

Existing nonfinite reference behavior is not silently repaired. Tests distinguish
pathology parity from valid finite inference. Runtime safety checks can reject
malformed inputs that would otherwise crash or loop forever; document them.

The retained C build remains the strict external oracle. Rust strict claims are
limited to the tested build/stack and explicitly supported inputs/options.
Equivalent acceleration and production tolerances remain outside this milestone.

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

The user authorized a SIMD implementation while limiting execution to one CPU
thread. Independent lanes may execute simultaneously, but every scalar lane's
operation grouping and addend order remain the Phase 2 order. No horizontal
reduction, FMA, vector math substitution or structured-algebra change is included.
See docs/phase-3-simd-derivation.md for the pre-validation derivation and gate.

## Optional CUDA extension — explicitly authorized 2026-10-10

The historical phase scopes above remain historical. An optional hybrid backend
may move transition-count cells to CUDA using the operation-order derivation in
crates/psmc-cuda/README.md. Every multiply/add uses explicit round-to-nearest f64,
with no contraction, altered site order or tile partial-sum reduction. CPU model,
messages, initial/emission counts, log-likelihood, normalizer and optimizer stay
unchanged. CUDA runtime failures are errors; no equivalent-mode substitution.

## Experimental equivalent extension — explicitly authorized 2026-10-10

`--mode strict` retains every contract above and remains the numerical default.
`--mode equivalent --backend cpu` opts into real-arithmetic triangular factors
with different binary64 grouping. See `docs/equivalent-mode.md` for the derivation,
predeclared component tolerances and empirical full-fit gates. Full expected
transition counts, original entropy normalizer, model, optimizer, observations and
iteration count remain. Guarded ineligible candidates use literal dense model/Q
calculations and are counted in `structured_fallbacks`. This is explicitly not a
strict-output claim, and the mode name is not evidence of scientific equivalence.

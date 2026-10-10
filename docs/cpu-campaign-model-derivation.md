# Reusing exact model invariants

The isolated candidates duplicate the pinned literal model-workspace calculation
in the CPU crate; core's dense model and original model workspace remain untouched.
The formulas are audited against `core.c::psmc_update_hmm` and
`psmc_update_intv` at `82fa2ada83ee463fe1251b562ae3d60e82d7ad6a`.

The ordinary grid depends only on state count, `max_t` and the grid offset alpha.
State count is fixed by the workspace. An exact `(max_t.to_bits(), alpha.to_bits())`
key may reuse the previous binary64 grid. Misses execute the original expressions
and loop order. Explicit grids retain their original copy path. All time cells,
including the terminal 1000, are restored even if a caller has overwritten the
model's public arrays. Nonfinite key values disable reuse. No approximate comparison
or logarithm/exponential substitution is made.

The second candidate also retains the expanded lambda vector and interval lengths.
The original alpha recurrence, beta recurrence, q_aux and C_pi depend only on those
two vectors. Their complete bit patterns must match the previous calculation
before reuse. A different group map that expands to the same lambdas is harmless;
changed interval lengths or lambdas trigger full recomputation. A missing or
nonfinite previous derived result is ineligible for reuse.

The candidate restores C_pi on a hit, then computes C_sigma and every model row
using the original formulas and operation order. Rho, theta and divergence are
read live. Sigma, initial probabilities, transitions and both nonmissing emission
rows are overwritten; the missing-emission row has the unchanged legacy contract.
No expected statistics, objective value, optimizer callback or accepted parameter
state is cached. The last callback's live model remains the original algorithm's
side effect, and model-update counters still count every callback.

The cache uses only a linear amount of additional storage and no unsafe code.
Tests compare every model field to the dense oracle across state sizes, repeated
and changed dependencies, explicit-grid switches, group changes, divergence,
invalid/nonfinite inputs, signed zeros and poisoned public output arrays. Private
invariant buffers are owned by the cache; arbitrary mutation of those private
buffers is not an external API operation.

Grid copying and dependency checks can outweigh saved transcendentals. Both
variants therefore require measured complete-fit benefits as well as exactness;
an isolated pass or a plausible cost estimate does not admit either to the release.

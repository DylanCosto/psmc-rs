# Implementation of the predeclared flagged-fit likelihood check

This diagnostic implements the frozen broader-qualification protocol; it does not
change its acceptance screens, production inference or frozen artifacts. It runs
only after the completed campaign passes the independent integrity audit.

For each flagged pair, reconstruct exactly its sampled ordered blocks from the
strict manifest (whose seed/draws were independently replayed and matched to the
equivalent run). Evaluate both final **printed** parameter vectors on these same
observations. No fitting, iteration extension or trajectory adjustment occurs.
The evaluator uses the existing dense CPU HMM with runtime SIMD and input-order
sums, first with literal model construction and then with independently transcribed
Decimal probabilities rounded to f64. Decimal precisions 50 and 80 must round to
identical matrices. The entire likelihood sum is still f64, not a Decimal HMM.

Literal probabilities outside [0,1], nonfinite values, normalization residual above
1e-12 or a nonfinite likelihood are reported as invalid. If either endpoint is
invalid, compare both with the common Decimal construction; otherwise retain the
literal comparison alongside Decimal sensitivity. This diagnostic validity check
is separate from the unchanged scientific screens.

Operational meaning of a “large first-group change”: absolute log lambda0 ratio
above 0.1. Such pairs also get five log-spaced lambda0 points between the two fitted
values, holding the other parameters at each endpoint background. This selects a
diagnostic slice, not a new acceptance threshold. Neither a shallow slice nor
similar LL proves convergence, a stationary ridge, or demographic accuracy.

Run sequentially after the main campaign, with one CPU, nice10, a 3 GiB hard address
space limit, 512 MiB per-file limit and one-hour per-pair timeout. Preserve output,
stderr, timing, resource samples, model points, input/parameter hashes and exact
commands. Check 4 GiB available RAM, 25 GiB disk and a 2 GiB diagnostic footprint.
Remove only each generated duplicate sample file after successful evaluation; its
source blocks, ordered manifest, checksum and all diagnostic results remain.
The script refuses an existing output directory and does not silently retry.

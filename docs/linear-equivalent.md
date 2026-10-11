# Linear equivalent E-step: prospective protocol

This milestone follows the user's explicit authorization to regroup equivalent
arithmetic and replace QD with QU. Strict arithmetic, QD, and the dense oracle
remain unchanged. This protocol is written before running candidate fits.

## Acceptance

Use the frozen HG001/HG002 original plus 30-bootstrap panel, the same seeds,
64 states, 30 EM rounds, initialization and records as v0.5.1. Reuse the pinned
C O2/FMA controls and frozen strict outputs; hash all inputs and binaries.

For each dataset, compare the distribution of absolute curve-log, theta-relative,
rho-relative and likelihood-per-bin differences. Require both median and nearest
rank p90 to be at most four times the corresponding C/C statistic, with floors
of 1e-6 for curve/relative parameters and 1e-10 for likelihood per bin (printed
output resolution). Four is an explicitly conservative engineering margin on
only two compiler builds, not a statistical confidence interval. Apply identical
checks to C/C first. No per-fit compiler-envelope gate.

Require maximum curve displacement / pointwise bootstrap SD <= 0.10 for every
fit, including the C/C controls. This user-authorized bound replaces the old 1%
screen: a numerical displacement of a tenth of the observed uncertainty is the
engineering budget, not proof of negligible inferential bias. Preserve all old
failed results. Zero SD admits only zero displacement.

Investigate every curve outlier exceeding max(0.01, four times that fit's C/C
curve difference), for candidate and C controls alike. Report fresh endpoint
likelihoods, both cross-Q values on common counts, and a lambda-only slice.
Require fresh endpoint likelihood difference and common-count Q differences
per bin <= 1e-8 for a ridge exception; report slice flatness separately, without
calling it a profile likelihood. A failed diagnostic blocks numerical acceptance.
Do not relax these thresholds after inspecting candidate results.

Component gate: finite messages, scales, triangle margins, diagonal/emission/
initial counts and raw Q against dense at identical parameters, absolute 1e-14
for probabilities/Q and 1e-24 for counts, plus 1e-12 relative. Cover tiny and odd
state counts, one-site records, masks, divergent and explicit-time models,
checkpoint boundaries, duplicates, invalid candidates and cache off.

Performance: one warmup, three alternating paired HG001 30-bootstrap runs with
16 workers and the same memory budget; report median wall/CPU/RSS and all pairs.
Require >=5% median improvement and wins in >=2/3 pairs. No projected speedup is
reported as measured. Scheduling has an independent bit-identical output gate.
Keep equivalent opt-in and strict default regardless of this limited-panel gate.

## Derivation and output contract

Write A[k,l]=L[k]q[l] below the diagonal, U[k]d[l] above it,
and D[k] on it. With x[l]=emission(next,l)*backward(next,l), contributions are:

* lower row: f[k]L[k] sum(l<k) q[l]x[l]
* upper row: f[k]U[k] sum(l>k) d[l]x[l]
* lower column: q[l]x[l] sum(k>l) f[k]L[k]
* upper column: d[l]x[l] sum(k<l) f[k]U[k]
* diagonal: f[k]D[k]x[k].

The same exclusive scans produce messages and these margins. Each triangle
margin includes one 1e-25 pseudocount per constituent matrix cell per record.
Emission counts still omit the final site; missing bins still carry transitions.
Records remain independent; 256-site checkpoints carry their boundary messages.
Reverse block/site accumulation is deterministic but intentionally differs from
v0.5.1 equivalent arithmetic. Four AVX lanes scan four contiguous state segments;
segment offsets complete the global prefix/suffix sums without subtraction.

QU reports unnormalized Q before/after optimization, with the full entropy
constant omitted from every equivalent objective evaluation, including fallback.
QU values cannot be compared across E-steps. Strict QD remains unchanged. Removal
of the constant can change floating-point optimizer ties and is included in the
full-fit gate. Invalid factors never get clipped: valid literal fallback models
must use complete counts reconstructed lazily from the frozen E-step posterior.

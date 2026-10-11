# Known-truth qualification pilot (prospective)

Freeze this protocol before generating the panel. This is an engineering and
scientific accuracy pilot, not a whole-genome or universal equivalence claim.
No additional speed optimization is part of this milestone.

## Design

Use Hudson's original `ms`, obtained through the author's source page
https://home.uchicago.edu/rhudson1/source/mksamples.html . Archive SHA-256:
`0edf46b9d35b3e677e00e4ea98c57c118c1ac7e3c3bfe748e038978b4a908205`.
Build the unmodified `ms.c rand1.c streec.c` with GCC `-O2 -lm`.

Three diploid panmictic histories, ten independent datasets each:

- Constant: Ne = 10,000.
- Bottleneck: Ne = 10,000 until 2,000 generations ago, 2,000 from 2,000
  to 6,000 generations ago, then 10,000.
- Expansion: Ne = 20,000 until 4,000 generations ago, then 10,000.

Each dataset contains twenty independent 1 Mb sequences (20 Mb total).
Mutation rate 2.5e-8/base/generation; recombination rate 5e-9/base/generation.
No missingness, ascertainment, phasing errors, population structure or selection.
Each ms replicate is an independent input record; do not split it further.
Generate each command with pinned PSMC `history2ms.pl`; replace `msHOT-lite`
with `ms` and remove its unsupported `-l` output switch. All demographic,
mutation and recombination parameters remain those emitted by the script.
Use `-p 12` for position precision and explicit three-word ms seeds. Convert the
standard two-haplotype output to exactly 10,000 100-base T/K bins per record:
K iff any differing site maps into that bin, T otherwise. Reject malformed data.
Retain source, commands, seeds, output hashes and the encoded inputs.

Fit vanilla C, Rust strict and Rust equivalent with the same 64-state pattern
`4+25*2+4+6`, 30 iterations, `-t 15 -r 5 -I 0`.
Use a fixed generation grid: 256 log-spaced points from 1,000 to 200,000
inclusive. Recover the final parameters from PA, reconstruct the original
alpha=0.1 grid, and scale Ne by theta/(4*mu*100), time by 2*Ne. Compare
piecewise-constant curves, without rescaling each fit to improve agreement.
Retain all failures and unidentifiable boundary parameters.

## Prespecified assessment

For every dataset, report each mode's root mean square natural-log error against
the true history on that fixed grid. Summarize by history, with all individual
fits retained. Require exact strict/C output equality except the version line,
and finite final parameters in all fits.

For each history, the upper one-sided 95% paired Student-t bound on the mean
(equivalent RMSE minus strict RMSE) must be below 0.05 natural-log units (df=9,
critical value 1.833112933). Also require the pooled RMS difference between the
modes' log curves to be <=10% of strict's pooled RMS error against truth.
These are prospective pilot non-inferiority budgets, not derived from the
observed errors and not a declaration that either mode is accurate in absolute
terms. Ten replicates provide limited tail and distributional evidence; the t
bound relies on approximate normality of paired errors. Report absolute errors
and failures even if the relative-mode budgets pass. No threshold adjustments
or selective exclusions after looking at results.

Known-truth recovery is complementary to compiler controls, bootstrap spread,
component tests and exact scheduling tests. It does not replace them. A larger
panel, realistic masks and the user's actual whole-genome preprocessing/workload
remain separate qualification steps. Keep equivalent opt-in.

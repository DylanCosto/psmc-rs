# Experimental structured numerical mode

Authorized 2026-10-10 after the user explicitly requested building and validating
structured mode while retaining strict mode. Existing strict tolerances do not
change. The user's CPU-default, version-reporting and golden-test edits are retained.

## Derivation and scope before implementation

Use the factors derived from pinned core.c in cpu-campaign-structured-derivation.md:
A[k,l] = L[k] q[l] below the diagonal, U[k] delta[l] above it, D[k] on it.
The existing diagonal and scalar model intermediates keep their original formulas.
Forward uses exclusive prefix sums of f U and suffix sums of f L.
Backward uses x[l] = emission[l] b[l], with prefix sums of q x and suffix
sums of delta x: b[k] = (L[k] prefix[k] + D[k] x[k] + U[k] suffix[k])/scale.
Scales, record boundaries, missing emissions, iteration counts, Hooke–Jeeves and
its final callback side effects retain the original meanings.

For full transition counts C, accumulate lower/upper row and column margins once
per E-step. Candidate Q uses diagonal C[k,k] log D[k], lower-row log L,
lower-column log q, upper-row log U and upper-column log delta terms, plus the
unchanged emission terms and full C entropy normalizer. This is the same
real-arithmetic objective, evaluated with different floating-point grouping.

The nonlinear entropy term sum C[k,l] log(C[k,l]/row_total[k]) is not determined
by these margins. This milestone therefore retains the full, quadratic transition
count calculation using the existing optimized CPU kernel. Messages and candidate
model/Q calculations become linear in state count; the entire E-step does not.
No 10x speedup is promised. Materialize the matrix once per E-step and at each
round's output, not at every eligible optimizer evaluation.

The raw model formulas include subtraction (q_aux, cpik, diagonal, alpha
increments). Positive probabilities alone do not prove numerical stability.
Only finite positive relevant factors and representably positive off-diagonal
products use the structured path. Other candidates use the literal model/Q path;
count and report these fallbacks. No clipping, probability repair, new optimizer,
precision reduction or altered statistical observations. Snapshot output is
initially unsupported in equivalent mode rather than presenting stale matrices.

## Predeclared validation

- Strict: retain exact C golden tests, run existing differential regression.
- Components: model, messages, counts and Q against dense at identical parameters;
  relative tolerance 1e-12 with absolute 1e-14 for probabilities/messages/Q and
  1e-24 for counts. Include masks, boundaries, repeated records, state counts,
  divergence, explicit grids, invalid candidate recovery and zero/underflow cases.
  Failures are recorded; tolerances are not widened after results.
- C sensitivity: three builds, O0 with contraction off, O2 with contraction off,
  O2 with native ISA and contraction fast (verify generated FMA instructions).
  No fast-math. Identical input records and seeds for all builds, HG001 chr22 and
  HG002 chr1, original fit plus 30 paired bootstrap samples each.
- Full fits: compare final theta, rho, LL and log-lambda curves on a common time
  grid (fit endpoints may differ). Report compiler envelope and bootstrap spread.
  Compiler agreement may be exactly zero; that is not a useful nonzero allowance.
  Report the proposed within-compiler-envelope criterion literally, including
  failure. Also report exploratory maximum curve difference <=0.01 log units,
  theta/rho relative difference <=0.001 and LL difference per bin <=1e-6;
  these are engineering screens, not an established scientific standard.
- Performance: one warmup and three alternating measured HG001 30-fit pairs,
  16 workers, same binary in strict/equivalent modes. Claim a useful speedup only
  if >=5% lower median elapsed time and at least two of three pair wins. Retain
  all failures. No optional repetitions to rescue a candidate.

Equivalent remains opt-in and experimental unless its numerical evidence supports
stronger wording. The mode name is not a claim of scientifically proven equivalence.

Full-fit comparison definition (fixed before the comparison): evaluate the
piecewise-constant log-lambda curve on 256 logarithmically spaced bin midpoints
between the first positive and last start time of the original O2 fit. Use that
same grid for all fits of a dataset. Also report interval-index log-lambda error,
RMS curve error and time-endpoint change, so a maximum at a moved boundary cannot
be mistaken for a uniform curve shift. Bootstrap spread is pointwise sample SD
of the 30 O2 log curves; the descriptive small-relative-to-spread screen is 1% of
that SD at every point. Zero SD with nonzero error fails. Compare the reported
legacy E-step likelihood (which precedes the final M-step); do not label it a
fresh likelihood evaluation of the final printed parameter vector.

### Why margins alone cannot preserve the full normalizer

Take four lower-triangular cells with source rows 2,3 and destination columns 0,1.
The blocks [[1,2],[2,1]] and [[1.5,1.5],[1.5,1.5]] have identical row and column
margins, and can have identical remaining cells. Their sum C log C differs.
Because their full row totals agree, subtracting C log(row total) does not remove
that difference. Thus the triangular sufficient statistics for candidate log A
are insufficient for legacy Q0. The implementation keeps all cells, including
every per-record 1e-25 initializer. Reducing that work further requires a separate
algorithm or an explicitly changed diagnostic/objective-offset contract.

### Compiler-panel resource amendment

Before any completed O0 fit and before viewing any FMA comparison, selected the
user's two-build option for the full panel: O2/contraction-off and
O2/native/contraction-fast. Disassembly confirms 0 versus 15 FMA-family
instructions. The extra O0 diagnostic was stopped during its original HG001 fit;
its partial output and original runner are retained. It is not a completed fit.
Both selected builds still run the original and all 30 bootstraps for both HGs.
No tolerance, fit length, sample size or acceptance criterion was relaxed. The
already-failed structured curve screen remains failed. `equivalent_c_baseline.py`
now reproduces the selected two-build panel from a fresh output directory;
`equivalent_c_resume.py` records this campaign's continuation without rerunning
its completed O2 controls.

Before starting any performance runs, add one v0.4.1 CPU control batch before and
one after the fixed mode pairs. The shared message workspace gained a structured
branch, so these controls check for a substantial regression in the retained
strict path. They do not change the equivalent-mode acceptance threshold and are
a descriptive two-run control, not a new claimed release speedup.

Measurement detail: use the nine-decimal `PA` records for theta, rho and grouped
lambda values. The `TR`/`RS` duplicates retain only six decimals and unnecessarily
hide small differences. Times still use `RS` and likelihood uses `LK` (six
decimals); zero observed difference is therefore resolution-limited. This parser
precision correction precedes final analysis and does not alter any tolerance.

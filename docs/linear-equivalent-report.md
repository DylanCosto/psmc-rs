# Linear equivalent E-step, v0.6.0

The equivalent engine now uses segmented AVX scans within each record and
triangle-margin transition counts. All messages/counts remain f64. The separate
quadratic transition-count pass and the ascending reconstruction pass are gone.
A forward pass saves scales and one state checkpoint per 256 sites; reverse
block reconstruction supplies the forward values for backward messages and
counts. Checkpoints do not reset the HMM. Odd state counts use zero padding;
all record lengths and repeated bootstrap records are supported.

`QU` is unnormalized Q before/after maximization. The entropy constant is omitted
from every equivalent objective, including literal fallback. It is not comparable
between rounds. Strict mode retains `QD`, its normalizer and literal arithmetic.
The upstream plotting/history/truncation tools previously audited do not read QD.
Snapshots remain unsupported in equivalent mode. Full-count observers retain
the reference structured path; ordinary fitting uses diagonal counts plus the
backend's private triangle margins.

If factors are invalid, the literal model is evaluated without clipping. Invalid
probabilities retain the reference sentinel/NaN behavior. A valid literal model
that cannot use factors triggers one lazy full-count reconstruction for that
E-step, using the same frozen parameters and segmented posterior. Reconstructions
are cached only within that expectation round. The normal scan/count loop is O(n) per
site; the guarded fallback can still cost O(n²). The shared Counts container
still reserves a dense array and performs O(n²) bookkeeping once per record,
which is negligible for the measured 50,000-bin blocks but not eliminated.

## Numerical evidence

The thresholds were written and hashed before new candidate fits in
[the prospective protocol](linear-equivalent.md). Existing C O2/FMA controls pass
all applicable checks on both public panels. This replaces the earlier per-fit
compiler envelope; historical failed screens are preserved. The fourfold
median/p90 limits and 10% bootstrap-SD budget are explicit engineering choices,
not calibrated statistical confidence bounds.

Both HG001 chr22 and HG002 chr1 were run as originals plus 30 bootstraps, retaining
64 states, 30 rounds, original record boundaries, masks, seeds, initialization and
Hooke–Jeeves settings. Every bootstrap draw was replayed independently. All 62
fits are finite and pass the declared distribution/spread checks.

| Measurement | HG001 | HG002 |
|---|---:|---:|
| Median curve log difference vs strict | 5.98e-5 | 4.68e-5 |
| Median C-FMA/C-O2 curve log difference | 1.05e-4 | 4.03e-5 |
| Maximum curve difference / bootstrap SD | 2.656% | 0.0611% |
| Structured fallback callbacks / total | 2,072 / 3,648,446 | 1,890 / 3,376,873 |

Bootstrap 13 triggers the prescribed extra ridge diagnostic. Its first-group
lambda is 845,981.020820268 under strict and 775,500.761907261 under the candidate.
Fresh strict-engine likelihood difference is -0.000292399; common-count Q
differences are -0.000222891 and -0.000211780. All are below 5.85e-10 per bin,
passing the predeclared 1e-8 per-bin diagnostic budget. The lambda-only slice
changes likelihood by at most 1.90e-6. This supports weak identification, without
proving global optimality or constituting a profile likelihood. Printed parameter
precision limits the diagnostic. The largest absolute curve displacement is
actually HG001 fit 3 (0.1292 log units), within four times its C build displacement;
it still satisfies the bootstrap-spread budget. No outliers are hidden.

The isolated tests compare segmented messages/scales, all four margins, diagonal,
emission and initial counts, and raw Q against dense arithmetic at fixed model
parameters. They cover n=2,3,4,5,7,23,64,65; lengths 1 through 1024 including both
sides of checkpoint boundaries; divergence and explicit grids; masks, duplicate
records, cache off, invalid candidates and lazy valid-model fallback. AVX and
portable scalar paths are tested separately. The original lockstep module remains
only as a test oracle and is not compiled into production.

Both strict original human fits and the full 30-HG001 strict batch are byte-exact
against pinned vanilla C outside the version line. The workspace release suite
passes 49 tests, with four CUDA hardware tests ignored/not_run; CPU debug passes
26 tests. All-features compile, formatting and whitespace checks pass. The
reference remains lh3/psmc 82fa2ada83ee463fe1251b562ae3d60e82d7ad6a; C controls
use the previously hashed source archive and compiler configurations.

## Reproduction and limits

Actual commands: `cargo test --workspace --release --offline`,
`cargo test -p psmc-cpu --offline`, `cargo check --workspace --all-features --offline`,
`python3 bench/linear_equivalent.py controls`, then `validation` and `performance`;
`target/release/examples/equivalent_ridge` on the retained sample-13 inputs;
`python3 bench/linear_equivalent_audit.py`. Raw observations and outputs remain
local under ignored work directories. Bench JSON records hashes and commands.

The first scalar-loop implementation passed components but barely reduced time;
explicit vector normalization and margin/emission updates were necessary. The
short pinned-core five-round HG001 screen reduced E-step time from 1.897s to
0.522s, M-step stayed near 0.094s, and RSS fell from about 504MiB to 10MiB. These
single screens do not replace the paired batch benchmark below.

CPU: i5-12600K, Linux/glibc 2.39, Rust 1.90, release opt-level 2, codegen-units 1,
no fast-math, no f32, no FMA requirement. ARM/NEON and CUDA hardware were not run.
No hosted CI or remote publication occurred. Equivalent remains experimental and
strict remains default. Two chromosomes and two compiler builds do not establish
general scientific equivalence. Shared-record scheduling is a separate milestone.

## Paired batch acceptance

One warmup and three alternating measured pairs, 30 HG001 bootstraps, 16 workers,
16GiB admission budget, affinity 0–15. All three pairs favor the candidate.

| Median | v0.5.1 equivalent | v0.6.0 equivalent |
|---|---:|---:|
| Wall seconds | 35.031 | 11.310 |
| Aggregate CPU seconds | 404.830 | 138.400 |
| Peak RSS KiB | 1078652.000 | 33956.000 |

Wall time falls 67.71% (3.10× speedup). The fixed >=5%/2-of-3 gate passes.
This is a measured comparison against v0.5.1, not a new paired vanilla-C benchmark.
See bench/linear-equivalent-performance.json for every timing, command and hash.

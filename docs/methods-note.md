# PSMC-rs methods and reproducibility note

PSMC-rs implements the pairwise sequentially Markovian coalescent model described
by Li and Durbin (2011), using the discretization, emission model and Hooke–Jeeves
optimizer of the pinned lh3/psmc implementation. The inference engine is written
in Rust and uses f64 throughout. Cite the original PSMC paper as well as the
specific PSMC-rs release used. This note describes implementation and validation;
it is not a peer-reviewed methods publication.

## Two arithmetic contracts

Strict mode preserves the original operation grouping, ordered reductions,
optimizer callback sequence and output diagnostics. Byte comparisons exclude only
the program/version header. Exact equality applies to the tested C build and
runtime stack, not every compiler/libm/platform. The dense scalar backend remains
an independent internal reference.

Equivalent mode factors the transition matrix into lower and upper triangular
terms plus a diagonal. Prefix/suffix scans and sufficient transition-count margins
reduce state-dependent work from quadratic to linear. Segmented SIMD scans change
floating-point summation order. Checkpoints preserve forward/backward boundary
messages inside a record; they do not create independent sequences. All original
record boundaries and missing observations remain. Noneligible structured models
use the documented literal fallback, counted in statistics.

The constant transition-count entropy term is omitted consistently from equivalent
mode's M-step objective. The output uses QU, distinct from strict/C's QD; QU values
are comparable within an iteration and must not be interpreted as QD. Fitted
likelihoods and scientific results require their own validation. Default equivalent
selection is a usability decision, not a claim of universal scientific equivalence.

## Parallelism and reproducibility

Independent records and bootstrap replicates may run concurrently. Counts are
reduced in original occurrence order. Repeated input blocks can reuse a computation
only within the same exact parameter state; every sampled occurrence contributes
its full multiplicity. Record-worker scheduling does not change each mode's output.
Bootstrap replicate i uses the recorded base seed+i and the legacy ordered draw
and stopping rule. Resume reuses only completed, checksum-verified fits with matching
input/settings/executable identity; it restarts unfinished fits from their beginning.

Memory admission estimates bound concurrent work, including full strict message
histories and equivalent checkpoint storage. They are not OS-enforced RSS limits.
Record bin size, mutation rate and generation time are external scaling assumptions.
Input preparation must document confident homozygous reference evidence; absence
of a VCF record alone is not sufficient.

## Evidence and limits

The repository contains prospective protocols, C/strict golden regressions,
component differentials, public HG001/HG002 comparisons, known-truth simulation
panels and a repeated controlled speed comparison. Native x86-64 and ARM64 Linux
builds run synthetic/regression checks; real-data whole-genome qualification is
local x86-64 evidence. These scopes must not be conflated.

The initial 20 Mb pilot had four outliers and weak recent-time recovery. A later
200 Mb panel passed its prospective primary-band/event checks but does not erase
those failures. Diagnostic high-precision construction revealed cancellation in
legacy equations and shallow between-mode likelihood paths. All four selected
pilot fits retained improving directions, so stationary ridges and full convergence
were not established. A stable-formula prototype remains isolated from production:
component accuracy alone did not establish safe optimizer behavior.

Thirty matched whole-genome bootstrap pairs passed the predeclared screens and
uncertainty bound; the largest primary-band difference was 0.0873% of strict
bootstrap SD. Four additional 23/32-state public-input comparisons passed, with
strict/C byte parity and passing compiler controls. See the
[release qualification report](adoption-qualification-report.md) and its frozen
protocol for exact configurations and limitations. The prepared public inputs have ascertainment limitations and
are implementation fixtures, not recommended demographic analysis pipelines. No
clinical validity, universal history recovery, or accuracy for arbitrary data is claimed.

## Suggested methods disclosure

Report the release/tag and mode, complete command, state pattern, iteration count,
input source/callability and binning rules, record boundaries, bootstrap splitting
and replicate count, base seed, biological scaling assumptions, CPU/runtime and
memory/worker settings. Preserve the version/mode header, manifests and checksums.
Do not infer that a successful exit means every legacy numerical field is finite.

Reference: Li H, Durbin R. Inference of human population history from individual
whole-genome sequence. Nature 475, 493–496 (2011). doi:10.1038/nature10231.

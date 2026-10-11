# Broader production qualification protocol

Frozen before execution, 2026-10-11. Numerical source base0b6bbfe; the frozen candidate selects version0.8.0. Exact
source/binary hashes are recorded in the campaign manifest; stable-model
prototype is excluded. This adds bounded empirical evidence, not a universal
claim of demographic accuracy. Earlier failed pilot screens remain visible.

## Inputs and fits

Use the already independently audited HG001 GRCh38 autosome PSMCFA (SHA-256
9d8633f04981b2b24114cad540368f46c508bf4290a976c430a182afcd55a112),
its chr22 record, and the previously audited HG002 GRCh38 chr1 PSMCFA (SHA-256
16d0f60777857fc724d46464da84c9b46c0755d3dbd7f678dfc88f1caed9bc14).
Restore only HG002's small encoded input from verified local evidence archive.
No human data enters Git, hosted CI, public assets or any external service.
Keep existing VCF-plus-callability preparation contracts/ascertainment limitations.

Additional-pattern panel: patterns `4+5*3+4` (23 states) and `8+8+8+8` (32 states),
each on HG001 chr22 and HG002 chr1, with C-O2, C-FMA, Rust strict and equivalent.
Use30 iterations, max_t15, theta/rho5, alpha0.1, zero random initialization,
seed20261011 for Rust. Pin upstream commit82fa2ada; build independent C binaries
with -O2 -ffp-contract=off and -O2 -ffp-contract=fast -mfma (x86-64 host).
Keep the selected binaries/source/protocol hashes frozen.

Whole-genome uncertainty panel: split each HG001 chromosome with exact pinned
splitfa semantics into50,000-bin blocks (5Mb at100bp/bin); preserve all missing
bins and boundaries. Run30 strict and30 equivalent bootstrap replicates using
base seed20261011, pattern4+25*2+4+6,30 iterations and the same other settings.
The two modes must have identical sampled record indices and traces for each seed.
Use encoded-input hashes and per-fit output/statistics/trace hashes. The existing
unsplit main fit is separate; bootstrap splitting intentionally changes boundaries.

## Predeclared checks and interpretation

- Strict must match C-O2 byte for byte on all additional-pattern trajectories,
  excluding only the version header. All outputs must contain rounds0–30 and
  finite positive final parameters. Report nonfinite trajectories separately.
- For each paired comparison compute theta/rho relative difference, final printed
  LK difference per bin, and RMS/max log-Ne difference on common fixed log grids.
  Use the existing bands1k–5k,5k–20k,20k–80k,80k–200k generations and
  mutation rate2.5e-8 with100bp bins. No time/height alignment or fitted rescaling.
- Apply the preceding whole-genome exploratory screen (primary-band RMS<=0.01,
  theta/rho relative<=0.001, absolute LK/bin<=1e-6) to C-FMA/C-O2 first on the
  four controls. If a control fails, that screen is not an implementation-specific
  acceptance test for that case; report both comparisons and the failed calibration.
  Do not replace this with a per-fit compiler-envelope gate.
- For30 whole-genome pairs report the complete distributions, medians,95th
  percentiles and maxima of mode differences. Compute sample SD of strict log-Ne
  across the30 bootstrap fits at each grid point, and differences as fractions
  of this uncertainty. Report undefined ratios at zero SD explicitly.
  The exploratory uncertainty bound is maximum paired difference<=10% of the
  bootstrap SD at every primary-band point. Also retain recent/ancient results.
  This is a practical descriptive bound, **not** a hypothesis test, statistical
  confidence interval, or a measured whole-genome C compiler-noise distribution.
- Flag any whole-genome pair failing the preceding numerical screen or uncertainty
  bound for fresh observed-LL evaluation at both final parameter vectors. Use the
  independent Decimal model if literal probabilities are invalid. Report a
  lambda0 log-scale slice only when a large first-group change motivates it.
  A flat slice does not prove full convergence, a ridge or demographic truth.
- Record structured fallbacks/model updates, memory admission, peak RSS and
  resource floors. Report every failure/exclusion; no post-hoc threshold changes.
  Full native CI regressions remain required for both x86-64 and ARM64; this human
  data campaign itself is local x86-64 only. User-specific inputs remain untested.

## Resource and audit policy

Run stages sequentially; no competing speed benchmark or simulation. Bootstrap
workers<=16, admission budget8192MiB, hard per-stage address space12GiB;
additional-pattern processes are sequential and use one CPU for C, up to4 record
workers for Rust within4096MiB. Low priority, no nested CPU oversubscription.
Require14GiB available RAM before a large stage, monitor a4GiB available-RAM and
25GiB free-disk floor, and cap campaign footprint at2GiB. Stop and preserve raw
outputs on guard failure. New bootstrap resume is available but never silently
retry a stopped stage. Raw files stay in ignored work/adoption-qualification.
Source/protocol/binary/input hashes, commands, timing and final independent audit
are required before claiming completion. Runtime observations are not a new
controlled speed comparison; retain the prior benchmark as the speed evidence.

# PSMC-rs 0.8.0 — native binaries and reproducible workflows

Release candidate: unpublished; broader qualification is still running.

**Use `--mode strict` for exact C reproduction on the pinned, tested build.**
CPU fits still default to equivalent f64 mode, with QU rather than QD. This release
does not introduce the experimental stable-formula prototype or change inference
arithmetic. The 0.7.0 output/default transition remains in force.

## Installation and workflow

- Native GNU/Linux x86-64 and ARM64 archives, SHA-256 checksums, original licenses,
  build/source provenance and synthetic examples. Both architectures run native
  C golden/Rust regression checks and fits from extracted archives.
- A five-minute synthetic tutorial covers inspection, fitting, splitting, bootstrap,
  export and local plotting. Its five iterations and three replicates demonstrate
  mechanics rather than recommended scientific settings.
- `inspect` reports encoded input composition and duplicate names. `split` follows
  upstream splitfa's short-tail rule without crossing source records; output symbols
  are canonical T/K/N. Block sizes are specified in bins.
- `export` produces a scaled CSV from the last complete round, with explicit mutation
  rate, bin size and generation time plus source mode/version/checksum provenance.
  The optional Matplotlib helper displays individual bootstrap fits, not inferred
  confidence intervals.
- `--progress` prints iteration/completion messages on stderr without changing fit
  output. `bootstrap --resume` verifies the executable, encoded input, settings and
  all completed outputs before reuse. Interrupted fits restart from round zero;
  partial files are preserved. Kernel locking prevents concurrent batch writers.
- A local container recipe uses the verified release executable. No container
  registry publication or Cargo/Bioconda registry submission is claimed.

## Validation

Native x86-64/ARM64 CI, strict C regressions, synthetic interruption/resume,
source/input/output tamper rejection, splitfa differential and extracted-archive
checks are required. The local x86-64 container also passed strict golden and
equivalent smoke checks with networking disabled.

The broader production campaign is in progress under its frozen protocol: 30 matched public HG001 whole-genome bootstrap pairs and additional patterns
on HG001 chr22/HG002 chr1, including C compiler controls. Its results, failures and scope will be recorded separately; this release note
does not claim that the pending campaign passed.
Historical speed results remain labeled v0.6.3, not advertised as fresh v0.8.0 timings.

## Numerical investigation and remaining limits

The isolated stable-model prototype matched all 332 high-precision component checks
and eight pilot endpoint likelihoods. Full synthetic fits changed optimizer paths
and some parameters substantially; it stays outside production. The original 20 Mb
pilot failures and incomplete convergence findings remain visible. No universal
scientific equivalence or demographic recovery claim is made.

Real-data scientific evidence is local x86-64 Linux; native ARM build/regression
coverage does not imply ARM whole-genome or performance qualification. CUDA remains
experimental and slower than CPU in the measured campaign. macOS/Windows binaries
are not provided. The user's own input/callability/splitting workflow is untested.

## Upgrade notes

Resume only applies to newly created batches with a resume contract, and requires
the same executable/runtime and fit settings. Older batches are not silently imported.
Worker count, admission budget and task order may change on resume; fit parameters,
seed and replicate count may not. Preserve the original executable for long runs.

Memory admission is an estimate, not an OS-enforced RSS limit; input loading precedes
admission. Legacy nonfinite calculations remain reported rather than repaired. A
completed fit marker preserves its nonfinite status and does not imply scientific
success. See [resume details](bootstrap-resume.md) and [mode guarantees](modes-and-guarantees.md).

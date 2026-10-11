# Prospective 3 Gb known-truth qualification

Frozen before any genome-panel simulation or fit. Date: 2026-10-10.
This extends the 200 Mb evidence to genome-scale continuous sequences; it is
not a qualification of unavailable real input, masks or hosted CI. No numerical
production code changes are planned. Strict remains default, equivalent opt-in.

## Data, sources and fixed fitting configuration

Thirty datasets: ten each of the constant, bottleneck and expansion histories
from known-truth-200mb-protocol.md, with the same mutation/recombination rates.
Each dataset contains 24 independent diploid chromosomes with lengths
[250, 120 repeated 22 times, 110] million bases: exactly 3,000,000,000 bases.
Each chromosome is simulated continuously, without concatenating independently
simulated blocks or adding computational boundaries. These are synthetic
chromosome lengths, not a human reference assembly. There are 30 million 100-base
bins per dataset; retain every bin and original chromosome boundary.

Use the previously pinned unmodified Hudson ms executable and upstream pinned
PSMC history2ms.pl. For each chromosome generate one replicate with history2ms;
replace only msHOT-lite executable/output switch to standard ms, as tested in
the earlier panel. Preserve the full genealogy-based standard-ms model (no SMC
approximation), precision, mutation rate 2.5e-8 and recombination rate 5e-9 per
base per generation. Histories (generations before present, absolute Ne):

- Constant: [(0,10000)].
- Bottleneck: [(0,10000),(10000,2000),(30000,10000)].
- Expansion: [(0,20000),(20000,10000)].

For history index h=0..2 in the order above, replicate i=0..9 and chromosome
k=0..23, let q=24*(10*h+i)+k. The standard-ms seed triple is
[41001+q,43001+3*q,47001+7*q], all within 16 bits. No masks, sequencing error,
structure or selection. All seed triples are distinct. Standard-ms output is
converted with the existing tested decimal-position converter, one chromosome
at a time. Headers are chromosome IDs; no sequence is silently dropped.

Run pinned vanilla C, installed v0.6.3 strict, and equivalent for each dataset:
-p 4+25*2+4+6 -N 30 -t 15 -r 5 -I 0 (64 states, alpha 0.1, f64).
C is serial. Primary strict fits use --record-workers 1 --memory-mib 4096;
equivalent uses --record-workers 4. Both Rust fits collect --stats, including
fallback counters. Numerical reductions remain ordered. No speed claim is made.
Do not reduce iterations, states, sequence length or replicates to get a pass.

An additional strict scheduling/memory check on constant-00 requests 16 workers
with --memory-mib 8192 and must match its primary serial output byte-for-byte.
Run it alone, under the separate 10 GiB address-space ceiling, with at least
14 GiB available RAM. Measure admitted workers, estimate and peak RSS. It must
admit at least two workers; otherwise record incomplete concurrency coverage.
The ordinary primary processes have a 6 GiB address-space ceiling. Failure to
fit a required case within these limits is explicit, not an excluded sample.

## Prespecified scientific gates

Use the exact 200 Mb PA reconstruction, absolute units and summary definitions.
Each of the four bands uses 128 log-spaced, left-inclusive/right-exclusive points:
1k–5k diagnostic; 5k–20k primary; 20k–80k primary; 80k–200k diagnostic.
Retain the older 256-point 1k–200k RMSE for continuity. Report all windows.

For every history and both primary bands require:
1. All 30 fits' final parameter vectors finite and positive; all strict/C
   full outputs byte-equal except MM Version. All rounds 0..30 present.
2. One-sided 95% paired Student-t upper bound on mean (equivalent truth RMSE
   minus strict truth RMSE) <0.05 log units; ten pairs, df9, t=1.833112933.
   Approximate normality is assumed; this is not a simultaneous CI claim.
3. Pooled RMS mode difference <=10% of strict pooled truth RMSE.
4. Each mode's mean truth RMSE <=0.5 log units.

Both modes must also pass the unchanged median event-ratio checks: bottleneck
Ne(12k–24k)/Ne(50k–80k)<0.75; expansion Ne(5k–10k)/Ne(40k–60k)>1.25.
Window Ne is geometric mean over 128 log points. These descriptive budgets are
not universal scientific accuracy standards. A global scientific pass requires
all primary-band, finite/exactness and event checks; report every failure.
Do not revise thresholds, windows, histories, seeds or exclusions after results.

If mode-to-mode RMSE exceeds 0.01 in any band of any dataset, run the existing
fresh endpoint likelihood and both common-count Q diagnostics, with the retained
lambda0-only slices (not profile likelihoods). Report raw/per-bin deltas, with
no universal DeltaLL=1 rule or retroactive HG-Q gate. Fallbacks are reported;
nonzero fallback frequency alone is not a scientific rejection criterion.

## Resource budget, retention and interruption policy

At most two active datasets, each one external command at a time. Thus at most
eight fitting threads in the equivalent phase; serial C/strict may use fewer.
Each child is a separate process group, nice level 10, RLIMIT_AS 6 GiB;
RLIMIT_FSIZE 2 GiB per output file. The harness checks resources at two-second
intervals and records RSS, free disk and available RAM. These limits supplement,
not replace, strict memory admission. Python conversion handles one chromosome
at a time, not an entire uncompressed ms genome. Standard-ms jobs may be slow;
allow up to 24 hours per chromosome and per fit, retaining timeout evidence.

Require >=30 GiB free on the evidence drive and >=10 GiB available RAM before
launching a new ordinary child. Stop all owned active process groups if free
disk falls below 25 GiB, available RAM below 4 GiB, or this panel's evidence
exceeds 12 GiB. Do not kill or alter unrelated processes. Resource-stop partials
and attempts remain recorded; exact frozen stages may resume when capacity is
restored. A resource stop is incomplete qualification, not a scientific pass.
A monitor exception also stops owned processes (fail closed).

Retain compact encoded inputs (~0.9 GB across the panel), output/log/stats files,
seeds, all commands and hashes. After each chromosome, gzip standard-ms output,
verify decompressed SHA-256 against the original, then remove only that redundant
uncompressed file. No other evidence deletion. Maximum temporary output per child
is 2 GiB. Monitor total directory size, and retain all failed/interrupted attempts.
Freeze copies/hashes of ms, C, Rust, ridge diagnostic and history2ms, plus protocol,
runner and helper source hashes before running. Resume only matching provenance;
validate completed stage hashes before reuse. Hold an exclusive run lock to avoid
duplicate harnesses. Never restart merely because tool observation timed out.

## Completion evidence

Completion means all 30 genome datasets/90 primary fits executed or explicit
scientific failures retained and investigated, required outlier diagnostics done,
additional concurrent strict check done, resource logs audited, sources/configuration
verified, and a committed report of outcomes and limits. A scientific gate failure
must remain a failure; completing the investigation is not permission to call it a
pass. Process/resource interruptions leave the panel incomplete until resolved.
Audit sequence lengths/counts/alphabet, full chromosome continuity from simulations,
units/seeds, installed executable hashes, output comparisons, counters, summary
arithmetic and prospectivity. Preserve raw evidence locally outside Git; track
compact analytical evidence and reproduction scripts. Update EXECPLAN and README.

ARM/non-Linux/CUDA, real callability and the user's actual input/splitting/command
remain not_run. Hosted CI still needs a remote URL. No performance extrapolation
from this accuracy campaign. No scientific qualification beyond this design.

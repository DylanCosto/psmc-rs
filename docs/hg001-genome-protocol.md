# Prospective public HG001 whole-autosome comparison

Date: 2026-10-11. This replaces the slow simulation campaign at the user's explicit
request. That campaign was stopped with its logs/partials preserved and no completed
chromosomes/fits; it is cancelled, not passed. This protocol is committed before
preparing the new PSMC input or fitting it. No inference code changes are planned.

## Public data and input contract

Use GIAB HG001 (NA12878), NIST v4.2.1, GRCh38, all chromosomes 1–22. This is the
whole autosomal genome; sex chromosomes and mitochondrial DNA are excluded by the
published diploid benchmark. Preserve full lengths from VCF contig declarations,
including missing regions, in exactly one PSMC record per chromosome. No splitting
or concatenation across chromosome boundaries, and no bootstrap resampling here.

Source directory:
https://ftp-trace.ncbi.nlm.nih.gov/ReferenceSamples/giab/release/NA12878_HG001/NISTv4.2.1/GRCh38/

- HG001_GRCh38_1_22_v4.2.1_benchmark.vcf.gz
  SHA256 93bc4c2c696eaf13515ab058caecc064bfed704f85bac7482330ca91bc730daa
- HG001_GRCh38_1_22_v4.2.1_benchmark.bed
  SHA256 dc3485e60447a3e863c34dfc063c3710ea5ed5efae50855c5197ba62538263b9
- Parent README_v4.2.1.txt
  SHA256 70e7d8cd54119c40e1be946574ce1b91db835af594809466bcf7d3727eaa9699

The GIAB README explicitly describes confident homozygous reference calls and
requires using VCF and BED together. Treat unlisted variants as homozygous only
inside the high-confidence BED. Reuse the tested HG002 converter contract:
A is a homozygous state placeholder, M a diploid PASS heterozygous simple SNV,
N is missing; these are not literal reference bases. Mask every non-simple-SNV,
non-PASS or invalid/missing diploid genotype's reference span plus five bases on
either side. Apply exclusions before heterozygous assignments so no masked base
is restored. Regions outside BED always remain N. This intentionally conservative
ascertainment is a compatibility fixture, not a recommended demographic pipeline.

Use pinned upstream fq2psmcfa with default 100-base bins: >90 missing bases gives
N, otherwise any called heterozygote gives K, otherwise T. Preserve its partial
last-bin semantics. Independently compare every output bin and require all 22
chromosomes present. Stream one chromosome at a time; retain compressed state
FASTA for reproducibility and all input/output hashes. Validate the entire VCF
gzip CRC, sample ID, contig declarations, BED order/bounds and VCF order/genotypes.
Do not download raw reads or a reference FASTA; no literal bases are needed here.

## Runs and comparisons fixed before fitting

Freeze copies/hashes of pinned vanilla C, installed v0.6.3 Rust, upstream converter,
ridge diagnostic, protocol, runner and conversion helpers. Use identical encoded
input and options for all three engines:
-p 4+25*2+4+6 -N 30 -t 15 -r 5 -I 0 (64 states, alpha 0.1, f64).
Run one fit at a time, C then strict then equivalent. Strict requests 16 record
workers with --memory-mib 8192; equivalent requests 8 workers. Rust collects
--stats. Record wall/CPU time, peak RSS, admitted workers, model updates/fallbacks,
all final parameters, and all numerical outputs. Timings are single observations
on a shared machine, not a repeated benchmark or a guaranteed speedup.

Strict acceptance: all rounds 0..30, finite positive final parameters and exact
full C output except the honest MM Version line. Equivalent must also complete
all rounds with finite positive final parameters and finite likelihoods. Its QU
line is the documented different diagnostic contract; don't compare it as QD.
Report theta/rho relative differences, legacy LK absolute/per-bin differences,
and absolute-Ne log-curve RMS/max differences on the four predeclared time bands
1k–5k, 5k–20k, 20k–80k, 80k–200k generations (128 log points per band), plus the
full 1k–200k grid. Absolute scaling uses mu=2.5e-8 and 100-base bins identically;
this is a shared plotting convention, not a claim about HG001's true demography.

The exploratory agreement screen is RMS log-curve difference <=0.01 in each
primary 5k–20k/20k–80k band, theta/rho relative differences <=0.001 and legacy
LK absolute difference / total encoded bins <=1e-6. These are descriptive screens,
not a calibrated equivalence theorem. If ANY band exceeds 0.01 RMS, or any screen
fails, run fresh strict-engine endpoint LL, both common-count Q comparisons and
lambda0-only slices on this same genome. Keep every failure and outlier; no
post-hoc relaxed thresholds. Small endpoint gaps do not prove ridge geometry.
Do not infer compiler-envelope or bootstrap-SD acceptance without those controls.
Prior chromosome/compiler and known-truth evidence remains separate.

## Memory, disk and completion

Single external fitting process at a time. Fits have a 10 GiB address-space ceiling,
nice level 10 and 512 MiB per-output-file limit; strict also has its 8 GiB admission
budget. Input preparation has a 3 GiB address-space ceiling. Start a fit only with
>=14 GiB available RAM and >=30 GiB free disk. Sample active process-group RSS and
resources every two seconds. Stop only owned process groups if available RAM falls
below 4 GiB, free disk below 25 GiB or this campaign's disk footprint exceeds 4 GiB.
Monitor exceptions fail closed. Each fit may run up to six hours; a timeout or
resource interruption remains incomplete evidence. Preserve partial attempts and
resume only matching frozen binaries/input/configuration. Avoid duplicate launches
with an exclusive lock. Downloads total about 142 MB; expected retained evidence
is well below 1 GiB. No unrelated files are removed.

Completion requires verified shutdown of the old simulation, validated whole-
autosome input, all three required fits/comparisons, conditional diagnostics when
triggered, audited resource/results evidence and a committed report with exact
commands/hashes/limits. Finishing the comparison is not permission to mark failed
screens passed. Keep strict default and equivalent opt-in. No claims about true
history recovery, whole-genome bootstrap uncertainty, missing sex chromosomes,
ARM/CUDA or hosted CI. No raw genomic input is committed or uploaded elsewhere.

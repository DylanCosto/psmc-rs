# Public HG001 whole-autosome comparison

The requested three-engine comparison is complete on all 22 autosomes of public
GIAB HG001 (NA12878), GRCh38 NIST v4.2.1. Strict/C exact comparison:
**PASS**. Equivalent's prospectively declared
exploratory agreement screen: **PASS**.
This compares implementations on real data; it does not establish a true demographic
history or a universal scientific equivalence guarantee.

## Data and provenance

The [prospective protocol](hg001-genome-protocol.md) was committed before preparation
and fitting. Source commit `76d81f99cc91cae37689355d976fdd80789c9867`; protocol hash
`8cf118b8e04035573da978ee728d204c1c41604fb0214f3cba453419e4785984`. The frozen runner, binary, source and input hashes and
exact commands are in [full results](../bench/hg001-genome-results.json), with
[the verification audit](../bench/hg001-genome-audit.json).

Input: **2,875,001,522 reference bases**, **28,750,027 100-base bins**,
22 complete chromosome records. Bin counts: `{'N': 3175977, 'T': 23832991, 'K': 1741059}`. Input SHA256:
`9d8633f04981b2b24114cad540368f46c508bf4290a976c430a182afcd55a112`. The same file was supplied unchanged to all engines.
The upstream converter and independent rule matched every bin; the final audit
reconstructed bins again from retained compressed state sequences.

Official [GIAB source directory](https://ftp-trace.ncbi.nlm.nih.gov/ReferenceSamples/giab/release/NA12878_HG001/NISTv4.2.1/GRCh38/)
and [release README](https://ftp-trace.ncbi.nlm.nih.gov/ReferenceSamples/giab/release/NA12878_HG001/NISTv4.2.1/README_v4.2.1.txt).
The README explicitly includes confident homozygous reference calls and requires
VCF/BED together. Bases outside BED remain missing. Invalid/non-SNV variants are
masked with five flanking bases before assigning heterozygotes. Full chromosome
coordinates, masks and partial-bin semantics are retained. No artificial splits.
State letters are placeholders, not actual reference bases. Sex chromosomes and
mitochondria are excluded by this autosomal benchmark. Confidence ascertainment
makes this an implementation fixture, not a recommended demographic pipeline.
No raw reads/reference FASTA were downloaded and no raw genome is committed.

## Measured execution

Each fit used 64 states and 30 iterations: `-p 4+25*2+4+6 -N 30 -t 15 -r 5 -I 0`,
f64, original optimizer, alpha 0.1. Fits ran sequentially with low scheduling
priority; strict requested 16 workers within an 8192 MiB budget, equivalent eight.
Installed Rust SHA256: `682be008483ef60aa226e448f03d2f1f073b008a87787f9fe7af78fe9bd810fb`.
C source remains pinned to `82fa2ada83ee463fe1251b562ae3d60e82d7ad6a`.
The platform is x86-64 Linux/glibc on i5-12600K, Rust 1.90 and pinned GCC C build.

| Engine | Record workers | Wall seconds | CPU seconds | Peak RSS MiB |
|---|---:|---:|---:|---:|
| c | 1 | 3159.43 | 3159.01 | 2598.4 |
| strict | 2 | 347.05 | 684.09 | 4893.2 |
| equivalent | 8 | 31.00 | 210.37 | 326.3 |

These are single observations on a shared machine with different worker counts,
not a repeated speed benchmark. The strict admission estimate was
7.283 GiB. No inference
arithmetic or production code was changed for this campaign.

## Numerical comparison

Strict equality excludes only `MM Version`; all rounds 0–30 and every remaining
output byte are compared. All final parameter vectors were positive and finite.
Equivalent uses the existing QU diagnostic contract, while strict/C retain QD.

| Band | RMS log Ne difference | Maximum log Ne difference |
|---|---:|---:|
| recent | 8.83058e-06 | 1.27247e-05 |
| primary_early | 1.35309e-05 | 3.26847e-05 |
| primary_late | 3.75083e-06 | 7.93478e-06 |
| ancient | 4.90561e-06 | 7.93478e-06 |

Theta relative difference: **2.76929e-06**; rho: **2.70778e-06**.
Legacy LK absolute difference: **0.000173**,
**6.01737e-12 per encoded bin**. LK precedes the last M-step;
it is not silently presented as a fresh final-parameter likelihood.
Full-grid RMS/max log differences: 9.05555e-06 /
3.26847e-05. Scaling uses the same mu=2.5e-8 and bin size for
both fits, with no fitted alignment. The recent/ancient diagnostic windows remain
visible. No compiler-envelope or bootstrap-spread claim is made from one genome.

Equivalent fallbacks: **63 / 112,781 model updates**
(0.000558605). Conditional fresh LL/common-Q/lambda0-slice diagnostic:
**not triggered by the predeclared screen**.
No failed screen was revised or excluded.

## Resource control and validation

Observed minimum available RAM: 15.49 GiB;
minimum free disk: 90.67 GiB;
maximum campaign footprint: 0.209 GiB.
Resource samples, peak memory and safeguards are retained in the audit. Hard
address-space limits supplement strict admission; neither changes the data.
Three new preparation/runner tests passed. The existing v0.6.3 numerical release
checks remain the preceding evidence; this campaign did not change their code.

Commands run:

```bash
python3 -m unittest discover -s bench -p 'test_hg001_genome.py'
python3 bench/hg001_genome_run.py --root work/hg001-genome
python3 bench/hg001_genome_finish.py --root work/hg001-genome --wait
```

The slow synthetic campaign was stopped at the user's request, with no completed
chromosomes or fits; its logs/partials are preserved and it is not marked passed.
The earlier 200 Mb known-truth evidence remains separate. This result does not
qualify real-workload splitting chosen by the user, whole-genome bootstrap
uncertainty, ARM/non-Linux/CUDA or hosted CI. Strict remains default and equivalent
opt-in. Raw and compressed input evidence remains in ignored `work/hg001-genome`.

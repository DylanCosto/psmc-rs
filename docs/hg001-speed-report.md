# Controlled HG001 whole-autosome speed comparison

Completed and independently audited on 2026-10-11. On this public whole-autosome
fixture, Rust strict is **4.79× faster than vanilla C on one core**, and Rust
equivalent is **17.66× faster on one core**. With all 16 logical CPUs available,
equivalent takes **26.24 seconds**, **115.41× faster than single-core C** and
**6.54× faster than its own single-core run**. These ratios describe one full fit,
not the user's 30-bootstrap workload or performance on other machines.

## Repeated measurements

Each row contains three measured runs; one complete warmup per configuration was
excluded prospectively. Wall time includes process startup, parsing, fitting,
output and Rust stats. All fits used the same input and 30 iterations, running
sequentially. Peak RSS is the maximum among that row's three measured runs.

| Configuration | Record workers | Median seconds | Range, seconds | Peak RSS, MiB | Speedup vs C single |
|---|---:|---:|---:|---:|---:|
| Vanilla C, single core | 1 | 3028.28 | 3007.61–3030.11 | 2598.86 | 1.00× |
| Rust strict, single core | 1 | 632.78 | 632.30–634.76 | 2481.42 | 4.79× |
| Rust equivalent, single core | 1 | 171.52 | 168.55–177.09 | 90.78 | 17.66× |
| Rust strict, full affinity, memory-limited | 2 admitted of 16 requested | 335.11 | 333.85–345.51 | 4893.04 | 9.04× |
| Rust equivalent, full affinity | 16 configured | 26.24 | 26.24–26.30 | 492.72 | 115.41× |

Strict retained the **8192 MiB admission budget** and admitted two workers, with
an estimated 7.283 GiB including reserved workspaces. Its 1.89× improvement over
single-core strict is a memory-limited two-worker result, not an unconstrained
16-worker result. The full-affinity equivalent run used less than 0.5 GiB peak RSS.

CPU time divided by wall time averaged 1.97–1.98 CPU equivalents for full-affinity
strict and 12.07–12.12 for equivalent. Single-core ratios were approximately 1.00.
Equivalent's 16-worker setting is verified in the executed command; there is no
independent per-thread occupancy trace. CPU-time ratios measure aggregate usage,
not equal capacity across this processor's P-cores, E-cores and SMT siblings.

Measured wall times in repetition order:

| Configuration | Repeat 1 | Repeat 2 | Repeat 3 | Excluded warmup |
|---|---:|---:|---:|---:|
| C single | 3028.28 | 3030.11 | 3007.61 | 3087.69 |
| Strict single | 634.76 | 632.30 | 632.78 | 637.92 |
| Equivalent single | 177.09 | 168.55 | 171.52 | 171.71 |
| Strict full affinity | 333.85 | 335.11 | 345.51 | 340.51 |
| Equivalent full affinity | 26.30 | 26.24 | 26.24 | 26.20 |

All times above come from GNU time, not the harness's coarser completion polling.
No observations were dropped. The raw CPU times and host load/pressure snapshots
are retained in [results](../bench/hg001-speed-results.json). Three repetitions
describe the observed range; they do not establish narrow confidence intervals.

## Output agreement and fallbacks

All **20 complete outputs** (15 measured plus five warmups) matched the audited
output for their engine exactly, excluding only `MM Version`. Every strict fit
also matched vanilla C. All rounds 0–30 were present; printed numerical fields
were finite and parameter vectors positive. Parallelism did not change output.

The preceding [HG001 agreement comparison](hg001-genome-report.md) independently
passed its strict equality check and predeclared equivalent exploratory screen.
Equivalent versus strict had full-grid RMS log-Ne difference 9.056e-6 and maximum
3.268e-5; theta/rho relative differences were 2.769e-6 / 2.708e-6. Legacy printed
LK differed by 0.000173, or 6.017e-12 per bin. This LK precedes the final M-step;
it is not a fresh final-parameter likelihood. The conditional ridge diagnostic
was not triggered. No scientific screen was revised or failed cases excluded.

Every equivalent fit recorded **63 structured fallbacks / 112,781 model updates**
(0.05586%); all eight equivalent fits together recorded 504 / 902,248. Strict
recorded zero structured fallbacks and 110,294 updates per fit. Those counts
match the preceding whole-autosome comparison. Equivalent retains its QU
diagnostic contract; strict/C retain QD. Agreement with C on this real sample is
not evidence of a known true demographic history or universal equivalence.

## Resources and method

The campaign kept at least **15.50 GiB available RAM** and **90.51 GiB free disk**.
The maximum sampled process-group RSS was 4.78 GiB; no resource guard fired.
GNU time reported zero swaps for every fit. The speed campaign used about
4.17 MiB of evidence during execution and reused the existing input in place.
The preceding input/comparison footprint was about 0.209 GiB; there were no new
genomic downloads or duplicate input copies.

Every child retained the 10 GiB address-space ceiling and 512 MiB/file output
limit. Strict's 8 GiB admission budget is an estimate, not a hard RSS limit.
The runner sampled machine resources every two seconds and required 14 GiB RAM
and 30 GiB disk before a fit, aborting its own group below 4 GiB RAM, below 25 GiB
disk, or above 4 GiB new evidence. No stage hit its six-hour timeout.

The i5-12600K host has 16 allowed logical CPUs. Single-core runs were pinned to
logical CPU 0, verified as a P-core; full-affinity commands allowed CPUs 0–15.
All jobs ran at nice 10. Single-core order rotated across engines, then full-core
Rust order alternated. Each fit was separated by at least five seconds.
No governor, SMT, cache or unrelated-process settings were changed. The host was
shared, and the single/full phases occurred at different times: these are
controlled input/affinity comparisons, not an exclusive-machine benchmark.

## Provenance and verification

The [prospective protocol](hg001-speed-protocol.md) and runner were committed as
`cb74d510208840c658faf561c18926777751a705` before any speed run, with a clean tracked
diff. Protocol SHA256:
`ee5a9fa6975a3defddb153a16473fa09979d048f7a540e39a0b5d8da1410f0e1`.
The existing input comparison was frozen under
`76d81f99cc91cae37689355d976fdd80789c9867`. No numerical code or binaries changed.

Input is public GIAB HG001/NA12878 GRCh38 NIST v4.2.1: all 22 autosomes,
2,875,001,522 reference bases and 28,750,027 100-base bins, retaining chromosome
boundaries and missingness. Its conservative VCF-plus-confidence-BED preparation
is an implementation fixture, not a recommended demographic pipeline. See the
[input protocol](hg001-genome-protocol.md) for the callable-reference contract.
Input SHA256:
`9d8633f04981b2b24114cad540368f46c508bf4290a976c430a182afcd55a112`.

Frozen C SHA256:
`da1743512f1925da6277d5a2e5350c70c61c9771d11749df0918605f795ff32b`.
Pinned upstream C source: `82fa2ada83ee463fe1251b562ae3d60e82d7ad6a`;
build provenance is in [the reference build record](../reference/build-vanilla.json).
Rust v0.6.3 SHA256:
`682be008483ef60aa226e448f03d2f1f073b008a87787f9fe7af78fe9bd810fb`.
Both use the existing f64 model and optimizer, 64 states and options
`-p 4+25*2+4+6 -N 30 -t 15 -r 5 -I 0`. Rust selected AVX, with stats enabled.
All exact commands, hashes and counters are retained in the compact results.

The independent auditor re-read raw output, GNU time, stats, attempt and resource
files; verified source/binary/input hashes against committed provenance; checked
warmup exclusion, all 20 commands, chronological order, strict admission, every
output comparison, fallback counts, finite fields and resource floors; and
recomputed medians, ranges and speed ratios without calling the runner's
schedule, timing or summary helpers. [Audit evidence](../bench/hg001-speed-audit.json)
records per-fit hashes and checks. Ten targeted Python tests passed, including
real CPU affinity and child resource limits plus rejection of changed outputs,
missing rounds, nonfinite values and failed timing records.

Commands executed:

```bash
python3 bench/hg001_speed.py
python3 bench/audit_hg001_speed.py
python3 -m unittest discover -s bench -p 'test*hg001*.py'
```

Raw evidence remains in ignored `work/hg001-speed`; no genome is committed or
uploaded. This delivery adds the independent auditor/tests, this report and
compact evidence, retains the completed input-comparison report, and updates
EXECPLAN. Strict remains default; equivalent remains opt-in. The user's actual
input/splitting procedure, whole-genome bootstrap uncertainty, unconstrained
16-worker strict, ARM, other processors, GPU and hosted CI remain untested here.
The next useful qualification is the user's real workload when available;
these results do not authorize weakening memory limits or resuming cancelled
simulations.

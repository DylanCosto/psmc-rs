# Broader production qualification — v0.8.0 candidate

This is an implementation comparison and empirical bootstrap-uncertainty screen,
not demographic ground truth or a controlled speed benchmark. Earlier pilot and
whole-autosome scientific screen failures remain visible in their original reports.

Frozen source: `e0867ada31249cfef3c6930c7f679f337740c1ef`. Protocol SHA-256: `1967fb757cf77a465086d4ee3548d0773350405241be87457563e973a421ab6f`.
Rust executable SHA-256: `0dc799a5a67ab3c9430e02fcbab408d3ac8dd7987ee67f96602c5bd3fd5356df`.
The stable-model prototype is excluded. The campaign ran locally on x86-64 Linux;
native ARM CI regression success does not extend these scientific results to ARM.

## Inputs, sampling and integrity

HG001 comprises 22 autosomes, 28,750,027 bins at 100 bp/bin (2.875 Gb).
Chromosome-preserving splitting produced 575 blocks under the pinned splitfa
50,000-bin/short-tail rule. Thirty strict and thirty equivalent fits used matched
seeds 20261011–20261040, 64 states (`4+25*2+4+6`), 30 iterations, t15/r5/I0.
The independent audit reconstructs all block contents and all RNG draws, checks
matching traces and completed-output hashes, and independently recomputes curves,
screens and sample SDs. Input preparation has the original VCF-plus-callability
ascertainment limitations; it is not a recommended demographic preparation pipeline.

## Additional patterns and compiler controls

The same exploratory screen was applied to C-FMA/C-O2 before interpreting
equivalent/strict. A failed C control means that screen is not specific to a
Rust implementation error for that case. No per-fit compiler-envelope gate is used.

| Input | States | Strict/C exact | C compiler screen | Equivalent screen |
|---|---:|---|---|---|
| hg001-chr22 | 23 | pass | pass | pass |
| hg001-chr22 | 32 | pass | pass | pass |
| hg002-chr1 | 23 | pass | pass | pass |
| hg002-chr1 | 32 | pass | pass | pass |

Strict/C equality excludes only the version header and covers all rounds 0–30.
There are only four C compiler controls. They do not measure a whole-genome
bootstrap distribution of C compiler noise. Detailed metrics are retained in JSON.

## Whole-genome differences across 30 bootstrap pairs

Curves use fixed log-spaced grids (128 points per band), mutation rate 2.5e-8
and 100 bp bins, with no time or height alignment. Values below are RMS natural-
log Ne differences. The p95 interpolates linearly at index (n−1)×0.95.

| Time band (generations) | Median RMS | p95 RMS | Maximum RMS | Maximum difference / strict bootstrap SD |
|---|---:|---:|---:|---:|
| 1k–5k | 1.12732e-05 | 1.73628e-05 | 1.99853e-05 | 0.000738585 |
| 5k–20k (primary) | 7.82594e-06 | 1.32497e-05 | 1.40032e-05 | 0.000873245 |
| 20k–80k (primary) | 3.26394e-06 | 4.6524e-06 | 4.88372e-06 | 0.000553199 |
| 80k–200k | 4.96624e-06 | 1.06315e-05 | 1.11276e-05 | 0.000555187 |

| Scalar difference | Median | p95 | Maximum |
|---|---:|---:|---:|
| theta_relative | 4.05332e-06 | 1.23618e-05 | 1.69724e-05 |
| rho_relative | 4.11548e-06 | 1.16827e-05 | 1.73525e-05 |
| legacy_lk_per_bin | 9.63531e-12 | 3.59848e-11 | 4.38051e-11 |

Exploratory numerical screen: **30/30 pass**.
The fixed screen requires primary-band RMS ≤0.01, theta/rho relative differences
≤0.001, finite trajectories and absolute printed LK difference/bin ≤1e-6.
Printed LK is the legacy E-step likelihood, not a fresh evaluation at the final
M-step parameters. The separate uncertainty bound is ≤10% of the strict sample
bootstrap SD at every primary-band grid point. These are descriptive bounds,
not hypothesis tests, confidence intervals or proof of demographic equivalence.

- recent: 0 undefined difference/SD ratios (zero SD).
- primary_early: 0 undefined difference/SD ratios (zero SD).
- primary_late: 0 undefined difference/SD ratios (zero SD).
- ancient: 0 undefined difference/SD ratios (zero SD).

## Flagged-fit diagnostics

Required pair indices: [].
No pair triggered the prospectively declared diagnostic rule.

## Resources and fallback behavior

Stages were sequential, low priority, under a 12 GiB address-space ceiling and
512 MiB per-file limit. Bootstrap admission was 8192 MiB with up to 16 workers;
both manifests admitted 16 pool workers (fit/helper roles are distinct).
Additional Rust fits used at most four record workers and 4096 MiB admission.
C additional-pattern fits had single-CPU affinity. Shared-host runtimes below
are resource evidence, not a new speed comparison.

| Stage | Elapsed seconds | Peak RSS MiB |
|---|---:|---:|
| split | 2.00 | 58.24 |
| bootstrap-strict | 2449.68 | 1396.99 |
| bootstrap-equivalent | 444.94 | 633.96 |
| hg001-chr22-4+5x3+4-c-o2 | 20.06 | 201.37 |
| hg001-chr22-4+5x3+4-c-fma | 18.08 | 201.36 |
| hg001-chr22-4+5x3+4-strict | 8.03 | 185.68 |
| hg001-chr22-4+5x3+4-equivalent | 2.00 | 19.96 |
| hg001-chr22-8+8+8+8-c-o2 | 18.04 | 279.09 |
| hg001-chr22-8+8+8+8-c-fma | 28.14 | 279.10 |
| hg001-chr22-8+8+8+8-strict | 44.21 | 255.39 |
| hg001-chr22-8+8+8+8-equivalent | 6.04 | 19.88 |
| hg002-chr1-4+5x3+4-c-o2 | 164.76 | 977.99 |
| hg002-chr1-4+5x3+4-c-fma | 126.57 | 978.13 |
| hg002-chr1-4+5x3+4-strict | 44.17 | 897.77 |
| hg002-chr1-4+5x3+4-equivalent | 16.05 | 33.40 |
| hg002-chr1-8+8+8+8-c-o2 | 116.37 | 1358.01 |
| hg002-chr1-8+8+8+8-c-fma | 84.13 | 1357.86 |
| hg002-chr1-8+8+8+8-strict | 28.04 | 1240.30 |
| hg002-chr1-8+8+8+8-equivalent | 8.01 | 34.01 |

The initial runner stopped after all 30 strict fits when available RAM failed
the next-stage 14 GiB preflight requirement. The original failure and strict
artifacts were preserved. An explicit continuation waited for the unchanged
floor and ran only the missing stages; no completed strict fit was rerun.
The audit checks the continuation source, preserved hashes and every recorded
continuation preflight. This interruption is part of the evidence.

Observed minimum available RAM: 7.752 GiB; minimum free disk: 70.313 GiB; maximum campaign size: 0.048 GiB.
The 4 GiB RAM / 25 GiB disk runtime floors and 2 GiB campaign cap were checked
against all resource samples; 14 GiB available RAM was required before stages.

- Bootstrap strict: 0 structured fallbacks / 3267291 model updates.
- Bootstrap equivalent: 1890 structured fallbacks / 3335544 model updates.

Equivalent bootstrap fallbacks represent 0.0567% of model updates.

Additional-pattern per-fit counters, exact commands, output/timing hashes and
source/binary identities are retained in the [results](../bench/adoption-qualification-results.json),
[independent audit](../bench/adoption-qualification-audit.json) and
[distribution summary](../bench/adoption-qualification-summary.json).
Raw inputs and run artifacts remain local in ignored `work/adoption-qualification`.

## Remaining limits

Known-truth qualification is still limited to the earlier 64-state panel; these
23/32-state comparisons do not establish demographic recovery for every pattern.
There is no user-specific input pipeline validation, whole-genome ARM qualification
or independent external-lab endorsement. The original 20 Mb pilot outliers and
legacy cancellation/nonfinite behavior are not repaired or erased by this campaign.
See the [frozen protocol](adoption-qualification-protocol.md) and
[validation overview](validation-overview.md) for their distinct scopes.

# Full-core bootstrap milestone — 2026-10-10

The existing Rust 0.3.1 scheduler is retained. On the tested Intel Core i5-12600K,
16 workers gave the fastest observed batch times across the tested configurations.
Compared with already-parallel vanilla at the same 16-worker limit, Rust completed
the original 30-bootstrap workload 1.73x faster and the model-based workload 2.77x
faster. The experimental heavy-first queue passed exactness but was slower in all
four paired comparisons, so it is not promoted. No production source, version,
scientific method, input boundaries or numerical tolerance changed.

The user's full-core authorization supersedes the earlier one-CPU restriction for
this milestone only. Each fit still has one numerical thread; independent fits
share immutable input and use their own RNG, workspace and count cache. There is
no nested pool or scheduling-dependent numerical reduction.

## Configuration and provenance

Baseline production source is `e8a1cc176c809d163735fc55df94f4a7510b419a`, with
accepted numerical changes in `7ee52716beecc51f5432e8ca3a681c8032792920`.
The delivered executable remains SHA-256
`b0fc39d7c31637221de1152fc0d502bb65c90d0a5b9d6672250fe3117f75bfa4`.
Pinned vanilla is `lh3/psmc` commit `82fa2ada83ee463fe1251b562ae3d60e82d7ad6a`,
executable SHA-256 `da1743512f1925da6277d5a2e5350c70c61c9771d11749df0918605f795ff32b`.
The experimental executable SHA-256 is
`7a06233688c5f43407e137faa655d6b28509b9a75c9a85f647b156ea772fe04a`.
`bench/parallel-candidate-build.json` records its generated source hashes, build
commands and test logs; it changes only two CLI files. Generated files and frozen
executables are retained under `bench/parallel/`, outside production source.

The host exposes 16 logical CPUs, IDs 0–15, across 10 physical cores (six paired
P cores and four single-thread E cores). The physical-only control uses
`0,2,4,6,8,10,12,13,14,15`. All benchmark groups ran separately at normal priority;
no CPU affinity default is added. This is a shared host, not an isolated laboratory.
The pinned Rust toolchain/build stack is unchanged from the CPU campaign.

Both timed workloads contain all 30 original replicates, use 23 states
(`-p 4+5*3+4`), 30 EM iterations, `-t 15 -r 4 -I 0`, CPU auto SIMD and cache on.
The original input is `tests/fixtures/blocks.psmcfa`, seed 20261009. The model-based
input is `tests/fixtures/cpu-campaign-hmm/blocks-4000.psmcfa`, seed 20261011.
Vanilla uses the exact pre-materialized bootstrap inputs corresponding to those
seeds. It runs up to the same number of independent processes concurrently.
Rust uses one process with that many independent workers and a 2048 MiB admission
budget. Every Rust run selected AVX and admitted the requested worker count.

## Full-batch measurements

Scaling uses one warmup plus three measured batches per configuration. Values are
median wall seconds; all measurements and ranges are in `bench/parallel-scaling.json`.

| Workers / affinity | Original | Model-based |
|---|---:|---:|
| 1 / all logical CPUs | 6.965 | 19.012 |
| 4 / all logical CPUs | 1.869 | 5.191 |
| 8 / all logical CPUs | 1.152 | 3.196 |
| 10 / all logical CPUs | 1.108 | 2.934 |
| 16 / all logical CPUs | 0.955 | 2.670 |
| 10 / physical representatives | 0.995 | 2.931 |

The 1-to-16-worker scaling ratios are 7.29x and 7.12x. These are comparisons with
single-worker Rust, not with parallel vanilla. Using more workers also increases
aggregate CPU time: original 6.961 to 12.308 seconds and model-based 19.002 to
35.392 seconds. The choice optimizes elapsed time rather than total CPU cost.

Paired comparisons use one warmup plus five measured batches per variant, rotating
variant order. Values below are median [minimum, maximum] wall seconds. Warmups
are retained but excluded from summaries. The report status `passed` means the
run and exactness checks passed; it does not mean the candidate was accepted.

| Dataset / workers | Existing Rust | Experimental balanced | Parallel vanilla |
|---|---:|---:|---:|
| original / 16 | 0.977 [0.940, 1.013] | 1.094 [1.073, 1.105] | 1.694 [1.568, 1.702] |
| original / 10 | 1.141 [0.994, 1.159] | 1.197 [1.177, 1.198] | 1.850 [1.683, 1.892] |
| model-based / 16 | 2.720 [2.679, 2.859] | 2.986 [2.949, 3.152] | 7.539 [7.390, 7.687] |
| model-based / 10 | 2.982 [2.866, 3.049] | 3.218 [2.975, 3.232] | 8.354 [8.082, 8.450] |

| Dataset / workers | Rust CPU s / RSS KiB | Balanced CPU s / RSS KiB | Vanilla CPU s / RSS KiB |
|---|---:|---:|---:|
| original / 16 | 12.312 / 15416 | 12.594 / 14224 | 20.776 / 45080 |
| original / 10 | 9.181 / 11588 | 9.714 / 10844 | 15.092 / 28292 |
| model-based / 16 | 35.810 / 47156 | 37.585 / 46668 | 98.608 / 67068 |
| model-based / 10 | 26.251 / 31984 | 27.530 / 34272 | 73.052 / 42284 |

Wall time includes launch, bootstrap preview where applicable, fitting, and file
output; it excludes post-run validation. CPU time sums child user/system time.
RSS is sampled at 10 ms and summed across concurrently live processes; it is a
lower bound on aggregate peak, excludes the Python controller, and is not a hard
memory guarantee. Rust threads share one process; C uses separate processes.
CPU/RSS ranges, commands, affinities, host load and all input/binary hashes are in
`bench/parallel-candidate.json`. No seeds or measurements were discarded.

## Correctness and rejected experiment

The balanced queue previews samples using a separate RNG, orders estimated work
by distinct observation length when caching, then fits each replicate with its
original fresh RNG and ordered samples. The derivation is in
`docs/parallel-scheduling-derivation.md`. Input length does not capture optimizer
callback work or heterogeneous-core scheduling; that is a possible explanation
for its poor prediction, not an established causal diagnosis. All four medians
are worse than the existing queue. Production retains forward/reverse only.

The scaling suite checked 1,440 fit outputs; paired timing checked 2,160 outputs.
Every output matches its pinned C oracle byte-for-byte except the honest version
line. The 60 distinct timed fits retain 56 finite outcomes and four C pathologies:
original replicates 16/26/28 and model-based replicate 20. Pathology parity does
not establish valid inference, and repeated timing runs are not new unique cases.

A separate seeded C gate checks 300 experimental fits: 30 seeds each at 23 and
64 states with `-N 2 -I 0.1`, across 1/4/16-worker balanced CPU configurations,
16-worker reverse scalar CPU/cache-off, and 16-worker forward dense/cache-off.
Outputs and draw traces match exactly across those configurations. A 1 MiB budget
rejects before output creation; 21 MiB admits one worker for the two-replicate
control even when 999 were requested. These checks are in
`bench/parallel-validation.json`. The candidate's 33 unit tests pass in both debug
and release profiles; the production numerical sources remain unchanged, retaining
the previous release's full internal snapshot gate. No tolerance was relaxed.

## Use and reproduction

From the project directory, this is the tested full-core synthetic example. Use a
new output directory for each run and preserve your actual preprocessing/settings
when applying the runner to real input:

```sh
bin/psmc-rs bootstrap --backend cpu --workers 16 --replicates 30 \
  --memory-mib 2048 --seed 20261009 --output-dir work/bootstrap-parallel \
  -p '4+5*3+4' -N 30 -t 15 -r 4 -I 0 tests/fixtures/blocks.psmcfa
```

The worker default already requests available CPUs. Admission also considers the
memory estimate and replicate count; inspect `manifest.json` for actual workers.
The memory estimate is not an OS-enforced cap. Each input record must already be
an intended independent sequence; this runner does not split inputs.

Actual commands used for the new evidence:

```sh
python3 bench/parallel_benchmark.py --mode scaling
python3 bench/parallel_candidate.py
# In generated work/parallel-candidate-v2:
cargo fmt --all
cargo test --locked --offline --workspace --jobs 16 -- --test-threads=16
cargo test --release --locked --offline --workspace --jobs 16 -- --test-threads=16
cargo build --release --locked --offline --jobs 16
# Copy generated executable to bench/parallel/candidate, then from project root:
python3 bench/parallel_validate.py --candidate bench/parallel/candidate
python3 bench/parallel_benchmark.py --mode candidate --candidate bench/parallel/candidate --repeats 5
```

Runners require Linux `/proc`, the preserved frozen binaries, and rebuilt pinned C
references in `work/vanilla` and `work/instrumented` (see existing reference build
scripts). Their raw command arrays record the exact settings. The experimental
generator expects a fresh scratch destination and the unchanged 0.3.1 sources;
it does not mutate production crates. The timing matrix targets this host's
16-logical/10-physical topology. Reproduction on different hardware needs an
appropriate worker/affinity matrix and does not inherit these speed claims.

## Delivery and remaining limits

Changes comprise benchmark/validation/generator runners and reports, the scheduling
derivation, this report, README, EXECPLAN, packaging metadata and the evidence
archive. No production crate changes or version bump are warranted. Source,
experimental test, derivation and timings share commit `65d1d87`; package manifests
and every-member checksums identify the portable delivery independently of Git.
The new `../psmc-rust-parallel.zip` preserves all prior archives. The rejected
candidate is evidence only; `bin/psmc-rs` is the retained release.

This milestone does not establish a 10x advantage over parallel C or a universal
optimal worker count. Real user data/settings, whole-genome memory, full K64/N30
parallel timing, ARM/NEON, AVX-512, physical non-AVX machines and CUDA remain
untested here. No private genome was used. The next useful optimization milestone
is representative production batch profiling, including larger inputs and memory
pressure, or full K64 parallel timing. Within-sequence parallel numerics would
require a separate exactness derivation before implementation.

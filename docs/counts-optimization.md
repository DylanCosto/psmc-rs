# Ordered K64 counts and bounded workspace growth

## Contract and derivation (before promotion)

Baseline is v0.3.1 at bdd1a43, executable SHA256
b0fc39d7c31637221de1152fc0d502bb65c90d0a5b9d6672250fe3117f75bfa4.
The external source remains lh3/psmc 82fa2ada83ee463fe1251b562ae3d60e82d7ad6a,
`khmm.c::hmm_expect`. Its recurrence for each transition count is

```
c[k,l] = 1e-25
for u = 1 .. L-1, in ascending order:
    c[k,l] = c[k,l] + ((f[u,k] * ae[obs[u],k,l]) * b[u+1,l])
```

Here observations use Rust's zero-based indexing and messages retain the original
one-based site rows. Products `ae` are the unchanged rounded emission-transition
products. For fixed k,l, changing when other cells are visited cannot change this
recurrence. A register tile loads the existing count, executes the same two
multiplications and one addition for each ascending site, and stores the count.
The next tile resumes that exact rounded f64 value. No tile subtotal is formed or
added, and no contribution is reordered. Sixteen adjacent destinations occupy
four independent AVX registers. There is no cross-lane reduction or fused
multiply-add. Emission counts can be evaluated in their own ascending-site pass:
they do not read transition counts. Initial-state counts and the full Q entropy
normalizer are unchanged. The final site remains omitted from transition and
emission counts, and all missing observations and repeated blocks remain present.

The safe wrapper validates a nonempty observation sequence, every symbol in 0..2,
checked message dimensions, exactly 4096 count cells, and 12288 product cells.
Runtime AVX capability guards the isolated unsafe function. Only exactly 64-state
AVX workspaces dispatch to this kernel; other shapes and forced scalar execution
retain their existing paths. Tiles are solely loop scheduling: no new HMM starts,
sequence splitting, fit parallelism, model approximation, or optimizer change.

The memory candidate calls `reserve_exact(needed - len)` only if needed exceeds
capacity, before the existing resize. It changes no element, length or numerical
operation. It avoids Vec's amortized doubling when a later bootstrap block is
slightly larger. Existing capacity remains reusable after shorter records. The
allocator may provide more storage than requested; this is not a hard memory cap.
Successively increasing record lengths can trigger more reallocations than
geometric growth; the measured bootstrap workloads, not arbitrary length
distributions, establish the performance scope.

## Predeclared evaluation

`bench/counts_campaign.py` freezes the baseline and builds four isolated variants:
memory only, memory plus fixed K64 count loops, and memory plus site tiles of
8 or 32 sites with 16 destinations in registers. Debug/release workspace tests
must pass before a screen. Tests include scalar per-cell comparisons at tile
boundaries, nonfinite classes, signed zeros, subnormals and unaligned buffers;
complete HMM workspace comparisons remain in the existing suite.

Screen all candidates using the complete K64/N30 human bootstrap 01 (previously
selected by maximum optimizer evaluations), one warmup plus three rotated runs.
Check every output against retained pinned C and require finite inference.
This selection fixture is not sufficient for promotion. Any survivor must pass
complete internal/C regression and all 30 human bootstraps in repeated matched
16-worker batches against frozen v0.3.1, plus K23 controls. Retain rejected variants
and measured results. No historical report is rewritten to describe a new build.

Hardware scope remains this Linux x86-64 AVX host. ARM/NEON, GPU, whole-genome input
and the user's actual workload are not tested by this milestone.

## Accepted results: v0.3.2

The eight-site K64 transition-count kernel and exact-capacity message growth are
accepted together. Baseline v0.3.1 is preserved as `bin/psmc-rs-v0.3.1`; the accepted
binary is `bin/psmc-rs`, SHA256 `24d47084c2914aa44109040b7f5593efb7353621cb0d36ccdb28cd1a060f4c83`. The baseline source commit is
bdd1a4309502251f78ced5085f5d7aa498a200de. `bench/counts-build.json` records exact
source hashes, compiler, flags and linked libraries. Numerical changes, derivation,
isolated tests and measured evidence are committed together.

On the public HG001 chromosome 22 workload, the complete 30-bootstrap batch used
**27.5% less wall time (1.379x throughput)**
than the previous Rust release. Sampled peak RSS changed by
-0.02%: this campaign does **not establish a resident-memory
benefit** from exact-capacity growth. Both releases use 16 workers, the same 30 seeds, 64 states and 30 EM
iterations. All fits and validation steps complete; no problematic seed is omitted.

| Workload | Release | Wall median [min,max], seconds | CPU median, seconds | RSS median, MiB |
|---|---|---:|---:|---:|
| human | baseline | 69.150 [65.677, 69.909] | 905.708 | 1285.6 |
| human | candidate | 50.155 [50.132, 52.941] | 669.228 | 1285.3 |
| original | baseline | 1.000 [0.975, 1.004] | 12.373 | 15.1 |
| original | candidate | 1.015 [0.989, 1.104] | 12.434 | 15.0 |
| model-based | baseline | 2.797 [2.772, 2.855] | 35.976 | 46.2 |
| model-based | candidate | 2.891 [2.794, 3.058] | 35.537 | 45.6 |

These are one warmup plus three alternating measured pairs per workload on the
shared Intel Core i5-12600K host, using all 16 allowed logical CPUs. Wall time
includes scheduling and output. Peak RSS is sampled every 20 ms for human batches
and 10 ms for synthetic batches; it is a lower bound and excludes the controller.
K23 results are controls and do not imply a K64-kernel benefit at other state sizes.
Their measured wall medians were 1.5%
and 3.4% slower, respectively;
CPU medians changed little and ranges overlap. No K23 speedup is claimed.
A separate standard-Vec allocation diagnostic (`bench/counts-capacity.json`)
replays a 50,000-bin block followed by a 58,185-bin block. Per message buffer,
reported capacity changes from 51,201,024
bytes under the old growth rule to 29,791,232
bytes with exact reservation. This verifies tighter buffer capacity, not physical
RAM savings; untouched capacity need not appear in RSS. Successively increasing
record lengths can cause more reallocations than geometric growth.
Memory and kernel changes were measured as a combined release: the batch result
does not isolate their individual effects. Timing variability and three repeats
limit conclusions about small differences.

All **720 batch outputs** match retained pinned vanilla C numerical output exactly,
allowing only the honest version line. All 240 human outputs are finite. Original
synthetic batches retain their three pathological replicates and model-based
batches retain their one, exactly as C. Two additional complete unsplit chromosome
fits (baseline and candidate) also match C; their single-run times are correctness
controls, not repeated performance estimates. Bootstrap draws are independently
replayed and checked in every timed batch. The chromosome has 508,185 bins and
comes from the previously documented public smckit fixture; source provenance
and its limitations remain in `bench/hg-input.json` and the human-input report.
No human input is included in version control.

Acceptance checks: **35 debug and 35 release unit tests**; **340 complete regression
cases** across dense, CPU/AVX and forced scalar, including ordered internal f64
snapshots; all **66 extended fixtures** (39 finite and
27 pathology controls); serial forward/reverse
30-bootstrap scheduler and cache controls; **38 CLI/dispatch
checks**. Lints completed with advisory style warnings. Whole-binary assembly
inspection found zero FMA and zero horizontal-reduction instructions. Runtime AVX
selection and non-AVX scalar fallback remain intact; absent-AVX behavior is simulated
in unit tests, not tested on a separate machine.

The isolated screen retained all four candidates and all 20 complete fit results.
Median seconds: baseline 14.271,
memory only 14.669,
fixed K64 13.790,
eight-site tile 10.548,
32-site tile 12.385.
The eight-site candidate advanced based on the screen and then passed the complete
release gates above. Other kernels were not promoted. Single-fit screens allowed
OS scheduling across available CPUs; the matched full-batch measurements support
the release decision. The regenerated candidate source hashes match all saved
screen source hashes (`bench/counts-generator.json`).

### Reproduction and scope

Commands actually run are retained in `bench/counts-gates.json`,
`bench/counts-screen.json` and `bench/counts-batches.json`. Main entry points:

```
python3 bench/counts_campaign.py build
python3 bench/counts_campaign.py screen
python3 bench/counts_campaign.py verify_generator
python3 bench/counts_gates.py
python3 bench/counts_batches.py --candidate target/release/psmc-rs
python3 bench/counts_capacity.py
python3 bench/counts_report.py
```

Runners use fresh output directories and intentionally reject overwriting existing
raw evidence. The build/screen generator checks out the pinned baseline source;
its earlier build-runner hash predates screen/report plumbing repairs, while the
current generator is independently checked against every candidate source hash.
The final release build and gate runners have their own hashes. Historical C and
v0.3.1 reports are preserved unchanged. No C speed ratio is newly claimed here:
C output references are reused, but C timing was not repeated in this campaign.
The 10x goal remains unproven. ARM/NEON, GPU, whole genomes and the user's actual
workload remain untested. No approximation, changed model, FMA, altered optimizer
or additional HMM boundary is introduced.

Next permitted milestone: profile this accepted release on a whole-genome input
or a well-documented larger public workload before choosing further CPU work.
Per-fit reductions must remain ordered, and any next kernel must repeat the same
compatibility and complete-workload performance gates.

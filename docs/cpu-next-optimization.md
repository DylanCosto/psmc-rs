# CPU headroom campaign against v0.3.2

Baseline commit 4ab9ff5; Linux x86-64, Rust 1.90.0, portable release profile.
The executable is frozen and hash checked by the runners. No production edits
are made during candidate generation. Full-core execution is authorized only
for independent fits; per-fit arithmetic remains ordered and single-threaded.

## Derivation recorded before experiments

Every transition count cell follows C[u+1] = C[u] + ((f[u,k] * ae[z,k,l]) * b[u+1,l]),
starting at the original tiny initializer and visiting u in ascending order.
Widening a destination block from 16 to 32 changes only which independent cells
are kept in registers simultaneously. Four- and eight-site blocks still carry
the final accumulator into the following block without a partial reduction.
Each 4-lane load stays within a 64-cell row because l+31 <= 63. Observation and
message shapes remain checked by the existing capability wrapper.

Forward/backward width 32 similarly widens independent destination groups:
each accumulator starts at positive zero and visits all 64 source states in
ascending order, with the same multiply operand order. Emission multiplication
and scale division remain outside the sum. No horizontal reduction, FMA or
approximate arithmetic is allowed. The original scalar and generic paths remain.

The allocation control removes only exact reservation and uses the existing
Vec resize behavior. Logical lengths, initialized values and arithmetic remain
unchanged. The dispatch control moves the K64-only emission loop outside the
per-site generic branch. Each emission cell still adds (f*b)*scale in ascending
site order; transition and emission cells do not depend on one another.

Existing isolated differential tests exercise all states/tails, finite bits,
signed zero/subnormals, nonfinite classes, unaligned buffers, tile boundaries,
shape rejection and repeated workspace use. Both debug and release suites must
pass for every generated variant before full N30 screens. Final promotion also
requires the full internal/C trajectory gates and complete bootstrap timings.

## Fresh profile

bench/cpu-next-profile.json contains three instrumented repetitions per input,
with exact C output checks. HG001 unsplit median process CPU is 16.94 s: forward
3.80 s, backward 3.28 s, transition counts 6.53 s, other counts 0.60 s. Bootstrap
01 gives 10.73 s total, 2.07/1.97/3.53/0.39 s respectively. These overlapping
instrumented sections guide experiments; they are not release speed estimates.
K23 fits spend most time in Q/model construction, limiting kernel headroom.

## Decision

The completed decision and measured evidence appear below.

## Larger held-out input provenance

[GIAB release README](https://ftp-trace.ncbi.nlm.nih.gov/ReferenceSamples/giab/release/AshkenazimTrio/HG002_NA24385_son/NISTv4.2.1/README_v4.2.1.txt)
explicitly documents confident homozygous-reference calls alongside variants and
requires VCF/BED together. [NIST's GIAB FAQ](https://www.nist.gov/programs-projects/faqs-genome-bottle)
identifies HG002 as a public PGP sample with broad consent. We retain local hashes,
source URLs and synthetic converter tests in bench/cpu-next-hg002-input.json.
No raw human input is included in the commit or release. No separate license
file was supplied for these VCF/BED objects; this benchmark uses the public data
locally and makes no redistribution claim.

The held-out fixture is the full GRCh38 chr1, 248,956,422 coordinates in one record,
encoded to 2,489,565 bins. Homozygous state exists only inside the confidence BED;
called PASS diploid SNVs supply heterozygous state. Complex/non-PASS/missing-GT
reference spans plus five flanking bases are excluded before assigning SNPs.
These conservative, fixed benchmark filters introduce ascertainment and are not
a recommended population-history analysis pipeline. Synthetic tests verify
coordinate edges, indel overlaps, missing GT, multiallelic GT, strict >90 missing
threshold and partial tails against the original C fq2psmcfa. The original
converter retains its unusual denominator-100 rule even for the final partial bin.

## Initial screening decisions

All five generated variants passed debug/release differential suites (35 tests,
except 34 for the allocation-removal control whose obsolete reservation-only
test was removed). All 72 full-fit screen outputs match retained C. HG001 fit
medians in seconds: baseline 10.9820; counts32/sites8 10.7838; counts32/sites4
11.1270; messages32 10.6399; noreserve 10.9760; dispatch 11.0285. Ranges overlap
and a later screen round slowed across candidates; shared-host frequency/load
variation limits interpretation. No isolated screen is a release claim.

Counts32/sites4, allocation removal and outer dispatch are rejected at screening.
K23 original/bootstrap medians for allocation removal were 0.2557/0.2172 versus
baseline 0.2518/0.2158, with overlapping ranges; reverting reservation does not
explain or fix the previously observed small parallel K23 slowdown. Wider K64
messages and counts32/sites8 advance to a combined confirmation before full
batch acceptance. Their changes act on independent stages, but speedups must
be measured together rather than added arithmetically.

## Combined confirmation

The independent confirmation retained one warmup and three rotated measurements
for baseline, messages32, and combined messages32/counts32-sites8. All 12 outputs
match C. Wall medians [min,max] seconds are 10.1171 [10.0637,12.1174], 9.8745
[9.8670,9.8853], and 9.7782 [9.7257,9.7828]. The combined candidate advances to
full gates; this 3.35% screen difference is not yet a complete-batch release result.
The provisional v0.3.3 production source is exactly the combined generated SIMD
source, plus version metadata. Reservation, dispatch, K23 kernels and scheduling
remain unchanged. The published executable stays v0.3.2 until acceptance.




## Final measured decision

Accept v0.3.3: widen K64 forward/backward and eight-site count blocks to 32 independent destinations.

The candidate SHA256 is `f0c3282e87e3eed0cc31c63a438429c19ad47cedec4c56c1150cc8520838e305`. Frozen v0.3.2 SHA256 is `24d47084c2914aa44109040b7f5593efb7353621cb0d36ccdb28cd1a060f4c83`. Baseline source commit is 4ab9ff5; exact candidate source, Rust 1.90.0 compiler/profile and linked libraries are in bench/cpu-next-build.json. The milestone commit contains the implementation, reproducible candidate generators, proofs, tests and measurements together.

Complete HG001 chromosome 22 batches use all 30 fixed bootstraps, K64 and N30. The repeated paired comparison uses **16 workers** with affinity `[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]` for both binaries. There is one warmup and three alternating measured pairs per workload. Because the first two human pairs disagreed, a fixed second block added one warmup and three opposite-order pairs; the human row pools all six measured pairs. Human median wall reduction is **2.09%**, throughput ratio **1.0213x**, and median total CPU reduction **2.81%**. These are shared-host measurements on the Intel Core i5-12600K, not guarantees on other systems. Ranges overlap; six paired batches support a limited measured comparison, not a formal significance claim.

| Workload | Binary | Wall median [min, max], s | CPU median, s | Sampled peak RSS median, MiB |
|---|---|---:|---:|---:|
| human | baseline | 51.289 [49.705, 53.185] | 674.953 | 1285.5 |
| human | candidate | 50.218 [48.712, 51.697] | 655.979 | 1285.4 |
| original | baseline | 0.992 [0.970, 1.124] | 12.370 | 15.2 |
| original | candidate | 1.001 [0.982, 1.019] | 12.480 | 15.1 |
| model-based | baseline | 2.874 [2.822, 2.903] | 37.200 | 45.8 |
| model-based | candidate | 2.863 [2.776, 2.947] | 38.216 | 45.6 |

All six human paired effects are retained below; positive values mean the candidate used less time. No run is dropped for being slow.

| Block | Pair | Wall reduction % | CPU reduction % |
|---|---:|---:|---:|
| primary | 1 | -2.07 | 3.31 |
| primary | 2 | 4.44 | -2.91 |
| primary | 3 | 3.50 | 2.66 |
| confirmation | 1 | 5.18 | 3.71 |
| confirmation | 2 | 0.77 | 1.41 |
| confirmation | 3 | 1.03 | 3.70 |

K23 rows are controls: these changes specialize only K64. Small K23 timing differences and overlapping ranges do not establish an improvement at other state counts. Allocation and dispatch experiments did not explain the earlier minor K23 slowdown; those production paths remain unchanged. No resident-memory reduction is claimed. RSS is sampled every 20 ms for human batches and 10 ms for synthetic batches, excludes the controller, and is a lower bound on peak live-process RSS.

### Worker screen

Each row below is one complete 30-bootstrap screen, not a repeated scaling estimate. The 10-worker case uses one logical CPU per physical core; 8 and 16 use all allowed CPUs. Worker count and affinity therefore change together. The common confirmation configuration was selected by the lowest mean of both releases' screen wall times, then tested again on fresh repeated batches.

| Workers | Binary | Wall seconds | Total CPU seconds |
|---:|---|---:|---:|
| 8 | baseline | 59.752 | 422.386 |
| 8 | candidate | 58.589 | 411.309 |
| 10 | candidate | 52.054 | 464.322 |
| 10 | baseline | 52.829 | 476.701 |
| 16 | baseline | 50.331 | 679.296 |
| 16 | candidate | 49.064 | 649.832 |

### Larger held-out chromosome

The full HG002 GRCh38 chromosome 1 fixture has 2,489,565 bins and stays one continuous HMM record. All three full N30 fits are finite, and both Rust outputs exactly match pinned vanilla C apart from the version line. Single descriptive runs follow; **they are not repeated speed estimates**.

| Binary | Wall seconds | Peak RSS, MiB |
|---|---:|---:|
| vanilla | 272.762 | 2573.8 |
| baseline | 69.434 | 2456.0 |
| candidate | 65.700 | 2456.1 |

This is one chromosome, not a whole genome. Fifty upstream splitfa blocks and 30 fixed seeds are prepared for future HG002 bootstraps; those 30 fits were **not run**. The repeated acceptance workload remains HG001. Raw public human data are local ignored files and are not redistributed.

### Exactness, reproduction and limitations

All 35 debug and 35 release unit tests pass, as do 340 complete dense/CPU/scalar regression cases with ordered intermediate snapshots; 66 extended cases (39 finite, 27 reference-pathology controls); scheduler/cache checks; and 38 CLI/dispatch checks. Assembly inspection has zero FMA and horizontal-reduction instructions. The audit regenerates all six experiment source variants from the pinned baseline and verifies every source hash.

The delivery audit rechecks **1241 outputs**: 12 profile outputs, 72 isolated-screen outputs, 12 combination outputs, 180 worker-screen outputs, 240 confirmation outputs, 720 primary batch outputs, two HG001 unsplit outputs and three HG002 unsplit outputs. All 720 primary batch outputs, 240 confirmation outputs and 180 worker-screen outputs exactly match retained C references. Every bootstrap draw is independently replayed; no seed, repeated block or pathological reference result is removed. All 480 human primary/confirmation outputs are finite; original/model-based synthetic batches retain three/one pathological replicates respectively.

Production changes are confined to crates/psmc-cpu/src/simd.rs and version metadata in Cargo.toml, Cargo.lock and the CLI. Benchmark scripts/reports, this derivation and EXECPLAN.md record the campaign. Dense arithmetic, K23 kernels, the statistical model, optimizer, grids, counts, missingness, input boundaries and task queue are unchanged. No new dependency or architecture requirement is introduced. Runtime AVX selection and scalar fallback remain.

Commands actually run are retained with hashes in the JSON reports. Reproduction entry points (new raw directories are required to avoid overwriting evidence):

```bash
python3 bench/cpu_next_fetch.py
python3 bench/cpu_next_hg002.py
python3 bench/cpu_next_profile.py
python3 bench/cpu_next_candidates.py build
python3 bench/cpu_next_candidates.py screen
python3 bench/cpu_next_combine.py
python3 bench/cpu_next_gates.py
python3 bench/cpu_next_large.py --candidate target/release/psmc-rs
python3 bench/cpu_next_scaling.py --candidate target/release/psmc-rs
python3 bench/cpu_next_batches.py --candidate target/release/psmc-rs
python3 bench/cpu_next_confirm.py
python3 bench/cpu_next_audit.py --decision promote
python3 bench/cpu_next_report.py
```

Profile instrumentation and candidate generators are baseline-specific; run their preparation from v0.3.2 as recorded. Final release gates use the accepted candidate source. Published executable copying is performed only after checking the measured decision. Raw evidence stays in ignored work/cpu-next* and the legacy validation directories. Earlier releases, archives and reports remain intact.

ARM/NEON, GPU, whole-genome bootstrap throughput and the user's own data remain not_run. The 10x target remains unproven. No renewed whole-batch C speed ratio is claimed: canonical C outputs were reused for HG001, while HG002 has only one new C fit. Hardware counters are unavailable on this host; the profile uses disposable CPU-time instrumentation.

Next permitted milestone: whole-genome or user-workload validation and profiling before another optimization campaign. This campaign supports a small additional CPU gain on the measured workload, not a claim that all possible CPU optimization has been exhausted.

The confirmation decision rule was recorded before its measurements: at least 2% pooled median human wall reduction, lower median CPU time, and positive paired effects in at least four of six comparisons for each metric. It is a practical release rule, not a statistical significance claim. All four conditions passed.

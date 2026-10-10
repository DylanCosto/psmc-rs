# Phase 2 CPU engineering and deterministic bootstrap execution

This milestone adds a strict CPU backend and a bounded bootstrap runner while
retaining the scalar dense Rust implementation and pinned C executable as
independent references. It changes storage layout, storage lifetime and scheduling
of independent fits. It preserves the existing model, sequence boundaries, full
expected counts, objective, optimizer callback sequence and output calculations.
The upstream reference remains `lh3/psmc` commit
`82fa2ada83ee463fe1251b562ae3d60e82d7ad6a`; the tested Rust toolchain is 1.90.0.
The [reference contract](reference-contract.md) and
[compatibility policy](../MATH_AND_COMPATIBILITY.md) remain applicable.

This document explains the final implementation and its isolated evidence. It
does not infer an end-to-end speedup from kernel measurements. Complete run and
scheduler results are maintained separately in
[the validation report](../bench/phase-2-validation.json) and
[the scheduler report](../bench/phase-2-scheduler.json).

## Implementation boundaries

| Component | Dense reference | CPU implementation |
|---|---|---|
| Scaled messages and full expected counts | `psmc-core/src/hmm.rs` | `psmc-cpu/src/lib.rs`: `PreparedModel` and `Workspace` |
| Model construction for candidate parameters | `psmc-core/src/model.rs`: `Model::update` | `psmc-core/src/model_workspace.rs`: `ModelWorkspace::update` |
| Ordered expectation across records | `DenseBackend` in `psmc-core/src/em.rs` | `CpuBackend` in `psmc-cpu/src/engine.rs` |
| Full-count normalizer, Q and Hooke–Jeeves | Existing core routines | Same core routines |
| Bootstrap records and RNG | Existing parser, encoding and sampling rule | Borrowed source indices through `resample_indices` |
| Bootstrap execution | Independent single-fit command remains available | `psmc-cli/src/batch.rs`: one scoped thread pool |

`--backend dense` selects the oracle. `--backend cpu` selects these engineering
changes, and `--cache off` disables repeated-record reuse for comparison. The
implemented numeric mode remains `strict`, using binary64 throughout. There is
no structured transition factorization, approximate pruning, changed optimizer,
BLAS pool or CUDA path. Records within one fit are evaluated serially; the new
pool parallelizes complete independent bootstrap fits.

## Model construction: reusable scratch, unchanged calculation

The literal model update uses six temporary vectors: lambda (`K`), alpha (`K+1`),
beta (`K`), q_aux (`K-1`), q (`K`) and tau (`K`). Their total payload is `6K`
binary64 values, or `48K` bytes. At K=64 this is 3,072 bytes, excluding vector
headers and allocator metadata. `ModelWorkspace` allocates these buffers once
per fit and retains them across candidate evaluations.

Every value consumed during an update is written during that update. Lambda and
tau are filled over all states; alpha receives both endpoint values and every
interior recurrence; beta starts from zero and fills the remaining entries;
q_aux covers every entry that can be read; each row computation writes all q
entries before using them. Thus no clearing or retained numerical value is needed
between candidates. An invalid candidate cannot leave scratch values that affect
a later valid candidate.

The workspace routine deliberately duplicates `Model::update`, preserving its
parentheses, loop order, platform `log`/`exp` calls, divergence handling, time-grid
endpoint, fallback average time and dense transition/emission formulas. Exact-size
safe slices expose lengths to the optimizer once per call; no unchecked indexing
or arithmetic reassociation is introduced. The missing-symbol emission row is
left unchanged in both routines. The dense function remains independent.

The [model-workspace derivation and reproducer](../bench/phase-2-model-workspace/README.md)
and [recorded results](../bench/phase-2-model-workspace/results.json) cover 60 model
cases against unchanged Rust and retained pinned C: all 64,446 values are
byte-exact. Additional tests perform 360 candidate updates with NaN-poisoned
scratch, invalid-to-valid recovery and stable buffer pointers. A separate
single-thread allocation probe observes 6,000 dense allocations and zero workspace
allocations for 1,000 K=64 updates. This does not imply allocation-free inference:
prepared matrices, caches, count copies and message-capacity growth still allocate.

## HMM buffers: the same ordered binary64 operations

Let K be the number of states, L the length of one existing record, `z[u]` its
encoded observation at one-based position u, A its transition matrix, E its
symbol-major emission matrix, and pi its initial distribution. Missing observations
have their existing encoding and emissions; they retain transitions. Each record
restarts the HMM at pi. No record is split into computational tiles.

`PreparedModel` borrows the current model immutably and constructs these arrays:

```text
AT[k,l] = A[l,k]                   // exact copy
AE[z,k,l] = E[z,l] * A[k,l]        // same operand order as the oracle
```

The dense oracle constructed its transition transpose separately for each record.
The CPU path constructs it once per expectation call. A borrow prevents mutation
of the model while the prepared arrays are in use. Both prepared arrays are
recreated for the next expectation call; no stale parameter-derived values are
reused after an M-step.

`Workspace` retains flat forward, backward, scaling and count buffers. It resizes
their logical lengths for the current record while retaining capacity. Row zero
is reset, scale zero remains one, and every other used cell is overwritten before
reading it. Growing and then shrinking a record therefore cannot expose stale
message cells to calculation or snapshot output.

Forward initialization keeps the exact sequence of operations:

```text
for k ascending: F[1,k] = pi[k] * E[z[1],k]
s[1] = ascending sum of F[1,k], starting from 0.0
for k ascending: F[1,k] /= s[1]
```

For u=2 through L, each destination state uses an ascending source-state dot
product, then contributes to the scale in ascending destination-state order:

```text
tmp = 0.0
for l ascending: tmp += F[u-1,l] * AT[k,l]
F[u,k] = E[z[u],k] * tmp
```

After all destinations, the cells are divided by the same ordered scale sum.
Using row slices and zipped iterators changes addresses and bounds checks; it does
not reorder the additions inside a dot product or scale. Forward arithmetic
therefore follows the same recurrence in binary64, not merely in real arithmetic.

Backward initialization remains `B[L,k] = 1.0 / s[L]`. Sites are visited from
L-1 down to 1. For each source state k, `tmp` starts at zero and accumulates
`AE[z[u+1],k,l] * B[u+1,l]` in ascending l; the result is divided by `s[u]`.
The backward diagnostic preserves the operand grouping
`(pi[k] * B[1,k]) * E[z[1],k]` and ascending state order.

Likelihood keeps the original grouped product of scales. It multiplies scales
in ascending site order and adds `log(product)` only when the product is below
`1e-25` or at least `1e25`, resetting it to one after each such addition. It then
adds the log of the residual product. Summing a logarithm separately at every site
would change rounding and is not used.

Per-record initial-state counts start at zero. Every transition and emission
count cell starts at `1e-25`. For u=1 through L-1, each count cell receives the same
addends in the same site order:

```text
A_count[k,l] += (F[u,k] * AE[z[u+1],k,l]) * B[u+1,l]
E_count[z[u],k] += (F[u,k] * B[u,k]) * s[u]
A0_count[k] += (pi[k] * E[z[1],k]) * B[1,k]  // once, into zero
```

The final site's emission contribution remains omitted. Different count cells
are independent, so contiguous traversal may expose independent work to the
compiler while retaining the addition sequence within each cell. Initial-state
counts remain recorded but excluded from Q. Aggregate missing-symbol emission
counts remain omitted. The full-count entropy normalizer and normalized dense Q
are unchanged, including invalid-probability handling and NaN propagation.

The [HMM derivation](../crates/psmc-cpu/README.md) and
[workspace tests](../crates/psmc-cpu/src/tests.rs) compare all messages, scales,
likelihoods, diagnostics and counts. Coverage includes all 3,279 observation
strings of lengths 1–7, 1/2/4/23/64 states, explicit grids, divergence, missing
runs, buffer growth/shrinkage, repeated singleton records and nonfinite inputs.
Finite values, signed zero and infinity signs must match binary64 bits; paired
NaNs are classified separately. Exact behavior remains a tested property of the
pinned execution stack, not a universal compiler or architecture guarantee.

## Exact repeated-record caching

For a fixed model M, define `S(M,x)` as the complete per-record count arrays,
likelihood and backward diagnostic produced for encoded byte string x. Evaluation
has no record-name dependence. Two occurrences with exactly equal encoded bytes
and equal length therefore produce the same result under the same model and
backend. The CPU engine uses borrowed `&[u8]` keys: hashing finds candidates, and
full slice equality resolves collisions. A hash collision alone cannot declare
two records equal. Different record names may share computation because their
names are still preserved separately for output.

An occurrence prepass identifies repeated strings. Only strings occurring more
than once receive retained count arrays. The first occurrence is evaluated and
its statistics copied into a local cache; later occurrences retrieve those
statistics. Neither observations nor full message arrays are copied into the
cache. The immutable model, fixed binary64 backend and complete cache lifetime
are confined to one `expectation` call. At return the cache is dropped, so it
cannot cross an M-step, EM iteration or replicate, even if two calls happen to
have equal parameter vectors. This lifetime is the parameter/precision boundary;
a persistent cache with a weaker key has not been introduced.

Caching removes evaluation, not observations. For original occurrence order
`x[0], ..., x[m-1]`, aggregate cell c still executes:

```text
aggregate[c] = 0.0
for i in original occurrence order:
    aggregate[c] += S(M, x[i]).counts[c]
```

Likelihood follows the same occurrence-order addition. In particular, three
copies are three successive additions, never `3 * value`. Cached transition and
emission arrays already contain the per-sequence `1e-25` initializers, so every
occurrence retains its own pseudocount contribution. `Counts::add` preserves the
original state/symbol order and missing-emission omission; the normalizer is
computed only after the complete aggregate. HashMap iteration order is never used
for arithmetic, output or scheduling. The backward diagnostic is replayed for
cached occurrences so the existing warning condition is retained.

Observers needing per-occurrence message arrays disable cache hits. The observer
trait defaults to this conservative behavior; only `NoObserver` declares that
callbacks may be skipped. Snapshot output therefore evaluates every occurrence
and preserves names, indices and arrays. Counters distinguish sequence visits,
actual evaluations, hits and visits that bypassed the cache for snapshot output.
The [cache unit test](../crates/psmc-cpu/src/engine.rs) compares ordered counts and
likelihoods across repeated names/bytes and three changed model snapshots.

The prepass and lookups hash observation bytes and allocate metadata. Fits with
few repeats may not benefit. `--cache off` retains the CPU buffers while removing
that work. No cache is shared across fits or inferred from approximate equality.

## Borrowed bootstrap records and deterministic RNG replay

`resample_indices` returns source-record indices in sampled occurrence order,
plus an explicit draw trace. The legacy materializing API delegates to the same
sampler; the CLI instead borrows references from the original encoded records.
Repeated indices remain repeated references and contribute repeatedly to total
length, initialization statistics and every expectation step. Record boundaries
and unequal terminal-block lengths remain unchanged.

The sampler preserves the original nearest-length stopping rule. With current
accepted length R, target T and proposed block length d, define `remaining=T-R`
and `excess=R+d-T`. Accept when excess is nonpositive, or when remaining and excess
are positive and excess is strictly smaller than remaining. Stop at the first
proposal that reaches or crosses the target. A rejected crossing proposal still
consumes its RNG draw. This is not a fixed number of sampled blocks. Empty records
are rejected and total bootstrap length is restricted to the original stopping
rule's defined signed-int range.

Each replicate r owns `LegacyRng(base_seed+r)`. The signed seed range is checked
before work starts; manifests store every seed. The POSIX/glibc-compatible state is

```text
x0 = ((seed as u32) << 16) | 0x330e
x_next = (0x5deece66d * x + 0xb) mod 2^48
uniform = x_next / 2^48
```

The same owned RNG then initializes model parameters after all bootstrap draws,
including a final rejected draw. Parameter initialization consumes its original
draws even at zero random amplitude. No worker-global RNG or shared draw stream
exists. Explicit `--seed` gives replayable runs; an omitted seed is chosen from
time/process state and recorded. As in the legacy RNG, only the seed's low 32 bits
initialize its state.

## One bounded pool of complete fits

The `bootstrap` command reads the source once, then starts one scoped pool of
workers. Each worker takes a unique queue position from an atomic counter, maps
that position to the configured forward/reverse replicate index, and executes one
complete fit with local RNG, model, optimizer and workspaces. Each fit evaluates
its records in their original sampled order. There is no nested numerical pool,
parallel floating-point reduction or scheduling-dependent accumulation.

Results enter a mutex-protected vector by replicate index. After workers finish,
the manifest is assembled in that index order, regardless of completion order.
Relaxed atomic ordering is sufficient for unique task assignment because the
counter publishes no model or result data; source/configuration are immutable and
result writes use the mutex. Scoped threads can borrow the shared source and are
joined before the scope returns. This follows the standard library's
[`thread::scope` contract](https://doc.rust-lang.org/std/thread/fn.scope.html).

Requested workers are capped by replicate count, estimated available parallelism
and the memory admission calculation below. `available_parallelism` is a runtime
estimate with platform limitations, not a measurement of current system load or
heterogeneous-core speed. An error falls back to one worker. See the official
[`available_parallelism` documentation](https://doc.rust-lang.org/std/thread/fn.available_parallelism.html).

Per-fit failures and caught panics are recorded without abandoning the remaining
jobs. The command returns failure after writing a complete result manifest if any
fit failed; partial outputs are retained. Process termination, thread-creation
failure or allocator abort are not recoverable through this mechanism. Diagnostic
stderr from separate workers may interleave; deterministic guarantees concern
numerical files, sample traces and ordered manifest content.

Single-fit `--stats` enables expectation/M-step phase timers and writes counters
alongside them. Batch jobs always write per-fit counter files, but currently leave
phase profiling disabled: `profile_enabled` is false and phase-time fields are
zero. Those zeros are not elapsed-time measurements. The manifest links each
successful replicate's output, draw trace and statistics and distinguishes failed
jobs from completed jobs containing nonfinite legacy output.

## Conservative memory admission

Admission is checked after input loading and before reserving the result vector
or creating the new output directory. It is not an OS-enforced RSS limit. Let R
be source-record count, P replicate count, T total raw length, Lmin/Lmax the
shortest/longest record, and K the state count. All arithmetic below uses checked
integer operations:

```text
Dmax = ceil(T / Lmin) + 1                  // conservative maximum draws
M = 8 * (Lmax + 1) * (2*K + 1)             // forward, backward and scales
C = 8 * (K*K + 4*K)                       // transition, emission and initial counts
sampled = Dmax * (3*sizeof(usize) + 2*sizeof(BootstrapDraw))
worker = 2*M + 4*R*C + 128*K*K + sampled + 16 MiB
results = P * (128*Dmax + 4096)
source_json = sum_records(12*name_byte_length + 256)
resident = encoded_input_capacity_bytes + results + source_json
workers = min(requested, P, available, floor(max(0,budget-resident)/worker))
```

The factors allow for vector growth, sampled indices/references/draw traces,
count-cache metadata, model/optimizer scratch, retained completed results and
concurrent JSON construction. Shared metadata is reserved separately from worker
storage; a large replicate count cannot evade admission merely by using one
worker. If no worker fits, execution is rejected before creating the directory.
Manifests expose input bytes, estimated metadata bytes, estimated worker bytes,
requested/admitted workers and the policy wording.

These bounds favor predictable admission over maximizing occupancy. Very unequal
record lengths can make Dmax pessimistic. Allocation overhead, OS/thread stacks,
input parser transients and system activity are not precise RSS accounting;
input must already be loaded to derive its shape. There is no spill-to-disk,
checkpointed HMM or hard memory controller. The workload still retains complete
forward/backward arrays for its longest record.

## Reproducible evidence and measured limits

The model [isolated timing report](../bench/phase-2-model-workspace/results.json)
uses seven alternating pairs of 200,000 candidate updates pinned to CPU 0. At
K=23, dense/workspace medians are 0.251381/0.221478 seconds (1.135×). At K=64 they
are 1.077188/1.068506 seconds (1.008×), effectively neutral within observed
variation. The initial unbounded-Vec version regressed; exact-length safe slices
resolved that regression. Its [exploratory results](../bench/phase-2-model-workspace/results-initial-unbounded.json)
remain retained and excluded from accepted timings.

The separate [HMM kernel report](../bench/phase2-kernel-benchmark.json) records five
alternating pairs: 0.204605/0.096944 seconds at K=23 (2.111×) and
1.315706/0.761758 seconds at K=64 (1.727×), dense/CPU. These time message/count work
on synthetic unequal-length records, not EM, bootstrap scheduling or original C.
Each process performs an exact comparison outside the timed section. The report
identifies its immutable executable and notes that only integration module exports
were appended to the crate after that build; its kernel body was unchanged.
Process wall time and RSS include the correctness warmup and are not isolated
backend-memory comparisons. Final integrated executable evidence is separate.

The [independent CLI review](phase-2-review.md) and
[17-control result](../bench/phase2-review.json) cover file preservation, alias
checks, worker/order invariance, seed replay, partial failures and invalid options.
A discovered all-missing input truncation regression was fixed and rechecked;
initial failure evidence remains linked. Memory-admission metadata was expanded
after the same review. No failed case was reclassified by relaxing numeric
comparisons.

Representative reproduction commands, from the project root, are:

```console
cargo test --workspace --locked
python3 bench/phase-2-model-workspace/check.py
python3 bench/phase2-review.py --binary target/release/psmc-rs
cargo build --release -p psmc-cpu --example kernel_bench
python3 crates/psmc-cpu/examples/measure_kernels.py
python3 bench/phase-2-model-workspace/check.py --benchmark --cpu 0 --iterations 200000
```

Run timing commands in an otherwise quiet window; rebuilding or running unrelated
fits concurrently invalidates a clean comparison. Reports retain commands,
compiler/source/binary hashes, raw measurements and exclusions. Full validation,
all 30 fixed bootstraps and the scheduler controls have their own harnesses:
[phase2_validate.py](../bench/phase2_validate.py) and
[phase2_scheduler.py](../bench/phase2_scheduler.py).

Real workload commands, input/masking provenance and intended worker budget remain
unprovided. The user's existing 30 bootstraps already run concurrently, so ordinary
pooling alone is not evidence of acceleration over that workflow. Synthetic
reference nonfinite cases remain pathology-parity tests, not valid-inference
successes. GPU execution, cross-platform exactness, a 10× end-to-end speedup,
within-fit record parallelism and checkpointed long-record memory are not
established by this milestone.

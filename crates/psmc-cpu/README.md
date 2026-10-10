# Strict CPU workspace

`PreparedModel::new(&model)` creates one transition transpose and one array of
emission-transition products for a borrowed immutable model. `Workspace::new(n)`
owns one worker's flat message and count buffers. Calling
`workspace.evaluate(&prepared, observations)` returns borrowed core `Messages`
and `Counts`; their shapes match the current record. An observer can inspect the
same message arrays as the dense oracle. A caller that needs to retain counts
after another record can clone only `Counts`.

The model borrow ends before parameter updates, so stale products cannot be used
with a mutated model. The workspace changes vector lengths to the current record
while retaining capacities. It clears unused row zero and overwrites every other
message or scale cell before reading it. Count initializers are reset on every
record, including duplicate records.

## Derivation and operation order

The reference is `psmc-core/src/hmm.rs`, itself a literal translation of pinned
`lh3/psmc` `khmm.c` commit
`82fa2ada83ee463fe1251b562ae3d60e82d7ad6a`. This change only changes storage access
and lifetime. It does not change a real-arithmetic formula or a binary64
expression. No unsafe code, parallel reduction, structured factorization,
`mul_add`, or fast-math is used.

For states `k,l = 0..n` and original sequence sites `u = 1..L`:

- The transpose cell `at[k,l] = a[l,k]` is a copy. Moving its construction from
  every sequence to every immutable snapshot cannot change values.
- `ae[b,k,l] = e[b,l] * a[k,l]` has the same operand order as the oracle. The
  snapshot is reused only while the model is immutably borrowed.
- Forward dot products start from `0.0` and add `f[u-1,l] * at[k,l]` in ascending
  `l`. Each cell is `e[b,k] * tmp`; the scale adds cells in ascending `k`; each
  cell is then divided by that scale. Zipped slices visit the same indices in
  the same order. Initial forward cells and normalization keep their order.
- Backward sites visit `L-1` down to `1`, and each dot product adds
  `ae[b,k,l] * b[u+1,l]` in ascending `l` before dividing by `s[u]`. The final
  row remains `1.0 / s[L]`. The underflow diagnostic adds
  `(initial[l] * b[1,l]) * emission[first,l]` in ascending `l`.
- Log likelihood multiplies scales in ascending `u` and retains the same
  `1e-25`/`1e25` reset conditions and platform-log calls.
- Counts start with zero initial-state counts and `1e-25` in every transition
  and emission cell. For `u=1..L-1`, each transition cell adds
  `(f[u,k] * ae[next,k,l]) * b[u+1,l]` and each emission cell adds
  `(f[u,k] * b[u,k]) * s[u]`. Sites and states retain their original order;
  therefore every cell sees the identical addend sequence. The final site's
  emission remains omitted. Initial counts retain
  `(initial[l] * emission[first,l]) * b[1,l]` and `+=` into zero.
- Q, the count normalizer, model construction, and parameter optimization use
  the original core implementations. Aggregation and repeated-block caching are
  caller responsibilities; every occurrence must still be added in input order.

The compiler can remove repeated row index/bounds work and vectorize independent
count destinations without changing reductions. Whole-operation equivalence is
still a tested property on the pinned build stack, not a cross-platform promise.

## Isolated differential gate

The crate tests compare every message, scale, likelihood, diagnostic and expected
count against core. Finite values and infinities require identical `to_bits()`;
NaNs require matching classification. Coverage includes all 3,279 strings of
length 1–7 over the three symbols, models with 1/2/4/23/64 states, random initial
parameters, explicit grids, divergence, model updates, missing runs, grow/shrink
buffer reuse, repeated singleton records and nonfinite inputs. Invalid sequence
encodings and empty sequences remain rejected. Performance measurements belong
with the milestone's recorded benchmark evidence and must not be inferred from
these correctness tests.

Build and rerun the isolated timing harness during an otherwise quiet window:

```sh
cargo build --release -p psmc-cpu --example kernel_bench
python3 crates/psmc-cpu/examples/measure_kernels.py
```

The driver runs five alternating dense/CPU pairs per state count, pinning child
processes to the first allowed CPU unless `--cpu` is supplied. It saves binary
and source hashes, commands, raw outputs, exact-check status, medians, and a
source/binary stability guard. Its synthetic three-record workloads have 13,203
bins with 23 states and 52,803 bins with 64 states. Process wall time and RSS
include the separate correctness check and cannot isolate kernel memory usage.

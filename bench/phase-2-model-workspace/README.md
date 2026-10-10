# Reusable model scratch storage

This isolated check covers `crates/psmc-core/src/model_workspace.rs`. The original
`Model::update` remains unchanged as the dense Rust oracle. Both routines are
literal translations of `core.c::psmc_update_hmm` at upstream commit
`82fa2ada83ee463fe1251b562ae3d60e82d7ad6a`; the retained MIT notice applies.

Each candidate previously allocated six temporary vectors: lambda, alpha, beta,
q_aux, q and tau. The new worker-owned workspace allocates the same storage once.
Every consumed scratch element is overwritten during each call, including after
an invalid candidate. No computed model values are cached across parameter
vectors. Their total payload is exactly 6 × K binary64 values (48 × K bytes), or
3,072 bytes at K=64; vector headers and allocator bookkeeping are additional.
At K=1, q_aux is empty and does not require a heap allocation.

The transformation changes storage lifetime only. Exact-length safe slices are
bound once per update so that loop bounds remain visible to the compiler; no
unsafe indexing is introduced. The operations, parenthesized
expressions, state traversal, conditional fallback and matrix layout are copied
from the oracle without algebraic changes. In particular, parameters, time grid,
transcendentals, divergence handling, normalization and invalid-candidate behavior
are recomputed exactly as before. The missing-symbol emission row remains
untouched, as in the original update.

Run the isolated checks from the project root:

```console
python3 bench/phase-2-model-workspace/check.py
```

The driver compiles standalone Rust fixtures without touching the shared Cargo
target. It checks all 60 Phase 1 model fixtures against both the unchanged dense
Rust function and the retained C binary stream. It verifies the C stream and dense
source against the Phase 1 evidence hashes before comparison. Finite binary64
values and signed zero must agree exactly; NaN payloads are classified separately.
The first successful run compares all 64,446 values byte-for-byte.

The two workspace unit tests include 360 updates spanning 1, 2, 4, 23 and 64
states; default/explicit grids; divergence; random initialization; modified
parameters; signed zero; invalid candidates; and recovery after invalid trials.
Every scratch array is poisoned with NaNs before updates to detect incomplete
writes. The tests check stable buffer pointers and reject a mismatched model
shape. The standalone allocation-counter process observes 6,000 allocations for
1,000 dense K=64 updates and zero for the reusable updates. The allocation counter
is excluded from the ordinary comparison and timing binaries.

For paired microtiming, run the following during an otherwise idle measurement
window. The recorded run pins the driver and its children to CPU 0 and alternates
execution order over seven samples at K=4, 23 and 64, each with 200,000 candidate
updates. Parameters vary between updates; both paths execute
the same candidates. Compilation and workspace construction are outside each
sample. These are model-only measurements, not end-to-end inference speedups.

```console
python3 bench/phase-2-model-workspace/check.py --benchmark --cpu 0 --iterations 200000
```

The retained medians in seconds are:

| States | Dense | Workspace | Dense/workspace ratio |
|---:|---:|---:|---:|
| 4 | 0.043128 | 0.028072 | 1.536× |
| 23 | 0.251381 | 0.221478 | 1.135× |
| 64 | 1.077188 | 1.068506 | 1.008× |

K=64 is effectively neutral within the observed sample variation. Eliminating
allocations alone does not establish a meaningful speedup there. The initial
unbounded-Vec version was slower at K=23 and K=64; its exploratory, unpinned
measurements are retained in `results-initial-unbounded.json` and are excluded
from the final performance result. Exact-size slices remove the extra dynamic
bounds-check obstacle while preserving safe indexing and numerical identity.

`results.json` records the checks, compiler/source/binary hashes, raw timings when
requested and exact commands. Full EM, bootstrap, scheduling, memory and end-to-end
performance gates belong to the enclosing Phase 2 suite. CUDA and cross-platform
compatibility are not tested here.

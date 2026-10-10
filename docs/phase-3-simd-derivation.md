# Strict single-thread SIMD derivation and gate

This Phase 3a milestone implements the user's SIMD request and one-thread limit.
It does not implement Phase 3's structured transition or factored objective.
The unchanged external reference is PSMC commit
82fa2ada83ee463fe1251b562ae3d60e82d7ad6a (`khmm.c` forward/backward/expectation).
The unchanged Rust dense oracle and retained Phase 2 binary are independent controls.

For four destination states k..k+3, assign one state to each AVX binary64 lane.
Initialize each accumulator to +0. For every source l in original ascending
order, perform a separate multiply and then add into that lane. Forward uses
Fprevious[l] * A[l,k+lane]; backward uses AE[k+lane,l] * Bnext[l]. After the dot
product, forward multiplies emission * accumulator; backward divides by the
original site scale. The forward normalization sum remains a scalar ascending
state loop; lane results are never horizontally reduced. Moving independent
cell calculations before that sum does not change any sum operand or its order.

Forward reads the original row-major transition matrix. Backward reads a pure
transpose of already computed AE, where AE[z,k,l] = E[z,l] * A[k,l]. Transposing
copies values without recomputing products or changing operand order. Prepared
layouts live only while their model is immutably borrowed. Scalar fallback
retains Phase 2's existing transpose and product traversal.

For counts, process adjacent destination cells in one source row. Every lane
performs count += (F[u,k] * AE[znext,k,l]) * B[u+1,l], using two separate
multiplications followed by one addition. Sites still advance 1 through L-1;
therefore each cell sees the same initializer and ordered addends. Emission
counts remain (F * B) * scale in original site order. Tiny initializers, final-site
omission, original initial counts, missing-data handling and full Q remain intact.
No FMA, horizontal reduction or vectorized logarithm is permitted.

Vectors cover complete groups of four. Remaining cells execute the literal scalar
expression. Loads/stores are unaligned operations on in-bounds four-element
ranges; safe wrappers validate slice dimensions before entering isolated unsafe
architecture-specific functions. Runtime CPU/OS feature detection creates the
private AVX capability. Unsupported hardware falls back under auto mode; an
explicit unsupported AVX request errors before output creation. Shapes too small
for a vector use scalar code. Other architectures compile the scalar path.

First inspect compiler output; existing Phase 2 already includes SSE packed
operations (bench/phase-3-baseline-assembly.json). Measure actual added benefit
rather than equating lane width to speed. Check auto/off/forced dispatch, every
remainder mod four, singleton and odd/even lengths, missingness, divergence,
explicit grids, poisoned/reused storage and nonfinite classes. Compare every
message, scale, likelihood and count with the dense oracle. Run full pinned-C
output/trace checks and every fixed bootstrap sequentially. No tolerance is
relaxed. SIMD and scalar builds retain the same platform libm and optimizer.

All heavy build/test/benchmark commands run under one-CPU affinity with Cargo
jobs=1, test threads=1 and reduced process priority. Shared-machine activity can
perturb timings; report ranges and per-process CPU time alongside wall time.
No parallel throughput or ARM performance is inferred from these measurements.

# Masked AVX tails and separate 64-state kernels

The generic Phase 3a AVX path handles complete groups of four and scalar tail
states. At 23 states, three destination sums remain scalar. This candidate uses
AVX masked loads/stores to carry out those one-to-three independent lanes together.
Each active lane retains the same source-order sum, multiply operand order,
emission multiplication, backward division and ordered count update. No horizontal
sum, FMA, precision change or extra statistical contribution is introduced.

The mask activates exactly the low `n % 4` lanes. For a row beginning at k*n,
active indices are k*n+end through k*n+n-1. Inactive lanes perform no memory
access. Intermediate values in inactive lanes are never stored or reduced into
active lanes; their floating-point exception flags are not part of the program's
observed contract. All complete groups and zero-tail behavior remain unchanged.
Runtime feature checks still require AVX; AVX2 is not needed.

The semantics and feature requirement are documented by Rust's
[masked load](https://doc.rust-lang.org/core/arch/x86_64/fn._mm256_maskload_pd.html)
and [masked store](https://doc.rust-lang.org/core/arch/x86_64/fn._mm256_maskstore_pd.html)
intrinsics. The actual compile/test stack remains Rust 1.90.0. Isolated tests
compare signed zeros, subnormals, nonfinite classes, unaligned slices and all
remainders. Linux guard-page tests place each source and destination immediately
before inaccessible memory, so touching even one inactive tail address would fail.

A second candidate also dispatches exactly 64 states to separate wide functions
with four independent vector accumulators. The initial in-function specialization
improved both tested K64 fits but consistently slowed K23 controls; changing the
register/code layout of the original function can matter even when its arithmetic
path is nominally unchanged. Separate functions retain the original generic loop
body and local register requirements. The safe wrapper checks shapes and n==64
before entering the private fixed-size functions. The index proof is k+15<=63
and l<64, with every matrix address below 4096.

This is a new candidate, not automatic promotion of the earlier timing result.
It needs its own exactness, guard-page and performance checks, then the complete
release gates if the measured whole-workload result justifies adoption.

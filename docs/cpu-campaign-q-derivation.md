# Exact logarithm reuse: candidate derivation and admission gate

Status: exploratory candidates only. No candidate has been promoted. The source
baseline is `6a4d102`, and the external oracle is pinned C
`82fa2ada83ee463fe1251b562ae3d60e82d7ad6a`, `khmm.c::hmm_Q` (lines 363–385).

The original objective walks the two emission rows in symbol/state order, then
the transition matrix in source/destination order. For each probability `p`, it
first returns `-1e300` if `p <= 0`, otherwise accumulates `count * log(p)` into one
scalar sum. Finally it subtracts the previously computed full-count entropy
normalizer. Initial-state and missing-symbol counts do not participate.

The candidate retains the same input arrays, early-return location, multiplication,
ascending scalar sum and final subtraction. Flattening the contiguous emission
and transition arrays visits cells in exactly the same order. It does not collect
triangular margins, combine repeated counts, change the optimizer, or omit any
cell because its count is tiny or zero.

Three implementations are screened separately:

1. Flat loops with original libm calls, providing a loop-layout control.
2. One cache slot for each objective probability position, holding its most recent
   binary64 input bits and the exact returned binary64 logarithm.
3. An 8,192-slot direct map keyed by a multiplicative hash of the probability's
   bits. A hit requires equality of the complete 64-bit key, not just the hash.
   Collisions replace the old entry and cannot produce an approximate hit.

For positive finite `p` on the unchanged process/libm/floating-point environment,
the same binary64 input returns the same binary64 `log(p)`. Storing that result and
reading it on an exact-key hit changes no objective arithmetic. This is reuse of
a pure scalar function, not reuse of expected statistics between parameter
vectors. Counts are always read live, so the cache may remain populated across
EM iterations with different counts. Its capacity is bounded per backend.

All cache entries initially have zero key bits. The original positivity check
prevents positive/negative zero from reaching the cache; a positive finite input
therefore cannot match an uninitialized entry. NaN and infinity bypass caching
and call libm. A later nonpositive probability still returns the sentinel even
if an earlier NaN has contaminated the scalar sum. Signed zero, subnormals,
nonfinite values, changed counts and replacement collisions have isolated tests.
The project does not observe libm errno or floating-point exception flags; no
cross-rounding-mode or cross-libm cache portability claim is made.

The direct map requires approximately 128 KiB per backend; the positional cache
requires `16 * (K*K + 2*K)` bytes. Additional memory and lookup branches can erase
the saved libm work. Neither candidate is assumed faster. No logarithm polynomial,
vector math substitute, FMA or reassociated reduction is allowed in this experiment.

`bench/cpu_campaign_q.py` injects candidates into disposable source copies under
`work/`, runs isolated tests, then screens identical complete K23/N30, K64/N5
(partial trajectory), and one K23/N30 bootstrap against the preserved release.
It rotates implementation order, excludes warmups, retains five CPU/wall samples
and compares every output byte except the existing version allowlist. This screen
is not the full acceptance gate and does not establish production performance.

A candidate may enter the release only after full internal snapshots, optimizer
callback sequences, all existing 30 bootstraps, added finite workloads, safety and
dispatch integration, repeated uninstrumented end-to-end measurements and memory
accounting pass. Any speed regression or ambiguous benefit remains recorded.

# Independent SIMD chains and ordered count tiles

Exploratory candidates target the Phase 3a backend at `6a4d102`; none is admitted
to the release solely by this derivation. The pinned dense Rust and C oracles
remain unchanged. `bench/cpu_campaign_kernel_variants.py` generates isolated source
copies for the following comparisons.

The existing forward/backward AVX loops have one four-lane accumulator per
destination group. The 8- and 16-state candidates maintain respectively two or
four independent accumulators while scanning the same source states in the same
ascending order. Sharing the input broadcast across those accumulators changes
no lane's multiply/add grouping. Forward retains `f * A`, then `emission * sum`;
backward retains `AE * b`, then `sum / scale`. No accumulator is split and later
reduced. Remaining groups of four and scalar tails use the original loops.

Each wide group starts at a multiple of its width and ends no later than n.
Consequently every four-lane load/store stays inside its row and every source-row
address is less than n*n. The runtime AVX capability and safe dimension checks
remain the only entry point to the private unsafe implementation. Unaligned
accesses, finite/signed-zero/subnormal/nonfinite values and all new tail cases
are tested; no alignment or FMA assumption is introduced.

The count candidates visit sites in ascending tiles of 64 or 256. Within a tile,
each source row and four-destination group loads its previous count, then performs
the original ordered sequence `count += (f * AE) * next_backward` for every site
in that tile. It stores the result before the next tile. Tile boundaries therefore
neither reorder addends nor introduce a partial sum or another rounding operation.
The initial tiny count is present once, and binary64 registers/store values have
the same precision. Scalar tails follow the same site order.

Emission counts still use the original ascending-site traversal, final-site
omission and grouping. Moving independent transition-cell computations relative
to independent emission-cell computations creates no data dependency. All forward
and backward messages remain available and unchanged. A tile is not a new HMM
sequence; no boundary, mask, scale or statistical observation is added or dropped.

Count tiling may reduce loads/stores of the count matrix but increase strided
message reads and loop overhead. Wide SIMD chains may improve instruction overlap
but consume more registers. These are hypotheses to measure, not speed claims.
The screen must include isolated exact tests, complete fits and kernel timings;
promotion additionally requires the full C/snapshot/bootstrap/safety gate and
whole-workload CPU/wall/RSS measurements under the one-CPU policy.

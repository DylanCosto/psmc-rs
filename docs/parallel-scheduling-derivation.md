# Independent bootstrap scheduling

The user authorized all-core work on 2026-10-10 after the one-CPU campaign.
The baseline is the frozen 0.3.1 executable and source commit `e8a1cc1`.
Only independent replicates are scheduled concurrently. Numerical code remains
unchanged, including each fit's record order, full counts, Q, optimizer callbacks,
SIMD dispatch and binary64 arithmetic. A replicate's seed remains `base + index`.

The existing dynamic queue dispatches replicate indices in forward or reverse
order. The experiment adds `balanced`: preview each bootstrap with a separate
owned RNG, estimate work from its observation lengths, then dispatch descending
work with ascending replicate index as a deterministic tie-breaker. For the cached
CPU backend, count each distinct encoded observation string once in this estimate;
otherwise count every occurrence. This is only a scheduling estimate: optimizer
callback counts and heterogeneous-core speeds are not predicted.

`job()` still starts a fresh RNG from that replicate's original seed and runs the
original sampler, including rejected final draws. The preview cannot alter that
RNG. It never substitutes a new sample or orders the records inside a fit. Each
index occurs exactly once in the dispatch vector, and one atomic queue position
selects it. Results remain stored and serialized by replicate index regardless
of completion order. No floating-point shared reduction, cross-fit count cache or
nested pool is added. The dense and CPU numerical source files remain unchanged.

Preview scratch is transient and sequential, before worker launch. The existing
admission budget includes per-replicate draw/result metadata with conservative
headroom; only a queue vector and scalar work weights are retained additionally.
The original memory admission limit still bounds worker count, and is not an
OS-enforced RSS cap. No claim of lower-memory admission is made.

Acceptance requires exact comparison with C for every original and model-based
bootstrap, across worker counts and queue orders; nonzero random initialization
and cache-off controls establish that preview RNG and ordered reductions are
unchanged. Full-batch timing must include preview and file output. A faster
individual kernel does not establish better parallel throughput. Compare against
already-parallel vanilla with identical materialized samples and worker limits.
Keep the existing dispatch default if heavy-first scheduling gives no consistent
improvement; do not select seeds, omit pathologies or shorten fitted trajectories.

The harness samples aggregate live process RSS at 10 ms: it is a lower bound on
peak total RSS, not the sum of individual historical maxima. Rust threads share
one process; vanilla uses bounded independent processes. Both inherit the same
allowed CPUs in each comparison. Run complete benchmark groups sequentially to
avoid competition between variants; retain all warmups and measurements.

## Measured decision

The candidate passed correctness gates but failed the performance gate. Its median
batch wall time increased in all four dataset/topology comparisons (4.8–11.9%).
The candidate remains only in experimental evidence and is not a supported release
option. Production source and executable stay at 0.3.1. Use the existing forward
queue with 16 workers on this host. See parallel-report.md for complete results.

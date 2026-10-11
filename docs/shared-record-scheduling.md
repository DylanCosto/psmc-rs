# Shared record scheduling: prospective gate

A fixed worker budget executes fits and record jobs. No nested numerical pools.
When fit workers become idle, they take independent records from active fits.
Each caller waits for all its records and reduces counts/LL in original order;
duplicate cache hits still add each occurrence. Snapshot observers bypass record
sharing. Strict and equivalent arithmetic must be bit-identical to their serial
counterparts. Job panics return to the owning fit and must not strand helpers.

On Linux with readable maximum-frequency topology, workers are pinned within the
inherited allowed CPU mask. All fastest-core threads own fits; slower CPUs help records from the outset.
Faster threads join record helping when they exhaust the fit queue. Slower helpers
leave the final fast-worker-count jobs for faster cores. This replaces the first
screen's all-core fit ownership, which regressed equivalent time by 7% even
though strict improved. A six-physical-core-owner screen then showed no useful gain;
the final policy allows all twelve P-core threads to own fits. All screen
binaries, reports and protocol versions are retained.
Maximum frequency is a throughput heuristic. If topology is unavailable or
pinning fails, workers fall back to ordinary fit ownership and late helping.
Manifests report actual pinned CPUs and completed helper record jobs. Strict
record jobs reuse one workspace per OS thread to avoid repeated message allocation.

`--scheduler fit|shared` selects batch policy. `--record-workers N` enables record
parallelism within a single CPU fit (default 1), capped by available parallelism;
it is rejected with bootstrap, CUDA/dense and snapshots. Existing complete records
are the only parallel units. A one-record chromosome remains sequential.
The batch admission estimate includes twice message storage per worker,
count storage for every possible uncached draw, and bounded owned observation
copies for the frozen posterior and queued jobs. These are reserved separately
from source data and retained manifest metadata. It remains an estimate, not an OS-enforced limit. Single-fit
record workers have no memory admission option: more simultaneous records require
more message storage in strict mode.

Before promotion: exact complete outputs and bootstrap draws for both modes,
cache on/off, reversed fit order, single-worker and shared-worker runs; both human
panels in equivalent mode and HG001 in strict mode. Single-fit record-parallel
output must be exact. Queue panic propagation is unit-tested.

Performance: HG001 30 bootstraps with 16 workers, same settings/input as the linear
milestone; one warmup plus three alternating measured pairs, separately for strict
and equivalent. Require >=5% lower median wall time and >=2/3 pair wins to call
an improvement in that mode. No >5% median regression is allowed for default
promotion. Preserve fit scheduling as a selectable fallback. Also measure a
single multi-record HG001 fit. Report CPU/RSS and actual helper work; do not infer
95% utilization from the existence of a queue.

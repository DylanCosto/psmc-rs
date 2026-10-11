# Bootstrap interruption and resume

New batches write a `resume-contract.txt` and per-replicate `.complete` markers.
`--resume` is supported for these batches, on Linux filesystems supporting advisory
`flock`; older batch directories without a contract cannot be imported implicitly.
Resume requires an explicit original `--seed`, also recorded in the contract.

The contract binds SHA-256 of the executable and encoded input (ordered record
names, lengths and observation bytes), all model settings including loaded parameter
values/time grid, mode, backend, SIMD policy, cache policy, iterations, decoding
options, CUDA tile/buffer settings, seed and replicate count. Changing compression,
input path or equivalent alphabet aliases is permitted because encoded observations
are identical. This is not raw-file provenance: retain input-file checksums separately.
Use the same machine/runtime libraries; the contract is not a portable cross-libm
reproducibility guarantee. Changing worker count, memory admission budget, scheduler,
task order or progress reporting does not alter fit arithmetic and is permitted.

Each completed replicate has flushed and synchronized PSMC output, statistics and
draw trace, whose SHA-256 values are written into a synchronized completion marker.
All completed artifacts are verified before any incomplete files are moved. Missing,
modified, nonregular or malformed completed artifacts stop the run. Checkpoints are
integrity checks against accidents, not signed protection against malicious edits.

An unfinished replicate is rerun with its original deterministic seed from the
beginning. Existing partial output is moved to a uniquely named `incomplete-*`
directory. Interrupted checkpoint temporary files are retained. Old manifests are
retained as `manifest.previous-N.json` on subsequent completion. A nonfinite fit is
marked completed **with its nonfinite status preserved**; resume never turns a
numerical failure into a passing result. Inspect the final manifest.

The kernel lock is held throughout contract/output verification and fitting. A
killed process releases it automatically; do not delete `run.lock` while a process
is live. Filesystems without working locking or synchronization may fail the run.
A crash before initial contract publication leaves a directory that must be preserved
and replaced with a new output directory; it cannot safely be resumed.

The memory budget is the existing conservative admission estimate, not an OS RSS
limit. Input loading precedes admission. Resume uses the same admission checks as
new batches, even if all fits are already complete.

# Independent Phase 2 CLI and bootstrap review

Review scope: CLI option handling, protected input/output paths, deterministic
bootstrap seeds and task order, bounded admission, failure reporting, manifests
and per-fit counters. This review does not replace the numerical differential
suite or establish a performance result. No production files were changed by the
reviewer.

**Final status: all 17 CLI and scheduler review controls pass.** The output-safety
finding is fixed and rechecked against executable SHA-256
`fd866573a007003d2388137270ec24f14acb436c42c7084ab8dac076fdabb59a`. The final
[review result](../bench/phase2-review.json) records the successful rerun performed
by the root agent; this independent follow-up verified the result, source hashes
and corrected source without rebuilding during the final validation window.

The initial executable reviewed was SHA-256
`28bb94161d898ebd3bc676a10df0fb24a26580e37fe6c3a48412d48e7f9ac948`.
Every run uses an immutable executable copy. The reproducer is
`bench/phase2-review.py`; the initial 17-control result is retained in
[the initial failure report](../bench/phase2-review-before-fixes.json).

## Corrected output-safety finding

**P1 — validate selected records before opening output files.** In single-fit
`run`, output and snapshot files were opened with truncation before `fit` checked
whether every selected observation was missing and initial parameters were absent.
An all-N input exited with the appropriate validation error but erased existing
output and snapshot files. The bootstrap form had the same problem when a mixed
source sampled only missing records: it additionally replaced an existing draw
trace before rejecting the fit. The two failing controls reproduce both cases;
the second uses the synthetic mixed fixture and seed 45.

The corrected single-fit path validates the ordered, selected records before
creating/truncating trace, legacy output or snapshot files. Checking only the
original source is insufficient for bootstrap sampling. Both regression controls
now return the expected validation error while preserving every existing file
byte-for-byte. The new batch-directory path continues to retain partial files and
report failed jobs under its explicit failure policy; it never replaces an
existing destination directory.

## Static memory-admission observation

The initial worker estimate accounted for messages, model scratch and count
caches, but omitted the complete result vector and retained sampled indices across
all requested replicates. Those are allocated outside the bounded worker queue.
Large replicate counts could therefore exceed the stated conservative estimate
even when one worker was admitted. Sampled indices, draw traces and ordered
references can also exceed the number of input records when source lengths differ.
The corrected admission calculation now uses a worst-case draw bound derived from
total input length and the shortest source record. Worker cost includes transient
sampled indices, ordered references and draw traces, with vector-capacity growth.
Resident cost separately reserves completed-result indices and JSON construction
across all requested replicates, plus escaped source-record metadata. Checked
arithmetic rejects overflow before creating the batch directory or reserving the
result vector. The manifest records `estimated_metadata_bytes` alongside the
worker estimate. Static follow-up verified these additions in the source matching
the final review hashes.

The policy remains a conservative estimate, not an operating-system-enforced
memory ceiling; input loading precedes admission. No large allocation or
exhaustion test was attempted.

## Completed controls

The two output-preservation regression controls and all 15 original passing
controls pass in the final review:

- Statistics paths that hardlink the input, or alias legacy output, are rejected.
- All-missing batch inputs, too-small memory budgets, and existing output
  directories are rejected before creating batch directories.
- One-worker forward and three-worker reverse schedules produce byte-identical
  outputs for four replicates, with manifest records in replicate-index order.
- Seeds 42–45 exactly replay four independent `-b` fits, including the subsequent
  randomized parameter initialization. This checks that resampling and model
  initialization share the per-fit RNG in the correct order.
- A mixed synthetic batch records two all-missing failures and six completed fits,
  retains a complete manifest, and returns failure without abandoning other jobs.
- Zero workers/replicates, invalid task order, overflowing memory budgets and an
  overflowing seed range are rejected before creating output directories.

Batch per-fit files expose counters and explicitly report whether profiling was
enabled. In the reviewed build, batch phase timings are disabled and reported as
zero with `profile_enabled: false`; these fields must not be interpreted as timed
performance measurements. Kernel and end-to-end timings are separate evidence.

## Separate model-workspace timing evidence

The model-workspace [isolated report](../bench/phase-2-model-workspace/results.json)
compares seven alternating pairs of 200,000 candidate updates pinned to CPU 0.
Dense/workspace median seconds are 0.251381/0.221478 at K=23 (1.135×) and
1.077188/1.068506 at K=64 (1.008×, effectively neutral within sample variation).
The numerical gate is byte-exact for all 64,446 model fields; 1,000 K=64 updates
require 6,000 allocations in the dense path and zero in the workspace path.
These are model-only measurements, not end-to-end inference claims.

The initial unbounded-Vec implementation was slower. It was corrected by taking
exact-length safe slices once per update, which exposes loop bounds to the
compiler without changing arithmetic. That regression is resolved and excluded
from the accepted timing result; its exploratory measurements remain in
[the initial timing report](../bench/phase-2-model-workspace/results-initial-unbounded.json).
It is not an unresolved numerical or release-gate failure.

## Reproduction and limits

To rerun these small controls without building or timing:

```console
python3 bench/phase2-review.py --binary path/to/the/final/psmc-rs
```

The final report records its own executable digest and source digests. Source
review found no other actionable correctness issue in seed arithmetic, queue
ownership, result ordering or repeated-record reductions. Disk exhaustion,
process termination and hardware memory exhaustion remain untested.

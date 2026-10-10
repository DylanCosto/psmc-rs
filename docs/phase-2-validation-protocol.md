# Phase 2 CPU and scheduling validation protocol

This protocol is recorded before timing the optimized backend. It extends the
existing exact Linux/glibc contract. The original dense Rust oracle and pinned
vanilla C stay available. CPU memory engineering, repeated-block caching and
independent-replicate scheduling do not authorize changed arithmetic, a new
optimizer, altered counts or tolerances, fewer iterations, or new HMM boundaries.

## Exactness and provenance

`bench/phase2_validate.py --run` first freezes read-only copies of the candidate,
Phase 1 release, vanilla C and instrumented C. Every wrapper verifies the actual
underlying executable hash before launch. The unchanged Phase 1 runner also
checks the wrapper hash. Sources at freeze time, original binary paths, copied
binary hashes, arguments, commands, output hashes and complete child reports are
retained under a new timestamped Phase 2 directory. The runners never rebuild a
shared executable or overwrite Phase 1 evidence.

Both explicit `--backend dense` and `--backend cpu` run 113 inherited controls.
These include every supported legacy option, malformed-input/output safety
controls, independent records, masks, aliases, supplied parameters, K64 outputs,
seed replay and all 30 fixed K23/N30 bootstrap trajectories. The only stdout
exclusion is the single honest `MM Version` record. Every numerical field and all
other metadata remain byte-exact. The 27 finite trajectories and pathologies 16,
26 and 28 must remain distinct; pathology parity is not finite inference.

Complete tiny/N2, explicit-grid/N1 and K23/N1 snapshots compare every event,
parameter, matrix element, scaled message, count, Q value and optimizer callback
in order. Finite values and signed zero use exact equality; nonfinite classes
are compared separately. No event is truncated. Snapshot runs must execute the
CPU workspace path while explicitly bypassing the repeated-count cache so that
all messages remain available. Separate non-snapshot controls verify cache use.

The exhaustive independent-enumeration trace and the large K64 model/callback
trace remain preserved from Phase 1 rather than being regenerated here. The
model and optimizer are unchanged in this milestone. The CPU HMM change needs
isolated exact tests across state sizes including 64, followed by complete K64
output parity. The existing independent-enumeration tolerance is not a production
CPU tolerance. If model/optimizer arithmetic or callback traversal changes, reconsider this
bounded scope before claiming the gate passes.

The reused child runner retains its historical Phase 1 descriptive labels. The
Phase 2 parent report and explicit wrapper backend arguments define the current
scope; all original child metadata stays inspectable rather than being edited.

## Scheduling and cache controls

`bench/phase2_scheduler.py --run` evaluates all 30 replicates at 1, 2 and 4 workers
in forward and reverse task order. Every result is compared with the pinned-C
materialized counterpart. Scheduler manifests and per-replicate statistics are
retained. The seed for replicate *i* is 20261009 + *i*; accepted source-block
indices and the legacy total-length stopping rule must match the fixed manifest.
Sequence contributions remain added in their original occurrence order.

Replicate 00 contains 13 block occurrences and eight distinct source blocks. A
one-iteration CPU fit must visit all 13 occurrences, evaluate eight and record
five cache hits. Its full-message snapshot counterpart must evaluate all 13,
record zero hits, explicitly report cache bypass and produce the same output.
Caching a contribution never removes the repeated addition or its pseudocount.
Cache keys and lifetime must prevent reuse across parameter snapshots. An explicit
cache-off fit must also evaluate all 13 occurrences and match both other outputs.
Three additional bootstrap fits use randomized initialization (`-I 0.1`) and
compare with seeded instrumented C, verifying that initialization consumes the
same RNG stream after the resampling draws.

## Timings and memory

After correctness passes and builds/tests are idle,
`bench/phase2_benchmark.py --run` uses the same frozen executable copies. No
snapshot instrumentation is enabled. Each serial-fit case has one warmup per
implementation and five measured repetitions with rotating execution order:
vanilla C, the delivered Phase 1 Rust release, current dense and current CPU.
Inputs are the finite K23/N30 unsplit fixture and the K64/N5 profile fixture.
The latter is explicitly a partial trajectory. Every measured output must pass
the same exact comparison and finite-output check as its C counterpart.

Separate batch measurements compare vanilla processes and the Rust scheduler
at equal worker budgets of 1, 2 and 4, with one warmup and three measured batches
per implementation. The batch uses all 30 full K23/N30 trajectories, including
the three retained pathologies, so its timing describes execution mechanics,
not scientific production throughput. C receives already materialized inputs;
Rust also performs deterministic resampling from the original blocks during the
timed command. This does not disadvantage the reference with instrumentation.

Wall time includes startup, output and scheduler work. Linux maximum RSS is
retained per process. A 10 ms sampler also sums resident memory over the live
child process tree, including `/usr/bin/time` and excluding the Python harness.
This sampled aggregate is a lower bound on the actual transient peak, not an
exact allocator measurement. A negative control confirms child processes created
by worker threads are observed. Per-process maximum RSS is not mislabeled as
aggregate parallel memory. Host load averages and raw timing files remain visible.

No test job or compression should run alongside these measurements. The host
is shared and CPU affinity/governor settings are not changed. Few repetitions
and synthetic inputs support only a local diagnostic comparison. The user's
real settings, input, preprocessing, worker budget, full-genome behavior, GPU
performance and tenfold target remain unvalidated. Ordinary process concurrency
is compared at equal worker counts and never presented as kernel acceleration.

## Measurement review and memory interpretation

The measured runner and its original report are preserved in
`bench/phase-2-benchmark/20261010T050118702033Z/measured-runner.py` and
`measured-report.json`. A read-only review found three latent guard issues:
worker admission was not required to equal the requested budget, taking the
maximum child exit code could hide a negative signal exit, and two subset flags
could be combined into an empty timing scope. The runner stayed unchanged until
measurements finished. The [post-run audit](../bench/phase-2-benchmark-audit.json)
checks every actual run: all 360 C children exit zero, all 12 CPU batch manifests
admit exactly the comparable 1/2/4 workers, and all 48 single runs plus 24 batches
are present. Neither subset flag was used. The active results satisfy the repaired
guards, so no measurements were reclassified or rerun. The current reproducer
fixes all three issues and nine harness regression tests pass.

Sampled child-tree RSS includes process-launch transients and shared resident
pages counted for each process, as well as the timing wrappers. It is not physical
RAM consumption or isolated inference memory. In this run the one-worker C
median sampled peak is 31,756 KiB, larger than the two-worker value of 9,084 KiB;
that does not establish that one inference worker needs more memory than two.
Do not turn those sampled figures into an engine memory-saving claim. The raw
samples and per-process peak RSS remain available. For the finite single fits,
C/CPU median inference-process peak RSS is 4,680/5,188 KiB at K23 and
27,308/26,772 KiB at K64. Memory admission is a conservative estimate, not an OS
enforced RSS limit.

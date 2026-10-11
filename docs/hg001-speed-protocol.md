# Controlled HG001 speed comparison — 2026-10-11

Prospective protocol; no benchmark result has been inspected. Start only after
the existing whole-autosome comparison finishes and its independent integrity
audit and C/strict exactness pass. Preserve and report the equivalent scientific
screen separately, including failures; timing does not establish accuracy.

Reuse the exact frozen C and Rust binaries, HG001 input, and fit options from
`docs/hg001-genome-protocol.md`: all 22 chromosomes, 28,750,027 bins, 64 states,
30 iterations. No downloads, compilation, re-encoding, subsampling or numerical
changes. Hash inputs, binaries, protocol and harness before execution.

First measure single-core C, strict and equivalent, each pinned to logical CPU 0
(a P-core according to Linux cpu_core/cpus), with one Rust record worker. Then
measure strict and equivalent with all 16 allowed logical CPUs and 16 requested
record workers. Verify these affinities on this host; fail if unavailable.
Strict retains an explicit 8192 MiB admission budget at both sizes: report its
actual admitted workers and label the full-affinity result memory-limited if
fewer than 16. This is not an unconstrained 16-worker strict benchmark.

Each phase has one complete excluded warmup per configuration, followed by three
measured repetitions. Single-core order is C/strict/equivalent, then
strict/equivalent/C, then equivalent/C/strict. Full-core order is strict/equivalent,
then equivalent/strict, then strict/equivalent. All fits run sequentially, with
five seconds idle between fits. No parallel benchmark jobs. Three repetitions
describe variability; they do not support narrow confidence intervals.

Measure whole-process wall time with GNU time (including parsing, startup,
fitting, output and stats), user+system CPU time, peak RSS, actual workers and
CPU-time/wall-time ratio. Retain all raw observations, commands, stats and outputs.
Report median and range, median C-single/Rust-single ratios, and same-mode
single/full ratios. Single/full phases are separated in time and external CPU
load is not controlled. Record load averages, CPU pressure and system CPU ticks
before/after each fit; do not silently remove slow observations or change system
governors, caches, SMT settings or other users' processes. All children use nice 10.

Check every warmup and measured output against the audited corresponding engine's
entire numerical output (only MM Version excluded), and C/strict against C. Any
mismatch, nonfinite/incomplete fit, nonzero status, changed provenance or resource
stop aborts the campaign with evidence retained. Equivalent fallback counts are
reported, never hidden. A stopped campaign is incomplete, not a speed result.

Reuse the bounded runner: 10 GiB address-space ceiling, 512 MiB/file output limit,
6-hour per-fit timeout; start only with at least 14 GiB available RAM and 30 GiB
free disk. Stop this campaign's child group if RAM falls below 4 GiB, free disk
below 25 GiB, or new campaign evidence exceeds 4 GiB. The input is reused in place.
Resource checks run every two seconds. Admission is an estimate, not an RSS cap;
the separate process limit and machine resource guard remain mandatory.

Queue behind the existing runner and audit, without polling the user. Do not
automatically restart failed runs or resume the cancelled simulations. Preserve
the comparison's numerical protocol unchanged. Results apply to this release,
host and public fixture; user workload and other hardware remain untested.

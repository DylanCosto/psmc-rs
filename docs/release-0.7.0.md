# PSMC-rs 0.7.0 — equivalent CPU default

Release candidate 0.7.0-rc.1 passed the prospective compatibility and resource
checks. Final release verification and local installation are in progress.

Ordinary CPU fits and bootstrap batches now select equivalent unless `--mode`
is supplied. Keep `--mode strict` in scripts requiring the tested pinned-C
arithmetic, exact numerical output or original QD diagnostic. Equivalent uses
QU, whose values can be compared before/after optimization within one round,
not across rounds. The model, f64 precision, optimizer and iteration count are
unchanged; this release changes selection and memory admission, not inference
arithmetic. Selected mode appears in stderr, MM Version, stats and batch manifests.

When mode is omitted, dense/CUDA backends and snapshots (including PSMC_SNAPSHOT)
select strict. Explicit equivalent with those features remains an error.
Selection does not depend on option order. CUDA remains optional and experimental.

`--memory-mib` now works for both single CPU modes. Strict keeps its existing
estimate. Equivalent reserves checkpoint scratch per worker, input copies/counts,
one retained serial dense history for an ineligible E-step, and another dense
history for decoding/scales. Its estimate deliberately exceeds usual RSS rather
than assuming that every future model remains eligible. Default budget remains
half detected available RAM/cgroup headroom (1 GiB fallback if unavailable).
Admission reduces workers or rejects before opening output. It is not a hard RSS
limit, and input loading precedes admission. Bootstrap's existing memory policy
is unchanged. Per-process budgets do not reserve RAM against other processes.

The candidate passed 61 Rust tests (four optional CUDA hardware tests ignored),
four live C golden comparisons, and 25 compatibility checks against v0.6.3.
Checks cover explicit strict/equivalent parity, omitted mode, decoding, full
posterior, scales, transition cap, divergence, random initialization, supplied
parameters, gzip/stdin, seeded bootstrap outputs/draws and memory admission.
Upstream history/average utilities ignore the objective diagnostic; truncation
preserves QU verbatim while producing unchanged other records. Plot data and
gnuplot script generation passed; actual plot rendering is not_run because
gnuplot is unavailable. No renderer was installed or falsely reported as run.

Candidate bounded allocation checks used eight distinct million-bin records:
strict under 2048 MiB admitted one worker and peaked at 995.2 MiB; equivalent
with decoding under 3500 MiB admitted eight workers and peaked at 1089.8 MiB.
Both used hard 10 GiB address-space limits and machine resource guards. The N30
HG001 default fit admitted 16 workers under 8192 MiB, estimated 3440.2 MiB and
peaked at 485.1 MiB. Its numerical output matched the previously audited v0.6.3
equivalent output exactly, excluding only MM Version. These are regression
checks, not a new speed benchmark. See the [controlled speed report](hg001-speed-report.md).

The [prospective release protocol](default-transition-protocol.md) and retained
raw records under ignored work/default-transition-* document the transition.
An early harness assertion incorrectly expected psmc_trunc to discard the
diagnostic; its actual passthrough behavior is now checked explicitly. Failed
harness output was retained; no numerical tolerance or inference output changed.

Prior [whole-autosome agreement](hg001-genome-report.md), [known-truth panel](known-truth-200mb-report.md)
and [linear-mode controls](linear-equivalent-report.md) remain supporting evidence.
Default promotion does not claim universal scientific equivalence. The user's
actual input/preprocessing, whole-genome bootstrap uncertainty, other CPUs/ARM,
non-Linux and new GPU hardware qualification remain outside this release check.
Hosted CI and remote publication require a configured remote; no remote release
is claimed. Historical runners/protocols belong to their recorded source/binary
versions and must not be silently replayed against a new implicit default.

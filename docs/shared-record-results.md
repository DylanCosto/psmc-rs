# Shared record scheduling, v0.6.1

The CPU batch runner has one cooperative queue within its existing worker budget.
All P-core threads may own fits; E-cores help with records. Faster workers also
help records after the fit queue empties. Every record retains its own model and
HMM boundaries. The fit owner adds completed results in original occurrence
order, including every cached duplicate. No reduction depends on completion order.
Strict and equivalent outputs each remain identical to their serial counterparts.

`bootstrap --scheduler shared` is the new policy; `--scheduler fit` retains the
previous queue of independent fits. A single fit can use `--record-workers 16`
(default 1). This only parallelizes existing records: a chromosome represented
by one record remains sequential. Snapshots bypass record sharing; the CLI rejects
single-fit record workers with snapshots, dense/CUDA backends or bootstrap.

On this i5-12600K, Linux maximum-frequency metadata distinguishes 12 P-core
threads from four E-cores. The policy is confined to the inherited affinity mask
and orders physical cores before SMT siblings. Slower helpers leave a final
queue of jobs for faster workers, reducing the chance of a late slow-core record.
The frequency heuristic is not universal throughput knowledge. Unknown topology
or failed affinity setting uses ordinary fit ownership and late record helping.
Manifests report actual pinned CPU IDs and completed helper jobs.

Threads reuse strict workspaces rather than repeatedly allocating complete
message histories. The batch admission estimate reserves twice message storage per worker,
completed count storage for all possible uncached draws, and owned observations
for frozen equivalent posteriors and queued jobs. A final review added the latter
reservations explicitly before repeating acceptance on the installed binary.
It remains a conservative estimate, not a hard RSS limit. Single-fit parallelism
has no memory-admission flag; simultaneous strict records need additional storage.
Queue jobs own their inputs; panics propagate to the owning fit. Stop guards shut
down helpers even if a single-fit call returns an error or unwinds.

## Retained screens

All-core fit ownership plus late helping preserved numerical outputs, but its
single equivalent screen regressed from 10.189s to 10.903s. Strict improved in that
screen, 61.740s to 51.254s, while allocating fresh helper histories increased CPU
and memory. The next screen used six physical P-core fit owners and reusable
strict histories: equivalent 11.054s vs 10.849s; strict 46.470s vs 47.677s. These
screens did not justify a promotion. The final screen allowed all twelve P-core
threads to own fits: equivalent 10.202s vs 9.429s, with all outputs exact.
Earlier binaries, raw outputs and protocol revisions remain in work/shared-records;
screen summaries are tracked under bench/shared-records-*.json. These noisy single
screens selected a candidate, not its accepted performance claim.

## Validation and reproducibility

The prospective gates are in [the scheduling protocol](shared-record-scheduling.md).
The runner independently replays bootstrap draws and byte-compares all outputs
outside the version line against the accepted arithmetic baselines: original
strict C-compatible output and v0.6.0 equivalent output. This does not claim that
equivalent and strict are bit-identical to each other.

Commands: `cargo test --workspace --release --offline`,
`cargo test -p psmc-cpu --offline`, `cargo check --workspace --all-features --offline`,
`python3 bench/shared_records.py validation`, `python3 bench/shared_records.py performance`,
`python3 bench/shared_records_audit.py`; formatting and diff whitespace checks.
The optional screen command records the retained variants. Final binary and
protocol hashes are fixed before validation/performance and recorded in each report.

The mathematical model, f64 kernels, optimizer, initialization, masks, record
boundaries, observations, iteration count, QU/QD contracts and RNG are unchanged
from v0.6.0. This milestone changes where record work executes. It follows the
[linear E-step milestone](linear-equivalent-report.md), whose separate numerical
acceptance and scope limits still apply. Strict remains the default numerical mode.
No GPU or ARM/NEON hardware tests, non-Linux affinity tests, hosted CI, or remote
publication were performed. No fresh paired comparison to vanilla-C runtime is
claimed; the performance baseline here is the same binary's fit-only scheduler.

## Final acceptance and timings

The final binary passes 52 workspace release tests and 27 CPU debug tests; four
CUDA hardware tests are ignored/not_run. All-features compilation, formatting and
whitespace checks pass. The audit rechecks 570 human bootstrap outputs, 32
synthetic comparisons and two complete single-fit comparisons. Bootstrap seeds
and every draw are replayed, and all timed batches actually used 16 workers.

The broader pinned-C suite passes 338 applicable checks and ten complete internal
traces on identical arithmetic source, frozen just before the CLI-only admission
fix. Its raw status remains failed because two historical tests still expect
CPU equivalent mode to be rejected. Those availability checks are explicitly
obsolete; all other cases pass. The final binary separately reruns goldens and
full human scheduling comparisons after the admission fix.

One warmup and three alternating measured pairs per mode, HG001 30 bootstraps,
64 states, 30 iterations, 16 workers and a 16GiB admission budget:

| Median | Fit-only | Shared | Wall reduction |
|---|---:|---:|---:|
| equivalent wall seconds | 10.047 | 9.477 | 5.67% |
| strict wall seconds | 46.473 | 44.024 | 5.27% |

Both final modes pass the >=5% median / >=2-of-3 wins gate, with three wins each.
Shared scheduling becomes the CPU batch default. The earlier pre-admission-fix
paired run measured 4.55% in equivalent (below the improvement threshold) and
7.67% in strict. Those reports are retained; the additional run was required by
the memory-accounting code change, not selected to erase a failed measurement.
These modest gains are sensitive to shared-host variation.

| Mode | Fit CPU seconds | Shared CPU seconds | Fit RSS KiB | Shared RSS KiB |
|---|---:|---:|---:|---:|
| equivalent | 136.03 | 140.27 | 33948 | 37272 |
| strict | 611.08 | 643.50 | 1315508 | 960748 |

Sharing lowers wall time but consumes about 3% more aggregate CPU in equivalent
and 5% more in strict. CPU/(16 × wall), calculated from the medians, rises from
84.6% to 92.5% in equivalent and 82.2% to 91.4% in strict; it does not reach 95%.
Median completed idle-helper jobs are 1,854 and 1,736 respectively. RSS is a
measured peak, not a promise for different record lengths or state counts.

Single-fit screens on the existing split HG001 records measure strict
12.943 → 4.875s and equivalent 3.236 → 1.222s with 1 vs 16 record workers.
These are exact-output screens, not repeated latency benchmarks. Unsplit
one-record inputs cannot obtain that record-parallel benefit.

The larger gain is the separately accepted linear E-step: v0.5.1 equivalent
35.031s vs v0.6.0 equivalent 11.310s (3.10×, paired). The final scheduler
benchmark above uses v0.6.1 fit-only as its control; do not treat the two
staged comparisons as one contemporaneous pair against v0.5.1 or vanilla C.

Final evidence: `bench/shared-records-final-validation.json`,
`bench/shared-records-final-performance.json`, `bench/shared-records-audit.json`,
and `bench/shared-records-strict-regression.json`. Installed binaries and hashes
are recorded in `bench/shared-records-install.json`; all earlier binaries remain.

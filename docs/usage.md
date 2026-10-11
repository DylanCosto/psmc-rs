# CLI usage and controls

Run `--help` for the complete supported list.

Single fits default to available CPU workers and a memory admission budget of half
available memory. Bootstrap batches default to 30 replicates, available CPU workers,
2048 MiB and the shared scheduler. Specify budgets that leave room for other work.
These are estimates, not hard OS RSS ceilings; input loading precedes admission.

The inherited default pattern is `4+5*3+4` (23 states); choose your pattern explicitly.

Use `--progress` for iteration/completion messages on stderr. Use `inspect INPUT`
for encoded input counts, `split --help` for record-preserving block construction,
and `export --help` for unit-explicit curve CSV. Output files for these utilities
must be new. `bootstrap --resume` verifies completed fits; see
[the complete resume contract](bootstrap-resume.md).

Bootstrap replicate i uses base seed+i and the original ordered draw/stopping
rule. Duplicates retain multiplicity even when their computations are cached.
Use `--workers` for batches, `--record-workers` for single fits. The shared scheduler
lets idle fit workers help records while retaining input-order reductions;
`--scheduler fit` selects fit-only scheduling. Mode selection is documented in
[modes and guarantees](modes-and-guarantees.md).

| Option | Purpose |
|---|---|
| `-p -N -t -r -l -I` | Pattern, iterations, maximum time, theta/rho, grid alpha, initialization |
| `-i -o` | Supplied parameter file and output path |
| `-b --seed INTEGER` | One legacy ordered-record bootstrap and reproducible RNG seed |
| `-d -D -s -C` | Posterior segments, full posterior, scales and transition cap |
| `-T` | Legacy divergence parameter, subject to supplied-file checks |
| `--backend cpu\|dense` | Optimized CPU (default) or retained scalar oracle |
| `--simd auto\|off\|avx` | Runtime AVX dispatch, generic path or require AVX |
| `--cache on\|off` | Repeated-record cache within one exact parameter snapshot |
| `--stats FILE` | Single-fit counters and instrumented E/M timers |
| `--snapshot FILE` | Large test-only messages, counts and optimizer traces |

Snapshot execution bypasses record sharing and count-only caching so every
occurrence's messages can be inspected. Do not use snapshots or instrumented
phase timings for throughput claims. Batch phase timing is disabled; counters
remain active. `PSMC_SEED`, `PSMC_SNAPSHOT`, `PSMC_BOOTSTRAP_TRACE` are supported
harness controls; unset them for ordinary benchmark runs.

The original `-c` and `-S` are rejected (`-S` is not a seed option). Direct VCF/long-read conversion is not implemented. Inspection, splitting,
CSV export and completed-fit bootstrap resume are available; see the tutorial.
Parameter files contain the raw PA payload, without its `PA` prefix. An explicit
time grid cannot also supply divergence; ordinary supplied parameters with `-T`
must include their own trailing divergence.

Some inputs make vanilla PSMC produce NaN/Inf. Rust preserves reference behavior
and warns on nonfinite fit records. A successful exit does not certify finite
inference; the expected round-zero `RI inf` is treated separately. Malformed input,
unsafe parameter combinations, path aliases and all-missing input without explicit
initial parameters are rejected. Streaming output writes are not atomic.


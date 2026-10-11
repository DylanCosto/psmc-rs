# Strict single-fit memory admission — v0.6.3

Strict CPU single fits now limit record workers using an explicit memory estimate.
The default is half detected available memory, limited by finite cgroup headroom
on Linux where exposed; unknown platforms use 1024 MiB. `--memory-mib MIB`
overrides the budget. Explicit `--record-workers` cannot bypass admission.
Equivalent single fits retain their worker default. Bootstrap's existing budget
is unchanged; both estimators use the same checked message-size formula.

## Why reserve the largest record

A history needs `(length+1)*(2*states+1)*8` bytes: forward, backward and scales.
Workers retain those buffers in thread-local storage when a record finishes.
Only counting currently active jobs would release reservations too soon.
Instead, admission reserves a largest-record slot for each admitted worker for
the duration of the fit. Shared fits also reserve the owner's possible serial
workspace; decoding adds another history and its path buffer. Queued observation
copies, input capacity, retained count results/cache, model layouts and overhead
are included. All size arithmetic is checked.

This conservative policy can admit fewer workers than a more complex scheduler
that shrinks idle buffers or packs short records dynamically. It avoids changing
record arithmetic, reduction order or the existing record queue. A 64-state fit
with sixteen 2.5M-bin chromosomes and a 9 GiB budget admits two workers in the
size-model test rather than launching all sixteen.

Admission happens after input parsing/sampling and before opening output, stats,
snapshot or bootstrap-trace files. A budget that cannot admit one record is an
error, including an explicit one-worker request. Stderr reports admission;
`--stats` includes budget, requested/admitted workers, estimate and largest
message allocation. Other processes can consume memory later; allocator behavior,
platform detection and unmodeled overhead mean this is not a hard RSS limit.
Input parsing itself precedes admission. Multiple independent processes do not
share reservations; allocate their budgets explicitly or use the batch runner.

## Measured regression

Eight distinct 1M-bin records, 64 states, two full E/M iterations, f64, cache on.
These are allocation/order tests, not scientific qualification or a speed campaign.
All outputs below match v0.6.2 serial exactly apart from the version line:

| Run | Requested workers | Admitted | Peak RSS |
|---|---:|---:|---:|
| v0.6.2 serial | 1 | 1 | 995 MiB |
| v0.6.3, 2048 MiB budget | 16 | 1 | 995 MiB |
| v0.6.3, 3500 MiB budget | 16 | 2 | about 1988 MiB |

See [raw summary](../bench/strict-memory-rss.json) for exact RSS, diagnostic times,
binary/input hashes and commands. Reproduce with
`python3 bench/strict_memory.py --output work/new-memory-screen`.
The unsafe eight-worker allocation is not rerun; the user's 8.1 GB measurement
motivated the regression and is not presented as an independent measurement here.

59 workspace release tests pass, including checked overflow, insufficient budgets,
retained workspaces, decoding reserve, mixed record lengths, cgroup parsing, and
failure before truncating an existing output. Golden and ordered-output tests
remain exact. Four CUDA hardware tests are ignored/not_run. No inference math,
optimizer, observation boundary or precision changed. Source baseline: bf4d1a1.
The source, tests and memory evidence are committed together.

A full 30-iteration 200 Mb check additionally admitted three workers under a
512 MiB budget, estimated 462,314,683 bytes and measured 311,096 KiB peak RSS
(about 304 MiB). Its output exactly matched the serial strict fit. See
[full-fit evidence](../bench/strict-memory-full-fit.json). This validates ordered
reduction across a complete fit; the larger eight-record screen above tests
allocation growth with longer individual records.

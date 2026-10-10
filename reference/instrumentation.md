# Test reference instrumentation

`instrument.py SOURCE DESTINATION` creates a separate instrumented copy of
`lh3/psmc` commit `82fa2ada83ee463fe1251b562ae3d60e82d7ad6a`. It never edits the
source directory, refuses an existing destination or a destination inside the
source, checks SHA-256 of every transformed upstream file, and requires each
replacement anchor to occur exactly once. The generated
`instrumentation-manifest.json` records before/after source hashes and the
instrumenter hash. The enclosing reference build records compiler and executable
provenance. Build the generated tree with the same configuration as the normal
reference.

The original `LICENSE.txt` and source notices are copied unchanged. New helper
files are additive. Modified upstream files retain their original content and
notices except for instrumentation additions. The instrumenter changes
`main.c`, `core.c`, `em.c`, `aux.c`, and the object list/dependencies in `Makefile`;
it does not change `khmm.c` or `kmin.c`.

## Runtime interface

All controls are optional environment variables. Paths are opened in write mode,
so use a different path for each run and each output stream. Parent directories
must already exist. An open failure exits with status 2 instead of silently
omitting requested evidence. The normal PSMC output destination remains
unchanged.

| Variable | Meaning |
|---|---|
| `PSMC_SEED` | Decimal signed `long` passed to `srand48` after the original automatic seeding and before CLI parsing/bootstrap resampling. Invalid or overflowing values exit 2. An unset or empty value preserves automatic seeding. |
| `PSMC_SNAPSHOT` | JSONL internal snapshots, potentially very large. |
| `PSMC_PROFILE` | JSONL wall-clock phase timings and optimizer evaluation counts. |
| `PSMC_BOOTSTRAP_TRACE` | JSONL draw indices and exact accept/stop decisions. |

Upstream `-S` means **simulate**, not seed. `PSMC_SEED` does not add an extra RNG
draw. For a bootstrap, draws happen during CLI parsing before the initialization
draws. Even with `-I 0`, original initialization still consumes RNG draws.

Example, from the project directory after building the reference copy:

```sh
PSMC_SEED=42 PSMC_SNAPSHOT=work/tiny.snapshots.jsonl \
PSMC_PROFILE=work/tiny.profile.jsonl \
work/instrumented/psmc -p '2+2' -N 2 -I 0 tests/fixtures/tiny.psmcfa
```

Use the actual fixture path created by the validation harness. This command is
an interface example, not an additional claimed test case.

## Snapshot schema

Every line is one JSON object. Finite floating-point values use `%.17g`, which
round-trips binary64. Nonfinite values are explicit strings `"nan"`, `"inf"`, or
`"-inf"`; consumers must handle these rather than assuming every value is a JSON
number. Arrays preserve source loop order. No rounding, normalization, summation,
or numerical repair is done by the logger. Array indices are zero-based except
for the existing HMM position convention described below.

| `event` | Fields and meaning |
|---|---|
| `model` | `iteration`, monotonically increasing `model_id`, `states`, `symbols`, `params`, `par_map`, `t`, `initial`, `transition`, `emission`, `sigma`, `C_pi`, `C_sigma`. One record after every existing model construction, including every candidate objective evaluation. Initialization has iteration 0. |
| `sequence` | `iteration`, `model_id`, `index`, `name`, `length`, encoded `observations`, `scales`, `forward`, `backward`, `log_likelihood`, `A0`, `A`, `E`, `stored_Q0`. Captured after the existing expectation computation, before aggregation/free. |
| `aggregate` | `iteration`, `model_id`, summed `log_likelihood`, `A0`, `A`, `E`, `stored_Q0`. Captured after the existing `hmm_Q0`; this `stored_Q0` is the entropy normalizer, not the printed pre-M-step normalized Q. |
| `objective` | `iteration`, `model_id`, `evaluation` (1-based within EM iteration), optimizer `raw_params`, model `params` after existing `fabs`, and `negative_Q`, exactly the value returned by the existing callback. |
| `em_end` | `iteration`, `model_id`, `optimizer_evaluations`, final mutated `params`, printed-state `Q0`, optimizer-returned `Q1`, `last_candidate_Q`, `log_likelihood`, `post_sigma`. |

`transition[source][destination]`; `emission[symbol][state]`. The emission arrays
include the missing-observation row (`symbols`), so normal PSMC has 3 rows for
observations 0, 1, and 2. `observations` has length L and its first element is HMM
position 1. `scales`, `forward`, and `backward` include position 0 and have L+1
rows/elements. The unused position-zero entries are exposed exactly as allocated
and initialized; backward position zero is zero. Sequence names preserve bytes
through JSON escaping; non-ASCII bytes are emitted as `\u00XX`.

Counts include the original `HMM_TINY` initialization and the original omission
of the final position from emission accumulation. Sequence missing-row counts
are present; the aggregate missing row stays zero because the original
`hmm_add_expect` excludes it. `A0` is captured even though the objective does not
use it. Sequence `stored_Q0` has not been computed and remains its original zero.

The existing optimizer may return a Q value whose parameter state differs from
the final callback's side effects. `em_end` exposes both `Q1` and
`last_candidate_Q`. The latter is obtained from the existing final callback;
the logger does not call the objective again or restore parameters.

## Bootstrap schema

Each `bootstrap_draw` has `draw` (0-based), `source_index` (0-based), `length`,
`accepted` (boolean), `before_length`, `after_length`, `target_length`, and `stop`
(boolean). Lengths here include missing observations, exactly as in upstream
`psmc_resamp`. `bootstrap_end` has `accepted_sequences`, final `length`, and
`target_length`. The final rejected draw is retained. Repeated accepted indices
are separate observations and must not be deduplicated.

The trace reads the already chosen sequence pointer and existing integer
comparisons; it performs no random draws and makes no resampling decisions.

## Profiling schema and limits

`startup` records contain `phase` (`cli_input_bootstrap` or `initial_model`) and
`seconds`. Each `em_profile` contains `iteration`, `optimizer_evaluations`,
`total_seconds`, and:

- `forward_seconds`, `backward_seconds`, `expectation_seconds`: inclusive wall
  time around the respective unchanged HMM calls, including their allocations.
- `expectation_merge_seconds`, `likelihood_seconds`, `pre_backward_seconds`,
  `q_normalizer_seconds`: the respective unchanged calls.
- `model_seconds`: all model-construction work in that iteration, including
  temporary allocations and frees, excluding model snapshot serialization.
- `q_seconds`: pre-M-step Q plus candidate Q calls, excluding model construction,
  optimizer overhead, and snapshot serialization.
- `m_step_seconds`: the whole maximization block, including normalizer, model
  construction, objective evaluations, optimizer, IT printing, and any snapshots.
- `allocation_setup_seconds`: only aggregate-count allocation and per-sequence
  copy/HMM-data setup. This is **not all allocation time**; allocations inside the
  HMM/model calls remain attributed to those calls.
- `free_seconds`: explicit end-of-sequence and aggregate frees, excluding frees
  internal to the timed HMM/model calls.

Durations use `CLOCK_MONOTONIC`. `m_step_seconds` overlaps model/Q/normalizer
durations and must not be added to them. `total_seconds` also includes logging
overhead and post-sigma updates. Initial model construction is reported as
startup and excluded from later per-iteration model totals. Timers do not split
output I/O from computation or decode/simulation phases. Use the normal binary
for end-to-end timing, a sampling profiler for attribution, and profile-only
runs with `PSMC_SNAPSHOT` unset for these diagnostic phase timings. Logging may
perturb cache behavior, allocation layout, and wall time; these are not unbiased
performance benchmarks. The instrumented build retains small helper-call
overheads even with all logging disabled.

## Verification performed

A local smoke check used a synthetic two-sequence fixture (lengths 20 and 29,
including missing observations), `-p '2+2' -N 2 -I 0`, the pinned normal binary,
and the instrumented binary with seed 42, snapshots and profiling enabled.
Their complete stdout was byte-identical, without metadata normalization.
All snapshot/profile lines parsed as JSON; the two EM evaluation counts agreed
with the snapshot summaries. The run emitted 1,910 model records, 1,909 objective
records, four sequence records, two aggregates, and two EM summaries. A seeded
bootstrap smoke run traced accepted source indices `[1, 0]`, totaling 49 bases,
and its stopping record parsed successfully.

Those checks establish narrow instrumentation parity, not broad Rust or
cross-platform equivalence. The parent validation harness supplies the durable
fixture matrix and paired materialized-bootstrap comparisons. No acceleration
or scientific calculation has been implemented here.

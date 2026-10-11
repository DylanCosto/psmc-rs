# PSMC-rs 0.7.0 — equivalent CPU default

**Breaking output change: use `--mode strict` for exact C reproduction on the
pinned tested build** (excluding the version header). CPU commands that omit
`--mode` now produce equivalent results, which are not byte-identical to C.
Their objective diagnostic changes from `QD` to `QU`. Third-party scripts parsing
`QD` must use strict or explicitly support QU's different meaning; renaming the
tag is not a valid conversion. Upstream history/plotting utilities do not consume
the objective diagnostic, while `psmc_trunc.pl` preserves it verbatim.

Released locally on 2026-10-11 after candidate and final compatibility/resource
checks passed. `bin/psmc-rs` and `bin/psmc-rs-v0.7.0` are the verified final build;
earlier releases and `bin/psmc-rs-v0.7.0-rc.1` remain available. No remote release
was published.

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

## Final release verification

Final 0.7.0 repeated all 61 Rust tests, the 25 compatibility checks against the
candidate, and all three bounded resource checks. Four optional GPU hardware tests
remain ignored. Four live C golden cases passed, as did 14 known-truth Python and
10 HG001 Python tests. Formatting and CUDA-feature compile checks passed. Strict
golden tests now name `--mode strict` explicitly; their reference data and tolerance
are unchanged, including in the existing hosted-CI workflow (not run remotely).

The final eight-million-bin strict regression admitted one worker under 2048 MiB,
peaked at 994.9 MiB and matched the prior strict result. Equivalent with decoding
admitted eight workers under 3500 MiB and peaked at 1089.8 MiB. The final N30 HG001
default fit admitted 16 workers under 8192 MiB and peaked at **480.1 MiB**, exactly
matching the previously audited equivalent output. All resource guards held;
fallbacks remain reported. These checks exercised the installed build's exact
binary hash before installation; an installed-executable smoke check also verifies
default equivalent and explicit strict selection.

Candidate source commit: `0ad72cac5ca18420a2b2fbc8e9a7b7c4fc481f21`.
Final executable source commit: `d42a7cfbbbf836c8cfac32da7605809c330710d3`.
The only candidate-to-final source change is the workspace/package version.
Final executable SHA256:
`aed1c1da7bd9140f9c2156a924d1220f74c985f0b7983b308457f68389eb170e`.
[Release evidence](../bench/default-transition-results.json) records both binaries,
commands, raw output digests, test summaries, counters and admission/RSS results.
Current/versioned installed files match the tested release executable byte for byte.

Commands used include:

```bash
cargo build --release --offline -p psmc-cli
cargo test --release --locked --offline --workspace
cargo fmt --all -- --check
cargo check --release --locked --offline -p psmc-cli --features cuda
python3 bench/ci_strict_reference.py --reference work/vanilla/psmc
python3 bench/default_transition.py --binary target/release/psmc-rs --previous bin/psmc-rs-v0.7.0-rc.1 --output work/default-transition-final
python3 bench/default_transition_resources.py --binary target/release/psmc-rs --output work/default-transition-final-resources
python3 -m unittest discover -s bench -p 'test_known_truth*.py'
python3 -m unittest discover -s bench -p 'test*hg001*.py'
```

Use new output directories when reproducing. The release adds mode selection and
equivalent admission in the CLI, preserves numerical engine files and strict/batch
admission formulas, updates explicit-mode golden/CLI tests, and adds downstream
and resource harnesses, README/help, protocol, notes and compact evidence.

Prior [whole-autosome agreement](hg001-genome-report.md), [known-truth panel](known-truth-200mb-report.md)
and [linear-mode controls](linear-equivalent-report.md) remain supporting evidence.
Default promotion does not claim universal scientific equivalence. The user's
actual input/preprocessing, whole-genome bootstrap uncertainty, other CPUs/ARM,
non-Linux and new GPU hardware qualification remain outside this release check.
Hosted CI and remote publication require a configured remote; no remote release
is claimed. Historical runners/protocols belong to their recorded source/binary
versions and must not be silently replayed against a new implicit default.

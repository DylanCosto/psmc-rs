# What has been validated

Validation is specific to an input, configuration and platform. This index separates
engineering regressions, scientific screens and performance measurements. Passing
one does not imply the others.

| Evidence | Scope and interpretation |
|---|---|
| Pinned-C regression | Strict numerical output bytes, excluding version, with original C model/optimizer behavior on saved synthetic cases |
| Native Linux CI | x86-64 and ARM64 builds, Rust/component tests, live C golden comparison, archive extraction and short fits |
| Bootstrap resume | Real process interruption, verified completed-result reuse, exact output/draw parity, tamper and concurrent-writer rejection on synthetic batches |
| Public HG001 whole autosomes | Same-input C/strict/equivalent comparison; no demographic ground truth |
| Broader production campaign | In progress: thirty whole-genome bootstrap pairs; additional 23/32-state public-input fits and C compiler controls; no completed result claimed yet |
| Known-truth 200 Mb panel | Prospective primary-band/event criteria across 30 simulated datasets, with strict/C parity |
| Initial 20 Mb pilot | Failed screens retained; weak recent-time recovery and four outliers investigated, not erased |
| Stable-model prototype | Diagnostic-only component/fixed-parameter accuracy and synthetic refits; not production arithmetic |
| Controlled speed benchmark | v0.6.3, one public HG001 fit, fixed affinity/resources, one warmup plus three measured runs per configuration |

## Reports and protocols

- [Whole-autosome numerical comparison](hg001-genome-report.md)
- [Broader release qualification protocol](adoption-qualification-protocol.md) (campaign in progress)
- [200 Mb known-truth panel](known-truth-200mb-report.md)
- [Original pilot report](qualification-report.md) and [outlier diagnostics](pilot-ridge-report.md)
- [Stable-model investigation](stable-model-report.md)
- [Controlled speed report](hg001-speed-report.md) and [benchmark protocol](hg001-speed-protocol.md)
- [Detailed mathematical contract](../MATH_AND_COMPATIBILITY.md), [validation policy](../VALIDATION_AND_BENCHMARKS.md)
- [Native binary workflow](../.github/workflows/binaries.yml) and [hosted results](https://github.com/DylanCosto/psmc-rs/actions)

The known-truth scientific panel used `4+25*2+4+6` (64 states). Additional-pattern
real-data comparisons broaden empirical implementation coverage; they do not provide
known-truth demographic validation for every pattern. The inherited CLI default
pattern is `4+5*3+4`; choose your analysis pattern explicitly.

The public VCF-plus-confidence-BED fixtures have ascertainment limitations and
are not a recommended demographic preparation pipeline. Your actual input,
callability masks, splitting procedure and scientific settings need their own checks.
No raw genomic input is redistributed in the repository or binary archives.

## How to reproduce and report a problem

Run `cargo test --workspace --release --locked --offline` for local regressions.
Hosted native jobs build the pinned C source independently. Use the protocol's
recorded source commit and commands for a historical campaign; old reports are
not replaced by rerunning scripts on a newer tree. Large historical raw evidence
has [local archive provenance](evidence-archive.md); compact reports and reproduction
scripts remain in Git.

Start a bug report with version/mode, platform, complete command, stats and a tiny
synthetic reproducer. For numerical differences, preserve every failing seed and
avoid changing iterations, masking, state pattern or other scientific settings to
make a comparison pass. Native ARM regression success is not whole-genome ARM
qualification; untested hardware and configurations should be labeled as such.

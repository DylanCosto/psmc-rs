# Modes and guarantees

| Property | Strict | Equivalent |
|---|---|---|
| CPU selection | `--mode strict` | CPU default; `--mode equivalent` |
| Precision/model | f64, original PSMC model/optimizer | f64, same model/optimizer, different arithmetic grouping |
| Output claim | Exact pinned-build C bytes except version line, on tested inputs | Empirical agreement within documented screens; not byte-identical |
| Objective diagnostic | QD, including original entropy normalizer | QU, omitting a round-constant term; compare only within that round |
| Messages/counts | Dense legacy arithmetic and full counts | Structured scans, transition margins and bounded checkpoints |
| Snapshots | Supported | Explicit equivalent + snapshot rejected |

With no explicit mode, dense/CUDA backends and snapshots select strict. Explicit
equivalent requires CPU and cannot use snapshots. The selected mode is recorded
in stderr, output `MM Version`, statistics and batch manifests. Mode selection
is independent of option order. Report it with the software version in methods.

Strict retains original calculation order, missing-bin handling, record boundaries,
optimizer callback behavior and the legacy Q normalizer. It matches the tested
C build, not all compiler flags, FMA policies, libm versions or CPU architectures.
Reference pathologies remain visible; a successful exit does not imply finite
inference. The special initial-round `RI inf` is expected and treated separately.

Equivalent may take a different optimizer path after a rounding difference in a
comparison. Every occurrence of a repeated bootstrap block still contributes;
caching saves work without dropping observations. Structured ineligibility uses
the existing literal fallback and increments the corresponding counters.
The stable-formula diagnostic prototype is not part of either production mode.

Within a tested mode and runtime, independent-record scheduling preserves reduction
order and fitted output. Changing worker counts is covered by exact output tests.
This does not promise cross-runtime bit reproducibility or validate arbitrary
input preparation, demographic histories, patterns or parameter extremes.

Upstream PSMC plotting/history utilities do not consume QD, but third-party tools
may. QU is a different diagnostic quantity, not a renamed QD. Use strict if your
workflow needs the original format or byte comparison against the pinned C build.
See the detailed [mathematical contract](../MATH_AND_COMPATIBILITY.md),
[validation overview](validation-overview.md) and [0.7.0 transition notes](release-0.7.0.md).

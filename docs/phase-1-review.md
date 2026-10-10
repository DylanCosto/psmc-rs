# Independent Phase 1 CLI and I/O review

All **11 targeted controls passed** against release executable SHA-256
`e112ed9a8d7d98cc5e29f497e8567e1de96f3e0210a0cb324a79dc91c5e65dd0`.
The digest was checked before and after the controls. Exact results, commands,
source hashes, and stderr are recorded in [the review evidence](../bench/phase1-review.json).
This is a CLI and safety review; numerical parity is validated separately.

The review identified and rechecked fixes for input hardlinks, aliases of new
output paths, bootstrap trace collisions, dangling output symlinks, redirected
stdin/stdout aliases, round-zero snapshot flush failures, and unreported
nonfinite initial/live models. Rejected write aliases exit with status 2 before
changing the synthetic input. A snapshot written to `/dev/full` reports its
buffered error even with `-N 0`. An all-heterozygous round-zero control retains
legacy nonfinite output and emits a warning; the finite control remains quiet.
Ordinary redirected stdin still succeeds.

Source review found no additional material issue in decoding/cap order,
probability-output precedence, posterior tie-breaking, final-segment precision,
JSON nonfinite classification, or preservation of the EM optimizer's final
callback side effects. No inference source was edited during this review.

The supported scope remains the tested Linux/libm/system-zlib stack. Parsing
uses finite decimal/exponent numbers and rejects C hexadecimal-float tokens,
malformed/empty/non-ASCII sequence inputs, unsupported supplied-grid/divergence
combinations, more than 255 parameter groups, and bootstrap raw totals outside
the legacy signed-int stopping-rule range. Filesystem identity checks prevent
ordinary aliases; they do not claim protection against concurrent adversarial
path replacement. No acceleration or GPU result is established here.

A prior shared-release rebuild invalidated a concurrent numerical validation
attempt. That interrupted attempt must not count as passing evidence; the
numerical validation is rerun against an immutable executable copy. The final
targeted review recorded here did not rebuild any executable.

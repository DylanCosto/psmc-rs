# Current local v0.6.1 CPU deliverable

`bin/psmc-rs` and `bin/psmc-rs-v0.6.1` are the final tested binaries. Strict remains
the numerical default; equivalent uses the linear E-step and QU diagnostics.
CPU bootstrap batches default to shared scheduling; `--scheduler fit` selects
the prior policy. Single fits support `--record-workers N` for existing records.
See [results](docs/shared-record-results.md), [audit](bench/shared-records-audit.json)
and [installation hashes](bench/shared-records-install.json). All earlier versioned
binaries and CUDA artifacts are preserved. No new portable archive is generated;
existing zip files and CHECKSUMS.sha256 describe historical snapshots.

# Historical local v0.6.0 CPU deliverable

`bin/psmc-rs` and `bin/psmc-rs-v0.6.0` contain the tested linear equivalent E-step.
Strict remains default. Equivalent prints QU and has a new numerical contract.
See [results](docs/linear-equivalent-report.md), [audit](bench/linear-equivalent-audit.json),
and [installation](bench/linear-equivalent-install.json). Earlier binaries and
archives remain unchanged. No new portable archive is generated.

# Historical local v0.5.1 CPU deliverable

`bin/psmc-rs` and `bin/psmc-rs-v0.5.1` provide strict mode by default and optional
structured CPU mode. Bounded four-record AVX reduces measured equivalent-mode
batch wall time 7.74%, CPU time 8.03% and RSS 18.16%, preserving its numerical
output exactly. See [the review and results](docs/equivalent-followup.md),
[the evidence audit](bench/equivalent-followup-audit.json) and
[installation manifest](bench/equivalent-followup-install.json).
The original numerical screens are retained as historical engineering evidence;
scientific equivalence is not inferred from their pass/fail labels. v0.5.0,
v0.4.1 and the CUDA executable are preserved. No new portable archive is generated.
Existing zip files and CHECKSUMS.sha256 are historical snapshots.

# Historical local v0.5.0 CPU deliverable

The v0.5.0 milestone introduced opt-in experimental `--mode equivalent` while
keeping strict as default. Its versioned binary remains in `bin/psmc-rs-v0.5.0`.
It passed the performance gate and failed the original full-fit engineering
screens, whose scientific interpretation is revised in the follow-up above. See
[the implementation and results](docs/equivalent-mode-report.md),
[final audit](bench/equivalent-audit.json) and
[installed binary manifest](bench/equivalent-install.json).
The v0.4.1 CPU executable remains available; the optional CUDA binary is unchanged.
No new portable archive is generated. Existing zip files and CHECKSUMS.sha256
remain historical snapshots and do not describe this working tree.

# Historical local v0.4.1 optimization deliverable

That milestone contained the v0.4.1 CPU source and executable, an optional
CUDA build, and the complete optimization campaign reports/runners. See
[the campaign report](docs/optimization-exhaustion.md),
[final build provenance](bench/exhaust-final-build.json),
[evidence audit](bench/exhaust-audit.json) and
[installed binary manifest](bench/exhaust-install.json).
Previous CPU and CUDA executables remain under versioned names in `bin/`.
No new portable zip is produced by this optimization milestone. The older zip
archives, package manifests and `CHECKSUMS.sha256` below are historical snapshots;
they do not describe the current working tree. Raw traces, prototype sources,
public inputs and build environments remain local and excluded from Git.

# Parallel milestone package contents

`../psmc-rust-parallel.zip` adds the full-core benchmark and correctness evidence
to the retained Rust 0.3.1 release. `bin/psmc-rs` is unchanged; the rejected
experimental scheduler under `bench/parallel/` is evidence only.
`bench/package_parallel.py` creates and verifies CRCs and every member SHA-256.
See `bench/parallel-package-manifest.json` for scope and exclusions and the sibling
`.zip.sha256` for the archive digest. All earlier archives remain untouched.

# CPU campaign package contents

`../psmc-rust-cpu-campaign.zip` is the local Rust 0.3.1 source-and-evidence package.
It includes source, pinned toolchain/lockfile, `bin/psmc-rs`, preserved Phase 1/2/3a
executables, synthetic fixtures, pinned reference build scripts/licenses,
derivations, exactness checks, benchmark runners, reports and ordinary raw output.
No private genome was accessed or uploaded. Verify the extracted package with:

```sh
sha256sum --check CHECKSUMS.sha256
```

`bench/package_cpu_campaign.py` recreates it under one-CPU affinity at reduced priority,
checks archive CRCs and verifies every member against its SHA-256. The archive
has a sibling `.zip.sha256` file. `bench/cpu-campaign-package-manifest.json` records
exclusions. Build/runtime caches (`work/`, `target/`, `.git/`, Python caches), test
symlinks and compressed internal JSONL snapshots are omitted. Exact snapshot
paths, sizes and hashes are in `bench/cpu-campaign-snapshot-manifest.json`; full streams
remain in the local project. Every snapshot event was compared before compression.

Reproduce new snapshots by building the C references and `simd_bench`, then running
`taskset -c CPU nice -n 10 python3 bench/cpu_campaign_release_gates.py` from the project.
Use an allowed logical CPU. The new gate includes the full K64 trace for automatic
AVX. Source and commands for historical snapshots are in the unchanged Phase 1/2
archives and their manifests. Historical package/build reports describe those
releases; only current CPU campaign reports identify the delivered executable.

The Linux binary is dynamically linked for the tested x86-64/glibc stack.
`bench/cpu-campaign-build.json` records compiler, system libraries, release settings and
source digests. The default compiled ISA stays generic; guarded AVX functions are
selected at runtime. `--simd off` exercises the generic CPU path on this host;
physical no-AVX and ARM machines have not been tested. No cross-platform bitwise
claim or globally native-only binary is implied.

Source, derivations, tests and measurements are committed together locally.
Git history is excluded from this portable zip. Prior archives remain unchanged.
Raw shared-host timing ranges and CPU time remain visible; packaging does not
convert diagnostic measurements into a production or 10× claim.

Campaign experiment runners that inject alternative kernels/caches require the
Phase 3a baseline source. Reproduce those screens using the preserved Phase 3a
source archive (or commit `6a4d102`) with the campaign benchmark files copied in.
Do not inject baseline-only transformations into the final 0.3.1 source. The final
release gate runs directly from this package after rebuilding the pinned C
references. It additionally uses the pinned toolchain's Clippy component for an
advisory lint pass; existing reference-code style warnings are recorded.

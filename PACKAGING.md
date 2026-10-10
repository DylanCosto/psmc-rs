# Phase 3a SIMD package contents

`../psmc-rust-phase-3-simd.zip` is the local Rust 0.3 source-and-evidence package.
It includes source, pinned toolchain/lockfile, `bin/psmc-rs`, preserved Phase 1/2
executables, synthetic fixtures, pinned reference build scripts/licenses,
derivations, exactness checks, benchmark runners, reports and ordinary raw output.
No private genome was accessed or uploaded. Verify the extracted package with:

```sh
sha256sum --check CHECKSUMS.sha256
```

`bench/package_phase3.py` recreates it under one-CPU affinity at reduced priority,
checks archive CRCs and verifies every member against its SHA-256. The archive
has a sibling `.zip.sha256` file. `bench/phase3-package-manifest.json` records
exclusions. Build/runtime caches (`work/`, `target/`, `.git/`, Python caches), test
symlinks and compressed internal JSONL snapshots are omitted. Exact snapshot
paths, sizes and hashes are in `bench/phase3-snapshot-manifest.json`; full streams
remain in the local project. Every snapshot event was compared before compression.

Reproduce new snapshots by building the C references and `simd_bench`, then running
`taskset -c CPU nice -n 10 python3 bench/phase3_validate.py --run` from the project.
Use an allowed logical CPU. The new gate includes the full K64 trace for automatic
AVX. Source and commands for historical snapshots are in the unchanged Phase 1/2
archives and their manifests. Historical package/build reports describe those
releases; only current Phase 3 reports identify the delivered executable.

The Linux binary is dynamically linked for the tested x86-64/glibc stack.
`bench/phase-3-build.json` records compiler, system libraries, release settings and
source digests. The default compiled ISA stays generic; guarded AVX functions are
selected at runtime. `--simd off` exercises the generic CPU path on this host;
physical no-AVX and ARM machines have not been tested. No cross-platform bitwise
claim or globally native-only binary is implied.

Source, derivations, tests and measurements are committed together locally.
Git history is excluded from this portable zip. Prior archives remain unchanged.
Raw shared-host timing ranges and CPU time remain visible; packaging does not
convert diagnostic measurements into a production or 10× claim.

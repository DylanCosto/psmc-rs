# Phase 2 package contents

`../psmc-rust-phase-2.zip` is a local source-and-evidence package rooted at
`psmc-rs/`. It includes Rust 0.2 source, pinned toolchain/lockfile, `bin/psmc-rs`,
the preserved `bin/psmc-rs-phase1`, synthetic fixtures, reference build scripts
and licenses, derivations, validation/benchmark runners, machine-readable reports,
ordinary raw evidence and `CHECKSUMS.sha256`. From the extracted root:

```sh
sha256sum --check CHECKSUMS.sha256
```

`bench/package_phase2.py` recreates the package, tests archive CRCs and verifies
every member's SHA-256 against the source file. `bench/phase2-package-manifest.json`
records exclusions. Build/runtime caches (`work/`, `target/`, `.git/`, Python
caches), test symlinks and large compressed internal snapshot streams are excluded.
`bench/phase2-snapshot-manifest.json` records each omitted stream's exact path,
compressed size and SHA-256. The original Phase 1 ten-file snapshot manifest is
also retained; its historical scope does not include new Phase 2 runs.

Complete snapshots remain in the local project. Comparisons read every event
before compression; packaging does not truncate correctness tests. Recreate
Phase 2 snapshots with `python3 bench/phase2_validate.py --run` after rebuilding
the pinned C references. Historical Phase 1 snapshots require the source in the
unchanged Phase 1 archive and the commands in its snapshot manifest.

Both the preliminary and final Phase 2 validation runs remain as separately
identified evidence. Only the final executable hash in the Phase 2 parent reports
supports the delivered result. Corrected review failures and the initial model
performance regression remain labeled historical; neither is silently deleted.
The Phase 0 and Phase 1 archives are unchanged. Historical Phase 1 package/build
manifests describe that prior release, not this archive's current source.

The Linux executable is dynamically linked for the tested x86-64/glibc stack.
Shared dependencies, toolchain, profile and all build-source hashes are in
`bench/phase-2-build.json`; Phase 1's binary has its own retained build record.
Rebuild and rerun compatibility gates on another stack. C/PHLASH environments
are rebuildable from their supplied scripts and are not distributed here.
Local Git history is excluded from the zip; the source, derivations, tests and
measurements are bundled together as a single reviewed milestone.

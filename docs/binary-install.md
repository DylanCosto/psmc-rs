# Installing a Linux binary

Download the archive for your architecture and its `.sha256` file from the
[GitHub releases page](https://github.com/DylanCosto/psmc-rs/releases).
Availability follows published assets; an unreleased source build is not a
published binary. `x86_64` means Intel/AMD 64-bit, `aarch64` means ARM64 Linux.

```sh
sha256sum -c psmc-rs-VERSION-TARGET.tar.gz.sha256
tar -xzf psmc-rs-VERSION-TARGET.tar.gz
cd psmc-rs-VERSION-TARGET
./psmc-rs --version
```

Replace VERSION and TARGET with the downloaded filename. Inside the extracted
folder, `sha256sum -c SHA256SUMS` checks every packaged file. No root privileges
are needed. To install for your user, copy `psmc-rs` to a directory on your PATH,
for example `~/.local/bin` (create it first if needed).

These are GNU/Linux executables, dynamically linked to system libraries. The
archive's BUILD.json records the minimum GLIBC symbol version, required shared
library names, source commit, Rust version, precision and binary checksum. Install
your distribution's zlib runtime if `libz.so.1` is missing. A GLIBC version error
means the archive needs a newer system; build from source on that machine instead.
Do not replace system libc to make a binary run. No GPU or Rust installation is
needed to run a supported prebuilt executable. CPU SIMD is selected at runtime.

## Check your installation with synthetic data

```sh
./psmc-rs --record-workers 1 --memory-mib 256 --seed 42 \
  -p '4+5*3+4' -N 2 -I 0 -o example.psmc examples/synthetic.psmcfa
```

This short run checks installation; it is not a scientifically calibrated fit.
The synthetic fixture is generated test data, not a person's genome. Ordinary CPU
runs use equivalent mode. Add `--mode strict` for the legacy arithmetic contract;
exact C reproduction is restricted to the tested toolchain/build. Version and mode
are recorded in the output. Release notes distinguish smoke tests, full platform
qualification and scientific validation.

For inspection, splitting, bootstrap resume and plotting, follow the
[five-minute tutorial](tutorial.md).

## Build from source

Install the pinned Rust toolchain and your system C linker/zlib, then run:

```sh
cargo build --release --locked --offline
./target/release/psmc-rs --version
```

Maintainers build archives with `python3 scripts/package_release.py --out-dir
work/release-assets`. The script requires clean Git, builds a generic native GNU
Linux executable, includes licenses and provenance, extracts its own archive and
runs both modes before emitting the external checksum and verification report.

# Final v0.8.0 release asset check

Written before final asset execution. Packaging must use a clean recorded source
commit and the pinned Rust 1.90.0 toolchain. Both native Linux architectures must
pass the hosted regression job, strict C goldens and extracted-archive fits/exports.
All archive checksums and every bundled file checksum are independently verified.
Only the explicit packaging allowlist and synthetic input may enter assets.

After downloading the final x86-64 asset, replay **bootstrap replicate 0** from the
broader frozen campaign in both modes. Use its unchanged blocks, seed20261011,
pattern4+25*2+4+6, N30/t15/r5/I0 and legacy one-bootstrap draw order. Request four
record workers and a2048MiB admission budget. Check the full draw trace and every
PSMC output byte against the corresponding frozen replicate; no mode comparison
or performance interpretation is substituted for this same-mode identity check.

Run the two fits sequentially through the existing bounded stage wrapper, with
14GiB RAM/25GiB disk preflight,12GiB hard address space and512MiB per-file ceiling,
nice10,4GiB RAM/25GiB disk runtime floors and2GiB check-directory cap. Preserve
commands, binary/input/output/trace hashes, statistics, timings and resource samples.
These are packaging/continuity checks, not a new controlled speed benchmark.
The broad campaign files, original runner and its frozen binaries remain untouched.

Review all Git history and final archives for unexpected private data/credentials.
Retain upstream licenses and citation, disclose earlier failed scientific screens,
and keep the stable-model prototype outside production. Verify uploaded release
assets by downloading them and running a synthetic fit/export from the downloaded
x86-64 archive. Native ARM fits remain verified on the hosted ARM runner; do not
claim local x86 emulation as ARM hardware qualification. Publish only after these
checks and the broader qualification report are reviewed.

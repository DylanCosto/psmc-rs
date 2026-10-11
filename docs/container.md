# Local container installation

A container recipe is included; this release does not publish a separate registry
image. Build locally from an extracted, checksum-verified Linux release archive
whose architecture matches your Docker host. Use a clean directory containing the
archive contents, not a directory containing genomic inputs.

```sh
# Run from the extracted psmc-rs-0.8.0-TARGET directory.
sha256sum -c SHA256SUMS
docker build -f containers/Dockerfile -t psmc-rs:0.8.0 .
docker run --rm --network none psmc-rs:0.8.0 --version
```

The recipe pins a Debian base-image digest and installs its zlib runtime. Apt
package versions can change; record the resulting image ID for reproducibility.
Only the verified executable and attribution files are copied. Building downloads
public image/packages; fitting requires no network access. The recipe defaults
to an unprivileged user.

To fit local files, run with your own user ID so output files remain writable:

```sh
docker run --rm --network none --user "$(id -u):$(id -g)" \
  --mount "type=bind,src=$PWD,dst=/data" --workdir /data \
  psmc-rs:0.8.0 --memory-mib 4096 --record-workers 4 \
  -p '4+25*2+4+6' -N 30 -t 15 -r 5 -I 0 -o result.psmc input.psmcfa
```

Docker's own `--memory` limit is independent of the program's admission estimate;
leave headroom above the program budget. Do not assume putting a fit in a container
makes it scientifically equivalent across runtime libraries. The local x86-64
candidate container passed the strict synthetic C golden fit and equivalent smoke
fit with network disabled. ARM-container and whole-genome container qualification
are not claimed. Native Linux regression evidence is documented separately.

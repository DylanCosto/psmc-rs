# Historical evidence storage

Large ignored benchmark outputs and experiment directories have been moved to
an external local backup drive. No source or tracked report was removed.
`bench/evidence-archive.json` lists the original repository-relative directory,
archive name, SHA-256, byte counts and verified member count for each archive.
The local `outputs/psmc-rs-evidence-archive/README.md` records the mounted drive
location; it is outside Git. Its adjacent manifests contain per-file hashes.

Archives preserve repository-relative paths (`work/...` or `bench/...`). To
reproduce a historical runner, restore its dependencies into an empty staging
directory, check their manifests, then place the needed paths back in the
repository without replacing newer evidence. Old report links into raw work
require restoration; compact tracked reports remain directly readable.

```bash
mkdir -p /path/to/empty-staging
tar --zstd -xf /path/to/ARCHIVE.tar.zst -C /path/to/empty-staging
```

`bench/archive_evidence.py` refuses tracked content, checks available headroom,
streams archive verification, compares every regular file's SHA-256 and each
symlink target, and rechecks the originals before removing a source directory.
Archive manifests are written before deletion; interrupted operations retain an
explicit incomplete state. Run it only on inactive evidence directories.

The first attempted combined archive exceeded the main drive's free space.
It was stopped and its incomplete output removed, with all originals retained.
The completed operation used individual runs and then the external drive.
A rebuildable 1.3 GiB debug compilation cache was also removed. No scientific
evidence was discarded. About 19 GiB of main-drive space was reclaimed, leaving
about 24 GiB free; future builds will recreate some compilation cache.

Active qualification inputs/results, the pinned vanilla reference, build
dependencies and installed binaries remain local. The backup archive is not
part of a Git push, and nothing was uploaded to an external service.

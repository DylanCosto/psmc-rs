#!/usr/bin/env python3
"""Bundle Phase 2 without replacing historical archives or large snapshots."""
from pathlib import Path
import hashlib
import json
import os
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT.parent / 'psmc-rust-phase-2.zip'
EXCLUDED_DIRS = {'work', 'target', '.git', '__pycache__'}


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def main():
    candidates, snapshots, symlinks = [], [], []
    for directory, dirs, names in os.walk(ROOT):
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDED_DIRS and not (Path(directory)/d).is_symlink())
        for name in sorted(names):
            path = Path(directory)/name
            relative = path.relative_to(ROOT).as_posix()
            if path.is_symlink():
                symlinks.append(relative)
            elif name.endswith('.jsonl.gz'):
                snapshots.append(dict(path=relative,bytes=path.stat().st_size,sha256=digest(path)))
            elif not name.endswith('.pyc') and relative != 'CHECKSUMS.sha256':
                candidates.append(path)
    snapshot_path = ROOT/'bench/phase2-snapshot-manifest.json'
    snapshot = dict(scope='All compressed internal JSONL snapshots in packaged evidence directories; full streams remain in local project.',
                    files=snapshots,total_compressed_bytes=sum(s['bytes'] for s in snapshots),
                    reproduction={'phase2':'Build pinned C references, then python3 bench/phase2_validate.py --run; timestamped outputs are new paths with exact comparison before compression.',
                                  'phase1':'See bench/phase1-snapshot-manifest.json; use preserved Phase 1 source archive.',
                                  'other':'See owning report and retained command; ordinary uncompressed small JSONL traces are packaged.'})
    snapshot_path.write_text(json.dumps(snapshot,indent=2)+'\n')
    manifest_path = ROOT/'bench/phase2-package-manifest.json'
    manifest = dict(archive_name=DEST.name,archive_root='psmc-rs',scope='Phase 2 Rust source and executable, original Phase 1 executable, fixtures, derivations, reports and ordinary raw evidence.',
                    excluded_directory_names=sorted(EXCLUDED_DIRS),excluded_suffixes=['.pyc','.jsonl.gz'],excluded_test_symlinks=symlinks,
                    omitted_snapshot_manifest='bench/phase2-snapshot-manifest.json',omitted_snapshot_files=len(snapshots),omitted_snapshot_bytes=snapshot['total_compressed_bytes'],
                    checksums='CHECKSUMS.sha256 covers every packaged file except itself',runner='bench/package_phase2.py',
                    historical_archives='Phase 0 and Phase 1 zip files are neither read nor replaced by this runner.')
    manifest_path.write_text(json.dumps(manifest,indent=2)+'\n')
    files = sorted(set(candidates + [snapshot_path,manifest_path]))
    checksum_path = ROOT/'CHECKSUMS.sha256'
    checksum_path.write_text(''.join(f'{digest(path)}  {path.relative_to(ROOT).as_posix()}\n' for path in files))
    files.append(checksum_path)
    with zipfile.ZipFile(DEST,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for path in files:
            archive.write(path,'psmc-rs/'+path.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(DEST) as archive:
        assert archive.testzip() is None, 'Archive CRC check failed'
        for path in files:
            relative = path.relative_to(ROOT).as_posix()
            actual = hashlib.sha256(archive.read('psmc-rs/'+relative)).hexdigest()
            assert digest(path) == actual, f'Archive content hash mismatch: {relative}'
    archive_sha = digest(DEST)
    DEST.with_suffix('.zip.sha256').write_text(f'{archive_sha}  {DEST.name}\n')
    print(json.dumps(dict(archive=DEST.name,bytes=DEST.stat().st_size,files=len(files),sha256=archive_sha,
                          all_archive_members_hash_verified=True,omitted_snapshot_bytes=snapshot['total_compressed_bytes']),indent=2))

if __name__=='__main__':
    main()

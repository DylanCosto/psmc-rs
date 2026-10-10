#!/usr/bin/env python3
"""Bundle the full-core milestone while preserving historical archives."""
from pathlib import Path
import hashlib
import json
import os
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT.parent / 'psmc-rust-parallel.zip'
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
    snapshot_path = ROOT/'bench/parallel-snapshot-manifest.json'
    snapshot = dict(scope='All compressed internal JSONL snapshots in packaged evidence directories; full streams remain in local project.',
                    files=snapshots,total_compressed_bytes=sum(s['bytes'] for s in snapshots),
                    reproduction={'campaign':'Build pinned references, then taskset -c CPU nice -n 10 python3 bench/cpu_campaign_release_gates.py; exact commands and frozen hashes are in the campaign reports.',
                                  'phase3':'Build pinned C references and simd_bench, then taskset -c CPU nice -n 10 python3 bench/phase3_validate.py --run; comparisons consume complete streams before compression.',
                                  'phase2':'Use the preserved Phase 2 source archive and bench/phase2_validate.py.',
                                  'phase1':'See bench/phase1-snapshot-manifest.json; use preserved Phase 1 source archive.',
                                  'other':'See owning report and retained command; ordinary uncompressed small JSONL traces are packaged.'})
    snapshot_path.write_text(json.dumps(snapshot,indent=2)+'\n')
    manifest_path = ROOT/'bench/parallel-package-manifest.json'
    manifest = dict(archive_name=DEST.name,archive_root='psmc-rs',scope='Unchanged production 0.3.1, full-core measurements and validation, rejected scheduler source/binary evidence, prior release executables, fixtures and historical ordinary raw evidence.',
                    excluded_directory_names=sorted(EXCLUDED_DIRS),excluded_suffixes=['.pyc','.jsonl.gz'],excluded_test_symlinks=symlinks,
                    omitted_snapshot_manifest='bench/parallel-snapshot-manifest.json',omitted_snapshot_files=len(snapshots),omitted_snapshot_bytes=snapshot['total_compressed_bytes'],
                    checksums='CHECKSUMS.sha256 covers every packaged file except itself',runner='bench/package_parallel.py',
                    historical_archives='All earlier zip files, including the CPU campaign, are neither read nor replaced by this runner.')
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

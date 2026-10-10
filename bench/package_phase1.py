#!/usr/bin/env python3
"""Create the compact local Phase 1 package, checksums and explicit exclusions."""
from pathlib import Path
import hashlib
import json
import os
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT.parent / 'psmc-rust-phase-1.zip'
EXCLUDED_DIRS = {'work', 'target', '.git', '__pycache__'}


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def main():
    snapshots=json.loads((ROOT/'bench/phase1-snapshot-manifest.json').read_text())
    omitted={entry['path'] for entry in snapshots['files']}
    symlinks=[]
    files=[]
    for directory, dirs, names in os.walk(ROOT):
        dirs[:]=sorted(d for d in dirs if d not in EXCLUDED_DIRS and not (Path(directory)/d).is_symlink())
        for name in sorted(names):
            path=Path(directory)/name
            relative=path.relative_to(ROOT).as_posix()
            if path.is_symlink():
                symlinks.append(relative)
            elif relative not in omitted and not name.endswith('.pyc') and relative!='CHECKSUMS.sha256':
                files.append(path)
    manifest_path=ROOT/'bench/phase1-package-manifest.json'
    manifest={
        'archive_name':DEST.name,
        'archive_root':'psmc-rs',
        'scope':'Rust source/binary, fixtures, reports and ordinary raw evidence; complete snapshots remain local',
        'excluded_directory_names':sorted(EXCLUDED_DIRS),
        'excluded_suffixes':['.pyc'],
        'excluded_test_symlinks':symlinks,
        'omitted_final_snapshot_manifest':'bench/phase1-snapshot-manifest.json',
        'omitted_final_snapshot_files':snapshots['files'],
        'omitted_final_snapshot_bytes':snapshots['total_compressed_bytes'],
        'checksums':'CHECKSUMS.sha256 covers every packaged file except itself',
        'runner':'bench/package_phase1.py',
    }
    manifest_path.write_text(json.dumps(manifest,indent=2)+'\n')
    if manifest_path not in files:
        files.append(manifest_path)
    files.sort()
    checksum_path=ROOT/'CHECKSUMS.sha256'
    checksum_path.write_text(''.join(f'{digest(path)}  {path.relative_to(ROOT).as_posix()}\n' for path in files))
    files.append(checksum_path)
    with zipfile.ZipFile(DEST,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for path in files:
            archive.write(path,'psmc-rs/'+path.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(DEST) as archive:
        assert archive.testzip() is None, 'Archive CRC check failed'
        for path in files:
            relative=path.relative_to(ROOT).as_posix()
            expected=digest(path)
            actual=hashlib.sha256(archive.read('psmc-rs/'+relative)).hexdigest()
            assert expected==actual, f'Archive content hash mismatch: {relative}'
    archive_sha=digest(DEST)
    DEST.with_suffix('.zip.sha256').write_text(f'{archive_sha}  {DEST.name}\n')
    print(json.dumps({'archive':DEST.name,'bytes':DEST.stat().st_size,'files':len(files),
                      'sha256':archive_sha,'all_archive_members_hash_verified':True,
                      'omitted_final_snapshot_bytes':snapshots['total_compressed_bytes']},indent=2))

if __name__=='__main__':
    main()

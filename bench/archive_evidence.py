#!/usr/bin/env python3
"""Archive ignored evidence only, verify every byte, then remove its source.

No tracked file is eligible. Archives preserve repository-relative paths.
Restoration: tar --zstd -xf ARCHIVE -C REPOSITORY (into an empty destination).
Run only while the selected evidence directories are inactive.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]


def digest(stream):
    h = hashlib.sha256()
    for block in iter(lambda: stream.read(1024 * 1024), b''):
        h.update(block)
    return h.hexdigest()


def inventory(path):
    result = {}
    for base, dirs, files in os.walk(path, followlinks=False):
        for name in sorted(dirs + files):
            p = Path(base) / name
            key = str(p.relative_to(ROOT))
            if p.is_symlink():
                result[key] = {'type': 'link', 'target': os.readlink(p)}
            elif p.is_file():
                with p.open('rb') as f:
                    result[key] = {'type': 'file', 'bytes': p.stat().st_size, 'sha256': digest(f)}
            elif not p.is_dir():
                raise ValueError(f'unsupported special file: {p}')
    return result


def archive(relative, destination):
    source = ROOT / relative
    if source.is_symlink() or not source.is_dir() or '..' in relative.parts or relative.is_absolute():
        raise ValueError(f'expected ordinary relative directory: {relative}')
    if subprocess.check_output(['git', 'ls-files', '--', str(relative)], cwd=ROOT):
        raise ValueError(f'tracked content: {relative}')
    subprocess.run(['git', 'check-ignore', '-q', str(relative) + '/'], cwd=ROOT, check=True)
    name = str(relative).replace('/', '__')
    target = destination / (name + '.tar.zst')
    manifest = destination / (name + '.json')
    if target.exists() or manifest.exists():
        raise ValueError(f'archive already exists: {target}')
    before = inventory(source)
    needed = sum(x.get('bytes', 0) for x in before.values())
    if shutil.disk_usage(destination).free < needed * 1.02 + 512 * 1024**2:
        raise ValueError('insufficient headroom; select smaller source directories')
    pending = target.with_suffix('.partial')
    if pending.exists():
        raise ValueError(f'incomplete archive already exists: {pending}')
    subprocess.run(['tar', '--use-compress-program=zstd -T2 -3', '--hard-dereference',
                    '-cf', str(pending), '-C', str(ROOT), str(relative)], check=True)
    seen = {}
    proc = subprocess.Popen(['zstd', '-dc', str(pending)], stdout=subprocess.PIPE)
    try:
        with tarfile.open(fileobj=proc.stdout, mode='r|') as tf:
            for member in tf:
                if member.isdir():
                    continue
                if member.issym():
                    seen[member.name] = {'type': 'link', 'target': member.linkname}
                elif member.isfile():
                    with tf.extractfile(member) as stream:
                        seen[member.name] = {'type': 'file', 'bytes': member.size, 'sha256': digest(stream)}
                else:
                    raise ValueError(f'unsupported archive member {member.name}')
        # Drain any tar padding so the decompressor can exit normally.
        while proc.stdout.read(1024 * 1024):
            pass
        if proc.wait() != 0:
            raise ValueError('decompression failed')
    finally:
        proc.stdout.close()
        if proc.poll() is None:
            proc.terminate()
            proc.wait()
    if seen != before or inventory(source) != before:
        raise ValueError('archive mismatch or source changed; source retained')
    pending.rename(target)
    with target.open('rb') as stream:
        archive_sha = digest(stream)
    record = {'source': str(relative), 'archive': target.name, 'sha256': archive_sha,
              'original_bytes': sum(x.get('bytes', 0) for x in before.values()),
              'archive_bytes': target.stat().st_size, 'verified_files': len(before),
              'members': before, 'source_removed': False}
    manifest.write_text(json.dumps(record, indent=2) + '\n')
    shutil.rmtree(source)
    record['source_removed'] = True
    manifest.write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps({k: v for k, v in record.items() if k != 'members'}), flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--destination', required=True, type=Path)
    p.add_argument('--apply', action='store_true')
    p.add_argument('directories', nargs='+', type=Path)
    args = p.parse_args()
    dest = args.destination.resolve()
    if args.apply:
        dest.mkdir(parents=True, exist_ok=True)
    for relative in args.directories:
        if dest == ROOT / relative or (ROOT / relative) in dest.parents:
            raise ValueError('archive destination must be outside source')
        if args.apply:
            archive(relative, dest)
        else:
            print(relative)


if __name__ == '__main__':
    main()

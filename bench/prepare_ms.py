#!/usr/bin/env python3
"""Fetch and build the pinned author-distributed ms source for qualification."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
from urllib.request import urlopen

SOURCE_PAGE = 'https://home.uchicago.edu/rhudson1/source/mksamples.html'
URL = 'https://uchicago.app.box.com/index.php?rm=box_download_shared_file&shared_name=l3e5uf13tikfjm7e1il1eujitlsjdx13&file_id=f_352115244835'
EXPECTED = '0edf46b9d35b3e677e00e4ea98c57c118c1ac7e3c3bfe748e038978b4a908205'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='new local directory')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    archive = args.output / 'ms.tar.gz'
    with urlopen(URL, timeout=60) as response:
        payload = response.read(2 * 1024 * 1024)
    actual = hashlib.sha256(payload).hexdigest()
    if actual != EXPECTED:
        raise ValueError(f'source hash mismatch: {actual}; no build attempted')
    archive.write_bytes(payload)
    with tarfile.open(archive) as tf:
        tf.extractall(args.output, filter='data')
    command = ['gcc', '-O2', '-o', 'ms', 'ms.c', 'rand1.c', 'streec.c', '-lm']
    subprocess.run(command, cwd=args.output / 'msdir', check=True)
    manifest = {'source_page': SOURCE_PAGE, 'download_url': URL, 'source_sha256': actual,
                'command': command, 'compiler': subprocess.check_output(['gcc', '--version'], text=True),
                'binary_sha256': hashlib.sha256((args.output/'msdir/ms').read_bytes()).hexdigest()}
    (args.output/'build.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(args.output/'msdir/ms')


if __name__ == '__main__':
    main()

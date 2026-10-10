#!/usr/bin/env python3
"""Check a freshly built pinned C executable against the committed golden files.

Cargo's golden integration test then checks default/CPU/scalar/dense Rust against
these same files. Never regenerate golden files to accommodate a mismatch.
"""
import argparse
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
# Keep these options aligned with crates/psmc-cli/tests/golden.rs.
CASES = [
    ('workload-k22', 'workload.psmcfa', ['-p','4+5*3+4','-N','10','-t','15','-r','4']),
    ('profile-k64', 'profile.psmcfa', ['-p','4+25*2+4+6','-N','3','-t','15','-r','5']),
    ('repeated-k6', 'repeated.psmcfa', ['-p','2+2+2','-N','5','-t','5','-r','4']),
    ('workload-k3-decode', 'workload.psmcfa', ['-p','1+2','-N','4','-t','15','-r','4','-d']),
]

def numerical_bytes(data):
    lines = data.splitlines(keepends=True)
    versions = [line for line in lines if line.startswith(b'MM\tVersion:')]
    assert len(versions) == 1, 'expected exactly one version line'
    return b''.join(line for line in lines if not line.startswith(b'MM\tVersion:'))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference',required=True)
    options=parser.parse_args()
    binary=Path(options.reference).resolve()
    with tempfile.TemporaryDirectory(prefix='psmc-ci-') as temporary:
        for name,fixture,args in CASES:
            output=Path(temporary)/f'{name}.psmc'
            subprocess.run([str(binary),*args,'-o',str(output),str(ROOT/'tests/fixtures'/fixture)],check=True,timeout=180)
            expected=(ROOT/'tests/fixtures/golden'/f'{name}.psmc').read_bytes()
            assert numerical_bytes(output.read_bytes())==numerical_bytes(expected), f'{name}: live C differs from pinned golden output'
            print(f'{name}: live C matches golden output',flush=True)

if __name__=='__main__':main()

#!/usr/bin/env python3
"""Build, package and smoke-test a native Linux GNU executable from clean Git.
No raw work/ data, external source files, or shared libraries enter the archive.
"""
import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]

def run(args, **kwargs):
    return subprocess.check_output(args, cwd=ROOT, text=True, **kwargs).strip()

def digest(data):
    return hashlib.sha256(data).hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir', required=True)
    args = parser.parse_args()
    if run(['git', 'status', '--porcelain']):
        raise SystemExit('Release packaging requires a clean tracked/untracked source tree.')
    if platform.system() != 'Linux':
        raise SystemExit('Only native Linux GNU packaging is currently supported.')
    target = {'x86_64': 'x86_64-unknown-linux-gnu',
              'aarch64': 'aarch64-unknown-linux-gnu'}.get(platform.machine())
    if target is None:
        raise SystemExit('Unsupported native CPU architecture.')
    out = Path(args.out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    versions = re.findall(r'^version = "([^"]+)"$', (ROOT/'Cargo.toml').read_text(), re.M)
    assert len(versions) == 1
    version = versions[0]
    source = run(['git', 'rev-parse', 'HEAD'])
    epoch = int(run(['git', 'show', '-s', '--format=%ct', 'HEAD']))
    name = f'psmc-rs-{version}-{target}'
    archive = out/(name+'.tar.gz')
    if archive.exists():
        raise SystemExit(f'Refusing to overwrite {archive}')
    build_dir = ROOT/'work'/'release-build'/target
    env = os.environ.copy()
    # A generic ISA with runtime SIMD selection, not the build host's native ISA.
    env.update(CARGO_TARGET_DIR=str(build_dir), RUSTFLAGS='', CARGO_ENCODED_RUSTFLAGS='',
               CARGO_BUILD_JOBS='2')
    command = ['cargo', '+1.90.0', 'build', '--release', '--locked', '--offline', '--target', target]
    subprocess.run(command, cwd=ROOT, env=env, check=True)
    binary = build_dir/target/'release'/'psmc-rs'
    assert run([str(binary), '--version']) == f'psmc-rs {version}'
    symbols = run(['readelf', '--version-info', str(binary)])
    glibc = sorted(set(re.findall(r'GLIBC_([0-9]+(?:\.[0-9]+)+)', symbols)),
                   key=lambda s: tuple(map(int, s.split('.'))))
    # Record library SONAMEs only; build-machine absolute paths are not useful.
    dynamic = run(['readelf', '-d', str(binary)])
    libraries = re.findall(r'\(NEEDED\).*?\[(.*?)\]', dynamic)
    provenance = dict(version=version, source_commit=source, target=target,
                      rustc=run(['rustc', '+1.90.0', '-Vv']), build_command=command,
                      generic_cpu=True, runtime_simd=True, cuda=False,
                      required_glibc=glibc[-1] if glibc else None,
                      shared_libraries=libraries, binary_sha256=digest(binary.read_bytes()),
                      precision='f64', strict_scope='Pinned-build comparisons; not universal cross-libm bit equality')
    files = {'psmc-rs': binary.read_bytes()}
    for path in ['LICENSE', 'NOTICE.md', 'CITATION.cff', 'README.md',
                 'docs/binary-install.md', 'reference/LICENSE.psmc.txt',
                 'reference/LICENSE.phlash.txt']:
        files[path] = (ROOT/path).read_bytes()
    files['examples/synthetic.psmcfa'] = (ROOT/'tests/fixtures/workload.psmcfa').read_bytes()
    files['BUILD.json'] = (json.dumps(provenance, indent=2)+'\n').encode()
    files['SHA256SUMS'] = ''.join(f'{digest(data)}  {path}\n' for path,data in sorted(files.items())).encode()
    with archive.open('xb') as raw, gzip.GzipFile(fileobj=raw, mode='wb', filename='', mtime=epoch) as zipped:
        with tarfile.open(fileobj=zipped, mode='w') as tar:
            for path, data in sorted(files.items()):
                info = tarfile.TarInfo(name+'/'+path)
                info.size = len(data); info.mtime = epoch
                info.mode = 0o755 if path == 'psmc-rs' else 0o644
                tar.addfile(info, io.BytesIO(data))
    with tempfile.TemporaryDirectory(prefix='psmc-package-test-') as tmp:
        installed = Path(tmp)/name
        with tarfile.open(archive) as tar:
            assert set(tar.getnames()) == {name+'/'+p for p in files}
            for member in tar.getmembers():
                assert member.isfile()
                relative = member.name[len(name)+1:]
                assert relative in files
                dest = installed/relative
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(tar.extractfile(member).read())
                dest.chmod(member.mode)
        for path,data in files.items():
            assert digest((installed/path).read_bytes()) == digest(data)
        fits = {}
        for mode in ['strict', 'equivalent']:
            dest = installed/(mode+'.psmc')
            subprocess.run([str(installed/'psmc-rs'), '--mode', mode, '--record-workers', '1',
                            '--memory-mib', '256', '-p', '4+5*3+4', '-N', '2', '-I', '0',
                            '--seed', '42', '-o', str(dest), str(installed/'examples/synthetic.psmcfa')],
                           cwd=tmp, check=True, capture_output=True, text=True)
            result = dest.read_text()
            assert 'RD\t2\n' in result and f'({mode} f64;' in result
            for line in result.splitlines():
                if line.startswith(('LL\t','TR\t','RS\t','PA\t')):
                    assert not re.search(r'(?i)\b(?:nan|inf)\b',line),line
            fits[mode] = digest(dest.read_bytes())
    checksum = digest(archive.read_bytes())
    (out/(archive.name+'.sha256')).write_text(f'{checksum}  {archive.name}\n')
    report = dict(archive=archive.name, archive_sha256=checksum, build=provenance,
                  extracted_file_checksums_verified=True, extracted_fit_sha256=fits,
                  smoke_status='passed', host_platform=platform.platform())
    (out/(name+'.verification.json')).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__ == '__main__':
    main()

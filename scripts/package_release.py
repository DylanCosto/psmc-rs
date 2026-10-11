#!/usr/bin/env python3
"""Build, package and smoke-test a native Linux GNU executable from clean Git.
No raw work/ data, external source files, or shared libraries enter the archive.
"""
import argparse
import csv
import math
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import posixpath
import re
import shutil
import subprocess
import tarfile
import tempfile
from urllib.parse import quote, unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]

def run(args, **kwargs):
    return subprocess.check_output(args, cwd=ROOT, text=True, **kwargs).strip()

def digest(data):
    return hashlib.sha256(data).hexdigest()

def archive_document(path, data, included, source):
    """Keep bundled links local; pin unbundled evidence links to this commit."""
    if not path.endswith('.md'):
        return data
    def replace(match):
        target = match.group(1)
        link = urlsplit(target)
        if link.scheme or link.netloc or not link.path:
            return match.group(0)
        resolved = posixpath.normpath(posixpath.join(posixpath.dirname(path), unquote(link.path)))
        if resolved.startswith('../') or resolved.startswith('/'):
            raise ValueError(f'Link escapes repository: {path}: {target}')
        if not (ROOT/resolved).exists():
            raise ValueError(f'Missing documentation target: {path}: {target}')
        if resolved in included:
            return match.group(0)
        url = f'https://github.com/DylanCosto/psmc-rs/blob/{source}/{quote(resolved)}'
        if link.query:
            url += '?' + link.query
        if link.fragment:
            url += '#' + link.fragment
        return '](' + url + ')'
    # Repository Markdown uses inline links without titles or spaces in targets.
    return re.sub(r'\]\(([^\s)]+)\)', replace, data.decode()).encode()

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
    remap_flags = [f'--remap-path-prefix={Path.home()}=/build-home',
                   f'--remap-path-prefix={ROOT}=psmc-rs']
    env.update(CARGO_TARGET_DIR=str(build_dir), RUSTFLAGS='', CARGO_ENCODED_RUSTFLAGS='\x1f'.join(remap_flags),
               CARGO_BUILD_JOBS='2')
    command = ['cargo', '+1.90.0', 'build', '--release', '--locked', '--offline', '--target', target]
    subprocess.run(command, cwd=ROOT, env=env, check=True)
    binary = build_dir/target/'release'/'psmc-rs'
    version_banner = run([str(binary), '--version'])
    assert version_banner.split(';', 1)[0] == f'psmc-rs {version}'
    symbols = run(['readelf', '--version-info', str(binary)])
    glibc = sorted(set(re.findall(r'GLIBC_([0-9]+(?:\.[0-9]+)+)', symbols)),
                   key=lambda s: tuple(map(int, s.split('.'))))
    # Record library SONAMEs only; build-machine absolute paths are not useful.
    dynamic = run(['readelf', '-d', str(binary)])
    libraries = re.findall(r'\(NEEDED\).*?\[(.*?)\]', dynamic)
    with tempfile.TemporaryDirectory(prefix='psmc-strip-') as temp:
        stripped = Path(temp)/'psmc-rs'
        shutil.copyfile(binary, stripped)
        subprocess.run(['strip', '--strip-debug', str(stripped)], check=True)
        binary_bytes = stripped.read_bytes()
    assert str(ROOT).encode() not in binary_bytes
    assert str(Path.home()).encode() not in binary_bytes
    provenance = dict(version=version, version_banner=version_banner, source_commit=source, target=target,
                      rustc=run(['rustc', '+1.90.0', '-Vv']), build_command=command,
                      generic_cpu=True, runtime_simd=True, cuda=False,
                      required_glibc=glibc[-1] if glibc else None,
                      shared_libraries=libraries, binary_sha256=digest(binary_bytes), debug_symbols=False,
                      source_paths_remapped=True, precision='f64', strict_scope='Pinned-build comparisons; not universal cross-libm bit equality')
    files = {'psmc-rs': binary_bytes}
    included = ['LICENSE', 'NOTICE.md', 'CITATION.cff', 'README.md',
                 'CONTRIBUTING.md', 'SECURITY.md',
                 'MATH_AND_COMPATIBILITY.md', 'VALIDATION_AND_BENCHMARKS.md',
                 'docs/binary-install.md', 'docs/tutorial.md', 'docs/bootstrap-resume.md',
                 'docs/usage.md', 'docs/modes-and-guarantees.md', 'docs/validation-overview.md',
                 'docs/methods-note.md', 'docs/external-pilot.md', 'docs/container.md',
                 'docs/adoption-qualification-report.md', 'docs/stable-model-report.md',
                 'docs/release-0.7.0.md', 'docs/release-0.8.0.md',
                 'docs/assets/hg001-benchmark.png', 'docs/assets/hg001-benchmark.svg',
                 'docs/assets/hg001-benchmark-data.json', 'containers/Dockerfile',
                 'scripts/plot_curve.py', 'reference/LICENSE.psmc.txt',
                 'reference/LICENSE.phlash.txt']
    runtime_notices = sorted((ROOT/'reference/rust-1.90.0').iterdir())
    inventory = json.loads((ROOT/'reference/rust-1.90.0/inventory.json').read_text())
    assert inventory['rust_version'] == '1.90.0'
    for path, metadata in inventory['files'].items():
        assert digest((ROOT/'reference/rust-1.90.0'/path).read_bytes()) == metadata['sha256']
    included.extend(str(path.relative_to(ROOT)) for path in runtime_notices)
    for path in included:
        files[path] = archive_document(path, (ROOT/path).read_bytes(), included, source)
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
                if line.startswith(('LK\t','TR\t','RS\t','PA\t')):
                    assert not re.search(r'(?i)\b(?:nan|inf)\b',line),line
            fits[mode] = digest(dest.read_bytes())
            exported = installed/(mode+'.csv')
            subprocess.run([str(installed/'psmc-rs'), 'export', '--mutation-rate', '1.25e-8',
                            '--generation-years', '25', '--bin-bp', '100', '--output', str(exported),
                            str(dest)], cwd=tmp, check=True, capture_output=True, text=True)
            rows = list(csv.DictReader(io.StringIO(exported.read_text())))
            assert rows and all(row['mode'] == mode and row['source_sha256'] == fits[mode] for row in rows)
            assert all(math.isfinite(float(row['reported_lk'])) for row in rows)
    checksum = digest(archive.read_bytes())
    (out/(archive.name+'.sha256')).write_text(f'{checksum}  {archive.name}\n')
    report = dict(archive=archive.name, archive_sha256=checksum, build=provenance,
                  extracted_file_checksums_verified=True, extracted_fit_sha256=fits,
                  extracted_export_provenance_verified=True, unbundled_links_pinned_to_source=True,
                  smoke_status='passed', host_platform=platform.platform())
    (out/(name+'.verification.json')).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__ == '__main__':
    main()

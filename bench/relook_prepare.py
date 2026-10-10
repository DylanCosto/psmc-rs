"""Reproduce the frozen v0.4.2 candidate sources without editing production."""
import io,json,os,subprocess,tarfile
from pathlib import Path
from common import ROOT,save,sha256
os.chdir(ROOT)
scratch=Path('work/relook/reproduce');scratch.mkdir()
archive=subprocess.check_output(['git','archive','30efe0b','Cargo.toml','Cargo.lock','rust-toolchain.toml','crates'])
with tarfile.open(fileobj=io.BytesIO(archive)) as tar:tar.extractall(scratch,filter='data')
variant=json.load(open('bench/relook-counts.json'))['variants']['uniformwide']
source=Path('work/relook/counts/uniformwide/crates/psmc-cpu/src/simd.rs')
assert sha256(source)==variant['source']['crates/psmc-cpu/src/simd.rs']
s=source.read_text().replace('mod relook_run_tests {','mod homogeneous_tile_tests {')
s=s.replace('let mut end = (begin + 16).min(observations.len());','let end = (begin + 16).min(observations.len());')
a=s.index('    pub(super) unsafe fn counts_emissions64(');b=s.index('        unsafe {',a)
s=s[:a]+s[a:b].replace('// SAFETY: validated K64 shapes; k advances by 2 and l by 16,\n        // so both source rows and all four-lane destination loads stay in bounds.','// SAFETY: validated K64 shapes. Uniform tiles use one source row,\n        // mixed tiles use two; both use 16 destinations and in-bounds AVX groups.\n        // Hoisted coefficients retain both multiplies and ascending additions.')+s[b:]
(scratch/'crates/psmc-cpu/src/simd.rs').write_text(s)
for name in ['Cargo.toml','Cargo.lock','crates/psmc-cli/src/main.rs']:
    p=scratch/name;p.write_text(p.read_text().replace('0.4.1','0.4.2'))
subprocess.run(['cargo','fmt','--all'],cwd=scratch,check=True)
build=json.load(open('bench/relook-build.json'))
for group in ['source_sha256','configuration_sha256']:
    for path,digest in build[group].items():assert sha256(scratch/path)==digest,path
save('bench/relook-reproduction.json',dict(status='passed',runner_sha256=sha256(__file__),
    base='30efe0b',prototype_source_sha256=sha256(source),directory=str(scratch),
    exact_final_source_hashes=build['source_sha256'],exact_configuration_hashes=build['configuration_sha256']))
print('Reproduced all frozen candidate source/configuration hashes.',flush=True)

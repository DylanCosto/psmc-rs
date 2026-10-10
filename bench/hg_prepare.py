#!/usr/bin/env python3
"""Pin the public upstream human PSMC fixture and exact bootstrap samples."""
import collections
import json
import os
from pathlib import Path
import subprocess
import urllib.request
from common import ROOT, draw_bootstrap, read_fasta, save, sha256, write_fasta

COMMIT = 'b5f0a200a99ecd86191780f0c8166d3e2ee0d776'
BASE = 'https://raw.githubusercontent.com/kevinkorfmann/smckit/' + COMMIT + '/'
FILES = {
    'NA12878_chr22.psmcfa': ('src/smckit/data/examples/psmc/NA12878_chr22.psmcfa', '0fe05d6fc19a94a3129803dc214660e0a72f2335ce5940b35fc3c9eab3698ea5'),
    'LICENSE': ('LICENSE', 'e9db8652d8026b7b74eb4477f8d87907b5d44d3ea300a68f742717e7327caa87'),
}

def main():
    os.chdir(ROOT)
    dest = Path('work/hg-input'); dest.mkdir(exist_ok=True)
    sources = []
    for name, (path, expected) in FILES.items():
        output = dest / name
        if not output.exists():
            with urllib.request.urlopen(BASE + path, timeout=60) as response:
                output.write_bytes(response.read())
        assert sha256(output) == expected, name
        sources.append(dict(url=BASE + path, path=str(output), sha256=expected, bytes=output.stat().st_size))
    original = dest / 'NA12878_chr22.psmcfa'
    records = read_fasta(original)
    assert len(records) == 1 and len(records[0][1]) == 508185
    assert set(records[0][1]) == set('TKN')
    split_command = ['work/vanilla/utils/splitfa', str(original), '50000']
    blocks_path = dest / 'blocks-50000.psmcfa'
    blocks_path.write_bytes(subprocess.run(split_command, capture_output=True, check=True).stdout)
    blocks = read_fasta(blocks_path)
    assert ''.join(s for _, s in blocks) == records[0][1]
    assert len(blocks) == 10
    reps = []
    for i in range(30):
        seed = 20261012 + i
        indices, draws = draw_bootstrap(blocks, seed)
        output = dest / f'bootstrap-{i:02d}.psmcfa'
        write_fasta(output, [blocks[j] for j in indices])
        reps.append(dict(index=i, seed=seed, indices=indices, draws=draws, path=str(output), sha256=sha256(output)))
    save('bench/hg-input.json', dict(status='passed', sources=sources, upstream_commit=COMMIT,
        upstream_description='Public smckit quickstart labels this a real NA12878 chromosome 22 PSMC example.',
        upstream_documentation='https://smckit.readthedocs.io/en/latest/get-started/quickstart-psmc.html',
        provenance_limit='Raw read accession, variant caller, filters and assembly for this particular bundled fixture are not independently established. The separate upstream prospective GRCh38 acquisition manifest is NOT provenance for this fixture.',
        scope='Full supplied chromosome fixture, not a whole genome; all encoded missing bins retained. No new VCF conversion or imputation. Local downloaded data are not committed.',
        license='Upstream repository MIT license retained locally; no redistribution of human input in this milestone.',
        input=str(original), input_sha256=sha256(original), bins=len(records[0][1]), symbols=dict(collections.Counter(records[0][1])),
        split_command=split_command, split_binary_sha256=sha256(split_command[0]), blocks=str(blocks_path), blocks_sha256=sha256(blocks_path),
        split_rationale='Explicit 50,000-bin bootstrap blocks (about 5 Mb at the standard 100-bp encoding). Default 500,000-bin splitfa would leave this fixture as one block, giving no meaningful resampling. This choice is fixed before outcomes; complete blocks and the remainder are retained.',
        blocks_summary=[dict(name=n,bins=len(s),symbols=dict(collections.Counter(s))) for n,s in blocks],
        seed=20261012, replicates=reps, runner_sha256=sha256(__file__)))
    print('Prepared all 508185 bins in 10 bootstrap blocks; 30 fixed samples.')

if __name__ == '__main__': main()

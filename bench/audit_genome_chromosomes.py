#!/usr/bin/env python3
"""Independently check completed chromosome encodings while a panel is running."""
import argparse
from decimal import Decimal
import gzip
import hashlib
import json
from pathlib import Path

import known_truth_genome as g


def verify_payload(raw, fasta, length, chromosome, command):
    lines = raw.splitlines()
    assert lines[0].split() == command, 'ms header differs from actual command'
    assert list(map(int, lines[1].split())) == list(map(int, command[-3:])), 'ms seed echo differs'
    pieces = raw.split('\n//\n')
    assert len(pieces) == 2, 'a chromosome must be one continuous replicate'
    data = [line.strip() for line in pieces[1].splitlines() if line.strip()]
    assert data[0].startswith('segsites: ')
    sites = int(data[0].split(':')[1])
    expected_heterozygous = set()
    if sites:
        assert len(data) == 4 and data[1].startswith('positions: ')
        positions = [Decimal(x) for x in data[1].split()[1:]]
        left, right = data[2:]
        assert len(positions) == len(left) == len(right) == sites
        assert positions == sorted(positions) and set(left+right) <= {'0','1'}
        for position, a, b in zip(positions, left, right):
            assert position.is_finite() and 0 <= position <= 1
            if a != b:
                expected_heterozygous.add(min(length//100-1, int(position*length/100)))
    else:
        assert len(data) == 1
    output = fasta.splitlines()
    assert output[0] == f'>chr-{chromosome+1}'
    assert all(not line.startswith('>') for line in output[1:])
    sequence = ''.join(output[1:])
    assert len(sequence) == length//100 and set(sequence) <= {'T','K'}
    assert {i for i,c in enumerate(sequence) if c == 'K'} == expected_heterozygous
    return {'bases':length,'bins':len(sequence),'segsites':sites,
            'heterozygous_bins':len(expected_heterozygous)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--panel',type=Path,required=True)
    args=parser.parse_args();root=args.panel.resolve()
    frozen=json.loads((root/'frozen.json').read_text())
    for name,digest in frozen['source_hashes'].items():assert g.sha(g.ROOT/name)==digest
    assert g.sha(root/'binaries/ms')==frozen['binary_hashes']['ms']
    checks=[]
    for manifest in sorted(root.glob('*/chr-*.converted.json')):
        name,index=manifest.parent.name.rsplit('-',1)
        k=int(manifest.name.split('.')[0].split('-')[1]);length=g.LENGTHS[k]
        sim=json.loads(manifest.read_text());base=manifest.parent/f'chr-{k:02}'
        assert sim['length']==length and sim['seeds']==g.seeds(name,int(index),k)
        command=sim['run']['command']
        assert command[0]==str(root/'binaries/ms') and command[1:3]==['2','1']
        n0=g.HISTORIES[name][0][1]
        assert float(command[command.index('-t')+1])==4*n0*g.p.MU*length
        r=command.index('-r')
        assert float(command[r+1])==4*n0*5e-9*length and int(command[r+2])==length
        assert command[-5:]==['12','-seeds',*map(str,sim['seeds'])]
        compressed=Path(str(base)+'.out.gz');fasta=Path(str(base)+'.psmcfa')
        assert g.sha(compressed)==sim['compression']['gzip_sha256']
        assert g.sha(fasta)==sim['fasta_sha256']
        with gzip.open(compressed,'rt') as f:raw=f.read()
        assert hashlib.sha256(raw.encode()).hexdigest()==sim['compression']['original_sha256']==sim['run']['output_sha256']
        check=verify_payload(raw,fasta.read_text(),length,k,command)
        checks.append({'case':manifest.parent.name,'chromosome':k,**check})
    report={'scope':'Only completed chromosomes; not a panel or fit qualification pass.',
            'checked_chromosomes':len(checks),'planned_chromosomes':720,
            'checked_bases':sum(c['bases'] for c in checks),'checks':checks}
    g.save(root/'chromosome-audit-progress.json',report)
    print(json.dumps({k:v for k,v in report.items() if k!='checks'},indent=2))


if __name__=='__main__':main()

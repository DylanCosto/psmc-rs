#!/usr/bin/env python3
"""Whole-autosome GIAB encoding using the already tested VCF+BED contract."""
import argparse
import collections
import gc
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

import cpu_next_hg002 as encoder
from known_truth_genome import sha, save
from common import ROOT

def read_fasta(path):
    result=[];name=None;chunks=[]
    with Path(path).open() as f:
        for line in f:
            if line.startswith('>'):
                if name is not None:result.append((name,''.join(chunks)))
                name=line[1:].split()[0];chunks=[]
            else:chunks.append(line.strip())
    if name is not None:result.append((name,''.join(chunks)))
    return result


CHROMS=[f'chr{i}' for i in range(1,23)]
PINNED={'benchmark.vcf.gz':'93bc4c2c696eaf13515ab058caecc064bfed704f85bac7482330ca91bc730daa',
        'callable.bed':'dc3485e60447a3e863c34dfc063c3710ea5ed5efae50855c5197ba62538263b9',
        'README_v4.2.1.txt':'70e7d8cd54119c40e1be946574ce1b91db835af594809466bcf7d3727eaa9699'}


def convert_chromosome(root, chrom, length, bed, records, converter):
    states,variants=encoder.encode(length,bed,records)
    destination=root/'chromosomes';destination.mkdir(exist_ok=True)
    compressed=destination/f'{chrom}.states.fa.gz';output=destination/f'{chrom}.psmcfa'
    digest=hashlib.sha256()
    with output.open('wb') as out, gzip.open(compressed,'wb',compresslevel=6) as zipped:
        process=subprocess.Popen([str(converter),'-'],stdin=subprocess.PIPE,stdout=out)
        try:
            header=f'>{chrom}\n'.encode();process.stdin.write(header);zipped.write(header);digest.update(header)
            for start in range(0,len(states),1_000_000):
                chunk=states[start:start+1_000_000]+b'\n'
                process.stdin.write(chunk);zipped.write(chunk);digest.update(chunk)
            process.stdin.close()
            assert process.wait()==0
        finally:
            if process.poll() is None:process.kill();process.wait()
    actual=read_fasta(output)
    assert len(actual)==1 and actual[0][0]==chrom, 'upstream converter dropped/changed record'
    expected=encoder.bins(states)
    assert actual[0][1]==expected and len(expected)==(length+99)//100
    verified=hashlib.sha256()
    with gzip.open(compressed,'rb') as f:
        for chunk in iter(lambda:f.read(1024**2),b''):verified.update(chunk)
    assert verified.hexdigest()==digest.hexdigest()
    result={'chromosome':chrom,'bases':length,'callable_bed_bases':sum(b-a for a,b in bed),
            'base_states':{chr(c):states.count(c) for c in b'NAM'},'variants':variants,
            'bins':len(expected),'symbols':dict(collections.Counter(expected)),
            'independent_binning_exact':True,'psmcfa_sha256':sha(output),
            'states_sha256':digest.hexdigest(),'states_gzip_sha256':sha(compressed)}
    save(destination/f'{chrom}.json',result)
    print(chrom,length,len(expected),flush=True)
    return result


def prepare(root):
    os.chdir(ROOT)
    source=root/'sources';converter=root/'binaries/fq2psmcfa'
    for name,digest in PINNED.items():assert sha(source/name)==digest
    encoder.FQ=converter;encoder.RAW=root/'prep-tests';encoder.RAW.mkdir(exist_ok=True)
    tests=encoder.test()
    regions={chrom:[] for chrom in CHROMS}
    with (source/'callable.bed').open() as f:
        for line in f:
            chrom,start,end=line.split()[:3]
            assert chrom in regions
            start,end=int(start),int(end)
            assert 0<=start<end
            if regions[chrom]:assert start>=regions[chrom][-1][1]
            regions[chrom].append((start,end))
    lengths={};results=[];current=None;records=[];seen=set();sample=None
    def finish():
        nonlocal records
        if current is not None:
            assert current not in seen
            results.append(convert_chromosome(root,current,lengths[current],regions[current],records,converter))
            seen.add(current);records=[];gc.collect()
    with gzip.open(source/'benchmark.vcf.gz','rt') as f:
        for line in f:
            if line.startswith('##contig='):
                match=re.search(r'ID=([^,>]+).*?length=(\d+)',line)
                if match and match[1] in CHROMS:lengths[match[1]]=int(match[2])
            if line.startswith('#CHROM'):
                fields=line.rstrip().split('\t');assert len(fields)==10 and fields[-1]=='HG001'
                sample=fields[-1];assert set(lengths)==set(CHROMS)
                assert lengths['chr1']==248956422 and lengths['chr22']==50818468
            if line.startswith('#'):continue
            fields=line.rstrip().split('\t');assert len(fields)==10
            chrom,pos,_,ref,alts,qual,filt,info,fmt,value=fields
            assert chrom in CHROMS and sample=='HG001'
            if chrom!=current:
                finish();current=chrom
            keys=fmt.split(':');values=value.split(':')
            gt=values[keys.index('GT')] if 'GT' in keys and keys.index('GT')<len(values) else '.'
            records.append((int(pos)-1,ref,alts.split(','),filt,gt))
    finish()  # Reaching EOF also checks the complete VCF gzip CRC.
    assert seen==set(CHROMS)
    results.sort(key=lambda r:CHROMS.index(r['chromosome']))
    output=root/'HG001_GRCh38_autosomes.psmcfa'
    with output.open('wb') as dst:
        for chrom in CHROMS:dst.write((root/'chromosomes'/f'{chrom}.psmcfa').read_bytes())
    combined=read_fasta(output)
    assert [n for n,_ in combined]==CHROMS
    assert [len(s) for _,s in combined]==[r['bins'] for r in results]
    report={'sample':sample,'assembly':'GRCh38','release':'NIST v4.2.1','source_hashes':PINNED,
            'converter_sha256':sha(converter),'converter_tests':tests,'chromosomes':results,
            'bases':sum(r['bases'] for r in results),'bins':sum(r['bins'] for r in results),
            'symbols':dict(sum((collections.Counter(r['symbols']) for r in results),collections.Counter())),
            'input_sha256':sha(output),'all_bins_independently_exact':True,
            'scope':'All 22 autosomes; complete chromosome coordinates and missing regions. Sex chromosomes/mitochondria excluded.'}
    save(root/'input.json',report)
    print(json.dumps({k:v for k,v in report.items() if k not in ['chromosomes','converter_tests']},indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',required=True,type=Path)
    args=parser.parse_args();prepare(args.root.resolve())

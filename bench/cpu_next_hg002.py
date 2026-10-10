#!/usr/bin/env python3
"""Prepare bounded public HG002 chr1 fixture under explicit GIAB VCF+BED contract."""
import collections,gzip,json,os,re,subprocess
from pathlib import Path
from common import ROOT,save,sha256,read_fasta
RAW=Path('work/cpu-next/hg002')
BASE='https://ftp-trace.ncbi.nlm.nih.gov/ReferenceSamples/giab/release/AshkenazimTrio/HG002_NA24385_son/NISTv4.2.1/'
FQ=Path('work/vanilla/utils/fq2psmcfa')

def encode(length,bed,records):
    states=bytearray(b'N')*length;last=0
    for start,end in bed:
        assert 0<=last<=start<end<=length
        states[start:end]=b'A'*(end-start);last=end
    hets=[];stats=collections.Counter();last=-1
    for pos,ref,alts,filt,gt in records:
        assert 0<=pos<length and pos>=last and pos+len(ref)<=length
        last=pos;stats['records']+=1
        alleles=[ref,*alts];parts=re.split(r'[/|]',gt)
        valid=len(parts)==2 and all(p.isdigit() and int(p)<len(alleles) for p in parts)
        snv=all(len(a)==1 and a in 'ACGT' for a in alleles)
        if valid and snv and filt=='PASS':
            if parts[0]!=parts[1]:hets.append(pos);stats['heterozygous_snv_records']+=1
        else:
            start=max(0,pos-5);end=min(length,pos+len(ref)+5)
            states[start:end]=b'N'*(end-start);stats['masked_variant_records']+=1
    # Apply after all exclusions, never restore an excluded/noncallable base.
    for pos in hets:
        if states[pos]==ord('A'):states[pos]=ord('M');stats['called_het_bases']+=1
    return states,dict(stats)

def bins(states):
    return ''.join('N' if block.count(ord('N'))>90 else 'K' if ord('M') in block else 'T' for i in range(0,len(states),100) for block in [states[i:i+100]])

def convert(name,states,directory):
    pseudo=directory/(name+'.states.fa');out=directory/(name+'.psmcfa')
    with pseudo.open('wb') as f:
        f.write(('>'+name+'\n').encode())
        for start in range(0,len(states),1000000):f.write(states[start:start+1000000]+b'\n')
    command=[str(FQ),str(pseudo)]
    with out.open('wb') as f:subprocess.run(command,stdout=f,check=True)
    actual=read_fasta(out);assert len(actual)==1
    expected=bins(states);assert actual[0][1]==expected,(type(actual[0]),str(actual[0])[:80])
    return dict(path=str(out),sha256=sha256(out),command=command,pseudo_state_input_sha256=sha256(pseudo),bins=len(expected),counts=dict(collections.Counter(expected)),independent_binning_exact=True)

def test():
    # 10k callable prefix passes upstream record filters; suffix exercises exact
    # BED coordinates, thresholds, final partial block and overlapping masks.
    d=RAW/'tests';d.mkdir()
    states=bytearray(b'A'*10000+b'N'*90+b'A'*10+b'N'*91+b'M'+b'A'*8+b'N'*22)
    record=convert('thresholds',states,d);assert bins(states)[-3:]=='TNT'
    states,stats=encode(11023,[(0,10000),(10099,10201),(10300,11023)],[(0,'A',['C'],'PASS','0/1'),(99,'A',['C'],'PASS','1|1'),(10000,'A',['C'],'PASS','0/1'),(10099,'A',['C','G'],'PASS','1/2'),(10100,'A',['C'],'PASS','0/1'),(10101,'AC',['A'],'PASS','0/1'),(10301,'A',['C'],'PASS','./.'),(10400,'A',['C'],'LowQual','0/1'),(11022,'A',['G'],'PASS','0|1')])
    assert states[0]==ord('M') and states[99]==ord('A') and states[10000]==ord('N')
    assert states[10099]==ord('N') and states[10100]==ord('N') and states[11022]==ord('M')
    assert states[10301]==ord('N') and states[10400]==ord('N')
    second=convert('coordinates',states,d)
    rejected=0
    for bed in [[(-1,10)],[(0,101)],[(10,20),(19,30)]]:
        try:encode(100,bed,[])
        except AssertionError:rejected+=1
    assert rejected==3
    return dict(status='passed',fixtures=[record,second],malformed_bed_rejected=rejected)

def main():
    os.chdir(ROOT);tests=test();vcf=RAW/'benchmark.vcf.gz';bedfile=RAW/'callable.bed'
    regions=[]
    for line in bedfile.read_text().splitlines():
        chrom,start,end=line.split()[:3]
        if chrom=='chr1':regions.append((int(start),int(end)))
    records=[];length=None;sample=None
    # Read entire gzip stream to validate CRC; collect only chr1.
    with gzip.open(vcf,'rt') as f:
        for line in f:
            if line.startswith('##contig=<ID=chr1,'):length=int(re.search(r'length=(\d+)',line).group(1))
            if line.startswith('#CHROM'):
                h=line.rstrip().split('\t');assert len(h)==10;sample=h[-1]
            if line.startswith('#'):continue
            fields=line.rstrip().split('\t');assert len(fields)==10
            if fields[0]!='chr1':continue
            chrom,pos,ident,ref,alt,qual,filt,info,fmt,value=fields
            keys=fmt.split(':');values=value.split(':');gt=values[keys.index('GT')] if 'GT' in keys and keys.index('GT')<len(values) else '.'
            records.append((int(pos)-1,ref,alt.split(','),filt,gt))
    assert length==248956422 and sample=='HG002'
    states,stats=encode(length,regions,records)
    result=convert('HG002_GRCh38_chr1',states,RAW)
    report=dict(status='passed',runner_sha256=sha256(__file__),source_urls={'vcf':BASE+'GRCh38/HG002_GRCh38_1_22_v4.2.1_benchmark.vcf.gz','bed':BASE+'GRCh38/HG002_GRCh38_1_22_v4.2.1_benchmark_noinconsistent.bed','readme':BASE+'README_v4.2.1.txt'},source_files={str(p):sha256(p) for p in [vcf,bedfile,Path('work/cpu-next/README_v4.2.1.txt')]},upstream_checksum='not supplied for these VCF/BED files; local SHA256 and gzip CRC verified',reference_converter=dict(path=str(FQ),sha256=sha256(FQ),source_commit='82fa2ada83ee463fe1251b562ae3d60e82d7ad6a'),sample=sample,chromosome='chr1',assembly='GRCh38',bases=length,callable_bed_bases=sum(b-a for a,b in regions),encoded_base_counts={chr(k):v for k,v in collections.Counter(states).items()},variant_counts=stats,output=result,tests=tests,contract=['GIAB v4.2.1 README explicitly includes confident homozygous reference calls; BED and VCF used together.','Only inside high-confidence BED: A represents a homozygous state, M a called diploid PASS heterozygous simple SNV, N missing. Letters are state placeholders, not actual reference bases.','Non-simple-SNV, non-PASS or missing/invalid diploid genotype records mask the reference span plus five bases each side. All exclusions precede heterozygous assignments.','All chromosome coordinates and missing regions retained in one HMM record; no artificial internal boundaries.','Pinned fq2psmcfa default 100-base bins: N if >90 missing, else K if a called heterozygote, else T. Last partial bin still uses denominator 100, including legacy all-missing-tail behavior.','Public GIAB HG002 data; local benchmark-only intermediate files, no raw genome redistribution.'],limitations=['Single chromosome of one individual, not whole-genome or user data.','Confidence/variant exclusions induce ascertainment; this is a compatibility/performance fixture, not a recommended demographic analysis pipeline.','VCF header fileDate is not release date; source is explicitly pinned to NIST v4.2.1.'])
    save('bench/cpu-next-hg002-input.json',report);print(json.dumps(result),flush=True)
if __name__=='__main__':main()

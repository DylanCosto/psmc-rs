#!/usr/bin/env python3
"""Wait for the existing HG001 run, audit its evidence, and write the comparison."""
import argparse
from collections import Counter
import gzip
import hashlib
import json
import math
from pathlib import Path
import subprocess
import time

import hg001_genome_prepare as prep
import hg001_genome_run as run


def near(a,b):assert math.isclose(a,b,rel_tol=1e-11,abs_tol=1e-13),(a,b)


def audit(root):
    r=json.loads((root/'report.json').read_text());f=json.loads((root/'frozen.json').read_text())
    assert r['metadata']==f
    for path,digest in f['source_hashes'].items():
        assert run.sha(run.p.ROOT/path)==digest
        original=subprocess.check_output(['git','show',f"{f['commit']}:{path}"],cwd=run.p.ROOT)
        assert hashlib.sha256(original).hexdigest()==digest
    assert f['diff_sha256']==hashlib.sha256(b'').hexdigest()
    assert int(subprocess.check_output(['git','show','-s','--format=%ct',f['commit']],cwd=run.p.ROOT))<=f['created']
    for name,digest in f['binary_hashes'].items():assert run.sha(root/'binaries'/name)==digest
    assert run.sha(run.p.ROOT/'bin/psmc-rs')==f['binary_hashes']['rust']
    for name,digest in prep.PINNED.items():assert run.sha(root/'sources'/name)==digest
    inp=json.loads((root/'input.json').read_text())
    assert run.metrics.relative(inp)==r['input']
    records=prep.read_fasta(root/'HG001_GRCh38_autosomes.psmcfa')
    assert [n for n,s in records]==prep.CHROMS
    assert run.sha(root/'HG001_GRCh38_autosomes.psmcfa')==inp['input_sha256']
    combined=hashlib.sha256();total=Counter()
    for (chrom,sequence),evidence in zip(records,inp['chromosomes']):
        assert chrom==evidence['chromosome'];d=root/'chromosomes'
        assert run.sha(d/f'{chrom}.psmcfa')==evidence['psmcfa_sha256']
        assert run.sha(d/f'{chrom}.states.fa.gz')==evidence['states_gzip_sha256']
        h=hashlib.sha256();chunks=[]
        with gzip.open(d/f'{chrom}.states.fa.gz','rb') as stream:
            header=stream.readline();h.update(header);assert header==f'>{chrom}\n'.encode()
            for line in stream:h.update(line);chunks.append(line.strip())
        states=b''.join(chunks);del chunks
        assert h.hexdigest()==evidence['states_sha256'] and len(states)==evidence['bases']
        # Independently classify state bins without calling the preparation rule.
        computed=[]
        for start in range(0,len(states),100):
            block=states[start:start+100]
            computed.append('N' if block.count(b'N')>90 else ('K' if b'M' in block else 'T'))
        assert ''.join(computed)==sequence
        assert len(sequence)==evidence['bins'] and dict(Counter(sequence))==evidence['symbols']
        assert {chr(c):states.count(c) for c in b'NAM'}==evidence['base_states']
        total.update(sequence);combined.update((d/f'{chrom}.psmcfa').read_bytes())
        del states,computed
    assert combined.hexdigest()==inp['input_sha256']
    assert sum(c['bases'] for c in inp['chromosomes'])==inp['bases']
    assert sum(map(lambda x:len(x[1]),records))==inp['bins'] and dict(total)==inp['symbols']
    texts={m:(root/f'{m}.out').read_text() for m in ['c','strict','equivalent']}
    exact=run.p.numerical(texts['c'])==run.p.numerical(texts['strict'])
    assert exact==r['strict_c_exact']
    params={m:run.p.curve(text)[1] for m,text in texts.items()}
    assert params==r['parameters']
    for mode in texts:
        assert run.sha(root/f'{mode}.out')==r['runs'][mode]['output_sha256']
        assert r['runs'][mode]['exit_code']==0 and r['runs'][mode]['ceiling_gib']==10
        cmd=[str(root/'binaries/c'),*run.p.FIT] if mode=='c' else [str(root/'binaries/rust'),
            '--mode',mode,'--record-workers','16' if mode=='strict' else '8',
            '--stats',str(root/f'{mode}.stats.json'),
            *(['--memory-mib','8192'] if mode=='strict' else []),*run.p.FIT]
        cmd.append(str(root/'HG001_GRCh38_autosomes.psmcfa'))
        assert run.metrics.relative(cmd)==r['runs'][mode]['command']
        assert run.timing(root/f'{mode}.time')==r['runs'][mode]['timing']
        ll=float([l.split()[1] for l in texts[mode].splitlines() if l.startswith('LK\t')][-1])
        assert math.isfinite(ll) and ll==r['legacy_ll'][mode]
    for mode in ['strict','equivalent']:
        assert json.loads((root/f'{mode}.stats.json').read_text())==r['stats'][mode]
    admission=r['stats']['strict']['memory_admission']
    assert admission['budget_bytes']==8192*1024**2
    assert 1<=admission['workers']<=16 and admission['estimated_bytes']<=admission['budget_bytes']
    for name,(a,b) in run.metrics.BANDS.items():
        times=[a*(b/a)**(i/128) for i in range(128)]
        curves={}
        for mode,v in params.items():
            curves[mode]=[math.log(v['n0']*v['lambdas'][max(i for i,x in enumerate(v['group_starts_generations']) if x<=t)]) for t in times]
            for x,y in zip(curves[mode],r['bands'][name]['log_curves'][mode]):near(x,y)
        diff=[abs(x-y) for x,y in zip(curves['strict'],curves['equivalent'])]
        near(math.sqrt(sum(x*x for x in diff)/128),r['bands'][name]['rms_log_difference'])
        near(max(diff),r['bands'][name]['max_log_difference'])
    difference=r['differences']
    for name in ['theta','rho']:near(abs(params['equivalent'][name]/params['strict'][name]-1),difference[name])
    near(abs(r['legacy_ll']['equivalent']-r['legacy_ll']['strict']),difference['legacy_ll_absolute'])
    near(difference['legacy_ll_absolute']/inp['bins'],difference['legacy_ll_per_bin'])
    screen=all(r['bands'][b]['rms_log_difference']<=.01 for b in ['primary_early','primary_late']) and all(difference[f]<=.001 for f in ['theta','rho']) and difference['legacy_ll_per_bin']<=1e-6
    assert screen==r['equivalent_screen_passed']
    diagnostic_required=not screen or any(b['rms_log_difference']>.01 for b in r['bands'].values())
    assert diagnostic_required==(r['diagnostic'] is not None)
    if diagnostic_required:
        raw=[json.loads(line) for line in (root/'ridge.out').read_text().splitlines()]
        assert raw==r['diagnostic'] and len(raw)==19 and raw[0]['kind']=='endpoints'
        for item in raw:assert all(math.isfinite(v) for v in item.values() if isinstance(v,(float,int)))
    samples=[json.loads(l) for l in (root/'resources.jsonl').read_text().splitlines()]
    resources={'samples':len(samples),'min_available_ram_gib':min(s['available_ram'] for s in samples)/run.GIB,
        'min_free_disk_gib':min(s['free_disk'] for s in samples)/run.GIB,
        'max_campaign_gib':max(s['campaign_bytes'] for s in samples)/run.GIB,
        'max_group_rss_gib':max(s['rss_bytes'] for s in samples)/run.GIB,
        'recorded_stop':(root/'stop.json').exists()}
    assert resources['min_available_ram_gib']>=4 and resources['min_free_disk_gib']>=25 and resources['max_campaign_gib']<=4
    assert not resources['recorded_stop']
    result={'audit_passed':True,'strict_c_exact':exact,'equivalent_screen_passed':screen,
        'whole_autosomes':22,'bases':inp['bases'],'bins':inp['bins'],
        'input_sha256':inp['input_sha256'],'report_sha256':run.sha(root/'report.json'),
        'protocol_sha256':f['source_hashes']['docs/hg001-genome-protocol.md'],
        'resources':resources,'source_commit':f['commit'],'conditional_diagnostic_run':diagnostic_required}
    run.save(root/'audit.json',result)
    return r,result


def write_report(r,a):
    root=run.p.ROOT;stats=r['stats'];inp=r['input'];delta=r['differences']
    rows=[]
    for m in ['c','strict','equivalent']:
        v=r['runs'][m];t=v['timing']
        workers='1' if m=='c' else str(stats[m]['memory_admission']['workers']) if m=='strict' else '8'
        rows.append(f"| {m} | {workers} | {v['seconds']:.2f} | {t['user_seconds']+t['system_seconds']:.2f} | {t['peak_rss_kib']/1024:.1f} |")
    bands=[]
    for name,b in r['bands'].items():bands.append(f"| {name} | {b['rms_log_difference']:.6g} | {b['max_log_difference']:.6g} |")
    fall=stats['equivalent']['structured_fallbacks'];updates=stats['equivalent']['model_updates']
    doc=f'''# Public HG001 whole-autosome comparison

The requested three-engine comparison is complete on all 22 autosomes of public
GIAB HG001 (NA12878), GRCh38 NIST v4.2.1. Strict/C exact comparison:
**{'PASS' if a['strict_c_exact'] else 'FAIL'}**. Equivalent's prospectively declared
exploratory agreement screen: **{'PASS' if a['equivalent_screen_passed'] else 'FAIL'}**.
This compares implementations on real data; it does not establish a true demographic
history or a universal scientific equivalence guarantee.

## Data and provenance

The [prospective protocol](hg001-genome-protocol.md) was committed before preparation
and fitting. Source commit `{a['source_commit']}`; protocol hash
`{a['protocol_sha256']}`. The frozen runner, binary, source and input hashes and
exact commands are in [full results](../bench/hg001-genome-results.json), with
[the verification audit](../bench/hg001-genome-audit.json).

Input: **{inp['bases']:,} reference bases**, **{inp['bins']:,} 100-base bins**,
22 complete chromosome records. Bin counts: `{inp['symbols']}`. Input SHA256:
`{inp['input_sha256']}`. The same file was supplied unchanged to all engines.
The upstream converter and independent rule matched every bin; the final audit
reconstructed bins again from retained compressed state sequences.

Official [GIAB source directory](https://ftp-trace.ncbi.nlm.nih.gov/ReferenceSamples/giab/release/NA12878_HG001/NISTv4.2.1/GRCh38/)
and [release README](https://ftp-trace.ncbi.nlm.nih.gov/ReferenceSamples/giab/release/NA12878_HG001/NISTv4.2.1/README_v4.2.1.txt).
The README explicitly includes confident homozygous reference calls and requires
VCF/BED together. Bases outside BED remain missing. Invalid/non-SNV variants are
masked with five flanking bases before assigning heterozygotes. Full chromosome
coordinates, masks and partial-bin semantics are retained. No artificial splits.
State letters are placeholders, not actual reference bases. Sex chromosomes and
mitochondria are excluded by this autosomal benchmark. Confidence ascertainment
makes this an implementation fixture, not a recommended demographic pipeline.
No raw reads/reference FASTA were downloaded and no raw genome is committed.

## Measured execution

Each fit used 64 states and 30 iterations: `-p 4+25*2+4+6 -N 30 -t 15 -r 5 -I 0`,
f64, original optimizer, alpha 0.1. Fits ran sequentially with low scheduling
priority; strict requested 16 workers within an 8192 MiB budget, equivalent eight.
Installed Rust SHA256: `{r['metadata']['binary_hashes']['rust']}`.
C source remains pinned to `82fa2ada83ee463fe1251b562ae3d60e82d7ad6a`.
The platform is x86-64 Linux/glibc on i5-12600K, Rust 1.90 and pinned GCC C build.

| Engine | Record workers | Wall seconds | CPU seconds | Peak RSS MiB |
|---|---:|---:|---:|---:|
{chr(10).join(rows)}

These are single observations on a shared machine with different worker counts,
not a repeated speed benchmark. The strict admission estimate was
{stats['strict']['memory_admission']['estimated_bytes']/run.GIB:.3f} GiB. No inference
arithmetic or production code was changed for this campaign.

## Numerical comparison

Strict equality excludes only `MM Version`; all rounds 0–30 and every remaining
output byte are compared. All final parameter vectors were positive and finite.
Equivalent uses the existing QU diagnostic contract, while strict/C retain QD.

| Band | RMS log Ne difference | Maximum log Ne difference |
|---|---:|---:|
{chr(10).join(bands)}

Theta relative difference: **{delta['theta']:.6g}**; rho: **{delta['rho']:.6g}**.
Legacy LK absolute difference: **{delta['legacy_ll_absolute']:.6g}**,
**{delta['legacy_ll_per_bin']:.6g} per encoded bin**. LK precedes the last M-step;
it is not silently presented as a fresh final-parameter likelihood.
Full-grid RMS/max log differences: {delta['full_grid_rms_log']:.6g} /
{delta['full_grid_max_log']:.6g}. Scaling uses the same mu=2.5e-8 and bin size for
both fits, with no fitted alignment. The recent/ancient diagnostic windows remain
visible. No compiler-envelope or bootstrap-spread claim is made from one genome.

Equivalent fallbacks: **{fall:,} / {updates:,} model updates**
({fall/updates:.6g}). Conditional fresh LL/common-Q/lambda0-slice diagnostic:
**{'run; full values retained in results' if a['conditional_diagnostic_run'] else 'not triggered by the predeclared screen'}**.
No failed screen was revised or excluded.

## Resource control and validation

Observed minimum available RAM: {a['resources']['min_available_ram_gib']:.2f} GiB;
minimum free disk: {a['resources']['min_free_disk_gib']:.2f} GiB;
maximum campaign footprint: {a['resources']['max_campaign_gib']:.3f} GiB.
Resource samples, peak memory and safeguards are retained in the audit. Hard
address-space limits supplement strict admission; neither changes the data.
Three new preparation/runner tests passed. The existing v0.6.3 numerical release
checks remain the preceding evidence; this campaign did not change their code.

Commands run:

```bash
python3 -m unittest discover -s bench -p 'test_hg001_genome.py'
python3 bench/hg001_genome_run.py --root work/hg001-genome
python3 bench/hg001_genome_finish.py --root work/hg001-genome --wait
```

The slow synthetic campaign was stopped at the user's request, with no completed
chromosomes or fits; its logs/partials are preserved and it is not marked passed.
The earlier 200 Mb known-truth evidence remains separate. This result does not
qualify real-workload splitting chosen by the user, whole-genome bootstrap
uncertainty, ARM/non-Linux/CUDA or hosted CI. Strict remains default and equivalent
opt-in. Raw and compressed input evidence remains in ignored `work/hg001-genome`.
'''
    (root/'docs/hg001-genome-report.md').write_text(doc)
    run.save(root/'bench/hg001-genome-results.json',r)
    run.save(root/'bench/hg001-genome-audit.json',a)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,required=True);parser.add_argument('--wait',action='store_true')
    args=parser.parse_args();root=args.root.resolve()
    while not (root/'report.json').exists():
        if not args.wait:raise RuntimeError('comparison report is not ready')
        pid=int((root/'run.lock').read_text());proc=Path('/proc')/str(pid)
        try:command=(proc/'cmdline').read_bytes()
        except OSError:raise RuntimeError('run stopped without final report; inspect preserved logs')
        assert b'hg001_genome_run.py' in command
        if (root/'stop.json').exists():raise RuntimeError('resource/interrupt stop recorded')
        time.sleep(10)
    # The report is written just before the monitor shuts down. Wait for the
    # verified owner to exit so the resource audit covers its entire lifetime.
    if args.wait:
        pid=int((root/'run.lock').read_text())
        while True:
            try:command=(Path('/proc')/str(pid)/'cmdline').read_bytes()
            except OSError:break
            if b'hg001_genome_run.py' not in command:break
            time.sleep(1)
    r,a=audit(root);write_report(r,a);print(json.dumps(a,indent=2),flush=True)


if __name__=='__main__':main()

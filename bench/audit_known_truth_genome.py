#!/usr/bin/env python3
"""Audit every genome-panel chromosome, fit, fixed gate and resource record."""
import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import shlex
import statistics
import subprocess

import known_truth_genome as g


def close(a,b):
    assert math.isclose(a,b,rel_tol=1e-10,abs_tol=1e-13),(a,b)


def rss_kib(path):
    for line in path.read_text().splitlines():
        if 'Maximum resident set size (kbytes):' in line:return int(line.split(':')[-1])
    raise AssertionError('missing peak RSS: '+str(path))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--panel',required=True,type=Path)
    args=parser.parse_args();root=args.panel.resolve()
    report=json.loads((root/'report.json').read_text())
    frozen=json.loads((root/'frozen.json').read_text())
    assert report['metadata']==frozen
    for name,digest in frozen['source_hashes'].items():
        assert g.sha(g.ROOT/name)==digest
        committed=subprocess.check_output(['git','show',f"{frozen['source_commit']}:{name}"],cwd=g.ROOT)
        assert hashlib.sha256(committed).hexdigest()==digest
    committed_at=int(subprocess.check_output(['git','show','-s','--format=%ct',frozen['source_commit']],cwd=g.ROOT))
    assert committed_at<=frozen['created']
    for name,digest in frozen['binary_hashes'].items():assert g.sha(root/'binaries'/name)==digest
    assert g.sha(g.ROOT/'bin/psmc-rs')==frozen['binary_hashes']['rust']
    assert frozen['source_diff_sha256']==hashlib.sha256(b'').hexdigest()
    assert frozen['lengths']==g.LENGTHS and frozen['jobs']==2
    cases=report['cases']
    assert {(c['history'],c['index']) for c in cases}=={(h,i) for h in g.HISTORIES for i in range(10)}
    assert len(cases)==30
    exact,diagnostics,stats_updates,fallbacks=0,0,0,0
    peak_rss={mode:0 for mode in ['c','strict','equivalent','ms','concurrent']}
    for case in cases:
        assert case['status']=='complete'
        name,index=case['history'],case['index'];folder=root/f'{name}-{index:02}'
        assert case['lengths']==g.LENGTHS and len(case['simulations'])==24
        assert g.sha(folder/'input.psmcfa')==case['input_sha256']
        assert sum(g.validate_input(folder/'input.psmcfa'))==30_000_000
        combined=hashlib.sha256()
        for k,(length,sim) in enumerate(zip(g.LENGTHS,case['simulations'])):
            base=folder/f'chr-{k:02}'
            assert sim['seeds']==g.seeds(name,index,k)
            assert sim['length']==length
            args=shlex.split(sim['history2ms_command']);n0=g.HISTORIES[name][0][1]
            assert args[:3]==['msHOT-lite','2','1']
            close(float(args[args.index('-t')+1]),4*n0*g.p.MU*length)
            pos=args.index('-r');close(float(args[pos+1]),4*n0*5e-9*length)
            assert int(args[pos+2])==length
            events=[list(map(float,args[i+1:i+4])) for i,a in enumerate(args) if a=='-en']
            assert events==[[t/(4*n0),1.,n/n0] for t,n in g.HISTORIES[name][1:]]
            command=sim['run']['command']
            # Report commands have the repository prefix removed for publication.
            assert command[1:]==[*[a for a in args[1:] if a!='-l'],'-p','12','-seeds',*map(str,sim['seeds'])]
            compressed=Path(str(base)+'.out.gz')
            assert g.sha(compressed)==sim['compression']['gzip_sha256']
            with gzip.open(compressed,'rt') as f:raw=f.read()
            assert hashlib.sha256(raw.encode()).hexdigest()==sim['compression']['original_sha256']==sim['run']['output_sha256']
            encoded=g.p.convert_ms(raw,length=length,bin_size=100,expected=1).replace('>ms-1\n',f'>chr-{k+1}\n',1).encode()
            fasta=Path(str(base)+'.psmcfa')
            assert hashlib.sha256(encoded).hexdigest()==g.sha(fasta)==sim['fasta_sha256']
            combined.update(encoded)
            peak_rss['ms']=max(peak_rss['ms'],rss_kib(Path(str(base)+'.time')))
        assert combined.hexdigest()==case['input_sha256'],'concatenation changed boundaries'
        texts={m:(folder/f'{m}.out').read_text() for m in ['c','strict','equivalent']}
        assert g.p.numerical(texts['c'])==g.p.numerical(texts['strict'])
        assert case['strict_c_exact'];exact+=1
        params={m:g.p.curve(text)[1] for m,text in texts.items()}
        assert params==case['parameters']
        for mode in texts:
            assert g.sha(folder/f'{mode}.out')==case['runs'][mode]['output_sha256']
            assert case['runs'][mode]['exit_code']==0
            peak_rss[mode]=max(peak_rss[mode],rss_kib(folder/f'{mode}.time'))
        for mode in ['strict','equivalent']:
            assert json.loads((folder/f'{mode}.stats.json').read_text())==case['stats'][mode]
        stats=case['stats']['equivalent'];stats_updates+=stats['model_updates'];fallbacks+=stats['structured_fallbacks']
        for band,(start,end) in g.metrics.BANDS.items():
            recorded=case['bands'][band]
            times=[start*(end/start)**(i/128) for i in range(128)]
            hist=g.HISTORIES[name]
            truth=[math.log(next(n for edge,n in reversed(hist) if edge<=t)) for t in times]
            curves={}
            for mode,v in params.items():
                curves[mode]=[math.log(v['n0']*v['lambdas'][max(i for i,edge in enumerate(v['group_starts_generations']) if edge<=t)]) for t in times]
                assert len(recorded['log_curves'][mode])==128
                for a,b in zip(curves[mode],recorded['log_curves'][mode]):close(a,b)
                close(math.sqrt(sum((a-b)**2 for a,b in zip(curves[mode],truth))/128),recorded['rmse'][mode])
            difference=[abs(a-b) for a,b in zip(curves['strict'],curves['equivalent'])]
            close(math.sqrt(sum(x*x for x in difference)/128),recorded['mode_curve_rmse'])
            close(max(difference),recorded['mode_curve_max'])
        trigger=any(b['mode_curve_rmse']>.01 for b in case['bands'].values())
        assert trigger==(case['ridge'] is not None)
        if trigger:
            assert case['ridge']==[json.loads(line) for line in (folder/'ridge.out').read_text().splitlines()]
            diagnostics+=1
    # Recompute each prospective decision separately from the runner booleans.
    gates=[]
    for history in g.HISTORIES:
        fits=[c for c in cases if c['history']==history]
        for band in ['primary_early','primary_late']:
            b=[c['bands'][band] for c in fits]
            strict=[v['rmse']['strict'] for v in b];equivalent=[v['rmse']['equivalent'] for v in b]
            delta=[e-s for e,s in zip(equivalent,strict)]
            upper=statistics.mean(delta)+1.833112933*statistics.stdev(delta)/math.sqrt(10)
            difference=math.sqrt(sum(v['mode_curve_rmse']**2 for v in b)/10)
            baseline=math.sqrt(sum(v*v for v in strict)/10)
            passed=upper<.05 and difference<=.1*baseline and statistics.mean(strict)<=.5 and statistics.mean(equivalent)<=.5
            expected=report['summary'][history]['bands'][band]
            close(upper,expected['upper_paired_error_difference'])
            close(difference,expected['pooled_mode_difference'])
            assert passed==(expected['relative_checks_passed'] and expected['absolute_checks_passed'])
            gates.append(passed)
        if history!='constant':
            for mode in ['strict','equivalent']:
                ratios=[g.metrics.event_ratio(c['parameters'][mode],history) for c in fits]
                for value,c in zip(ratios,fits):close(value,c['event_ratios'][mode])
                value=statistics.median(ratios)
                close(value,report['summary'][history]['event_median_ratios'][mode])
                gates.append(value<.75 if history=='bottleneck' else value>1.25)
    assert report['scientific_passed']==all(gates)
    cdir=root/'constant-00';cc=report['concurrent_check']
    assert (cdir/'strict-concurrent.out').read_bytes()==(cdir/'strict.out').read_bytes()
    assert cc['output_exact'] and cc['stats']['memory_admission']['workers']>=2
    assert json.loads((cdir/'strict-concurrent.stats.json').read_text())==cc['stats']
    peak_rss['concurrent']=rss_kib(cdir/'strict-concurrent.time')
    minimum_disk=minimum_ram=float('inf');maximum_panel=maximum_jobs=maximum_group_rss=0;samples=0
    with (root/'resources.jsonl').open() as f:
        for line in f:
            sample=json.loads(line);samples+=1
            minimum_disk=min(minimum_disk,sample['free_disk']);minimum_ram=min(minimum_ram,sample['available_ram'])
            maximum_panel=max(maximum_panel,sample['panel_bytes']);maximum_jobs=max(maximum_jobs,len(sample['jobs']))
            maximum_group_rss=max(maximum_group_rss,sum(sample['group_rss_bytes'].values()))
    assert samples>0 and maximum_jobs<=2
    interruptions=[str(p.relative_to(root)) for p in root.rglob('incomplete-*.json')]
    resource={'samples':samples,'min_free_disk':minimum_disk,'min_available_ram':minimum_ram,
              'max_panel_bytes':maximum_panel,'max_active_jobs':maximum_jobs,
              'max_aggregate_child_rss':maximum_group_rss,'peak_process_rss_kib':peak_rss,
              'interruptions':interruptions,'resource_stop_recorded':(root/'resource-stop.json').exists()}
    # Historical interruptions are retained even when a later exact resume completes.
    audit={'audit_passed':True,'scientific_passed':all(gates),'datasets':30,'primary_fits':90,
           'bases_per_dataset':3_000_000_000,'continuous_chromosomes_checked':720,
           'strict_c_exact':exact,'outlier_diagnostics':diagnostics,'model_updates':stats_updates,
           'fallbacks':fallbacks,'fallback_fraction':fallbacks/stats_updates,
           'resource':resource,'panel_sha256':g.sha(root/'report.json'),
           'scope':'Idealized continuous synthetic chromosomes; real workload, masks, ARM, CUDA and hosted CI not_run.'}
    g.save(root/'audit.json',audit);print(json.dumps(audit,indent=2))


if __name__=='__main__':main()

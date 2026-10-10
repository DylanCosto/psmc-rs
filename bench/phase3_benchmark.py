#!/usr/bin/env python3
"""Strictly sequential one-CPU timings; never run alongside builds/tests/profile."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import resource
import statistics
import subprocess
import time
from common import ROOT, save, sha256, timed_run
from phase1_differential import compare_output
from phase2_common import clean_env, utc_stamp, verify_binaries
from phase3_common import resource_policy

ARGS23=['-p','4+5*3+4','-N','30','-t','15','-r','4','-I','0']


def cpu_time():
    r=resource.getrusage(resource.RUSAGE_CHILDREN)
    return r.ru_utime+r.ru_stime


def summary(runs):
    measured=[r for r in runs if r['kind']=='measured']
    result={'repetitions':len(measured)}
    for field in ['wall_seconds','child_cpu_seconds','peak_rss_kib']:
        values=[r[field] for r in measured]
        result[field]={'median':statistics.median(values),'min':min(values),'max':max(values)}
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',action='store_true')
    options=parser.parse_args()
    os.chdir(ROOT)
    policy=resource_policy()
    if not options.run:
        print(json.dumps({'status':'not_run','policy':policy,'scope':'5 measured single fits/kernel pairs + warmups; 3 measured serial 30-fit batches + warmups; no parallel jobs'}));return
    validation=json.loads(Path('bench/phase-3-validation.json').read_text())
    assert validation['status']=='passed' and validation['complete_phase3a_selection']
    provenance=validation['provenance'];verify_binaries(provenance)
    binaries={k:v['path'] for k,v in provenance['binaries'].items()}
    raw=Path('bench/phase-3-benchmark')/utc_stamp();raw.mkdir(parents=True)
    report=dict(status='running',created_utc=dt.datetime.now(dt.timezone.utc).isoformat(),resource_policy=policy,provenance=provenance,validation_sha256=sha256(Path('bench/phase-3-validation.json')),runner_sha256=sha256(Path(__file__)),raw_directory=str(raw),single_cases=[],kernels=[],batches=[],limitations=['Shared CPU at reduced priority: wall time is contention-sensitive; child process CPU time is also retained.','One logical CPU, no concurrent inference jobs, no parallel throughput claim.','Kernel wall sections include prepared-layout construction; process CPU time includes the separate exactness check and startup.','The 30-fit batch includes 27 finite trajectories and three retained reference pathologies; mechanics-only timing.','Few synthetic repetitions do not establish production or ARM performance.'])
    save('bench/phase-3-benchmark.json',report)
    def timed(command,name):
        verify_binaries(provenance)
        start=cpu_time()
        r=timed_run(command,ROOT/raw/name,env=clean_env(),timeout=600)
        r['child_cpu_seconds']=cpu_time()-start
        assert r['exit_code']==0,(command,r)
        return r
    commands={'vanilla':[binaries['vanilla']],'phase2':[binaries['phase2'],'--backend','cpu'],
              'scalar':[binaries['candidate'],'--backend','cpu','--simd','off'],
              'simd':[binaries['candidate'],'--backend','cpu','--simd','auto']}
    profile=json.loads(Path('bench/profile.json').read_text())
    cases=[dict(id='k23-n30',input='tests/fixtures/workload.psmcfa',arguments=ARGS23),dict(id='k64-n5',input=profile['fixture']['file'],arguments=profile['arguments'])]
    for case in cases:
        entry={**case,'input_sha256':sha256(Path(case['input'])),'runs':[]};report['single_cases'].append(entry)
        expected=None;names=list(commands)
        for rep in range(6):
            kind='warmup' if rep==0 else 'measured'
            for name in names[rep%4:]+names[:rep%4]:
                assert sha256(Path(case['input']))==entry['input_sha256']
                r=timed(commands[name]+case['arguments']+[case['input']],f"{case['id']}-{kind}-{rep}-{name}")
                data=Path(r['output']).read_bytes()
                if expected is None:expected=data
                comparison=compare_output(expected,data)
                assert not r['nonfinite_records_beyond_initial_RI']
                entry['runs'].append(dict(implementation=name,kind=kind,repeat=rep,load_average=list(os.getloadavg()),comparison=comparison,**r))
                save('bench/phase-3-benchmark.json',report)
        entry['summary']={name:summary([r for r in entry['runs'] if r['implementation']==name]) for name in names}
        entry['ratios']={name:{field:entry['summary'][name][field]['median']/entry['summary']['simd'][field]['median'] for field in ['wall_seconds','child_cpu_seconds']} for name in names if name!='simd'}
        save('bench/phase-3-benchmark.json',report)
        print(json.dumps({'case':case['id'],'ratios':entry['ratios']}),flush=True)
    for n,bins,repeats in [(23,4400,20),(64,17600,5)]:
        entry={'states':n,'bins_per_first_record':bins,'records':3,'repeats_per_process':repeats,'runs':[]};report['kernels'].append(entry)
        expected_checksum=None
        for rep in range(6):
            for mode in (['off','avx'] if rep%2==0 else ['avx','off']):
                command=[binaries['kernel'],mode,str(n),str(bins),str(repeats),'3']
                before=cpu_time();start=time.perf_counter()
                run=subprocess.run(command,env=clean_env(),capture_output=True,text=True,check=True)
                wall=time.perf_counter()-start;cpu=cpu_time()-before
                values=json.loads(run.stdout)
                assert values['exact_check'] and values['simd_selected']==('avx' if mode=='avx' else 'scalar')
                if expected_checksum is None:expected_checksum=values['checksum']
                assert values['checksum']==expected_checksum
                entry['runs'].append(dict(kind='warmup' if rep==0 else 'measured',mode=mode,command=command,process_wall_seconds=wall,process_cpu_seconds=cpu,values=values))
                save('bench/phase-3-benchmark.json',report)
        entry['kernel_wall_medians']={mode:statistics.median(r['values']['seconds'] for r in entry['runs'] if r['mode']==mode and r['kind']=='measured') for mode in ['off','avx']}
        entry['scalar_over_avx_kernel_wall']=entry['kernel_wall_medians']['off']/entry['kernel_wall_medians']['avx']
        save('bench/phase-3-benchmark.json',report)
        print(json.dumps({'kernel_states':n,'wall_ratio':entry['scalar_over_avx_kernel_wall']}),flush=True)
    canon={i:(Path(validation['run_directory'])/'cpu-raw'/f'K23_N30_bootstrap_{i:02d}-oracle.psmc').read_bytes() for i in range(30)}
    fixture_hashes={str(p):sha256(p) for p in [Path('tests/fixtures/blocks.psmcfa'),*sorted(Path('tests/fixtures/bootstrap').glob('replicate-*.psmcfa'))]}
    entry={'workers':1,'scope':'Serial mechanics-only 30-fit batch including three reference pathologies','input_sha256':fixture_hashes,'runs':[]};report['batches'].append(entry)
    for rep in range(4):
        names=['vanilla','phase2','simd'];names=names[rep%3:]+names[:rep%3]
        for name in names:
            verify_binaries(provenance)
            assert all(sha256(Path(p))==h for p,h in fixture_hashes.items())
            label=f'batch-{rep}-{name}'
            if name=='vanilla':
                before=cpu_time();start=time.perf_counter();children=[]
                for i in range(30):
                    child=timed(commands[name]+ARGS23+[f'tests/fixtures/bootstrap/replicate-{i:02d}.psmcfa'],f'{label}-{i:02d}')
                    children.append(child)
                r={'wall_seconds':time.perf_counter()-start,'child_cpu_seconds':cpu_time()-before,'peak_rss_kib':max(c['peak_rss_kib'] for c in children),'children':children,'rss_scope':'maximum of individual sequential child process peaks, excludes parent Python'}
                for i,child in enumerate(children): compare_output(canon[i],Path(child['output']).read_bytes())
            else:
                directory=raw/(label+'-outputs')
                r=timed([commands[name][0],'bootstrap',*commands[name][1:],'--workers','1','--replicates','30','--seed','20261009','--memory-mib','2048','--output-dir',str(directory),*ARGS23,'tests/fixtures/blocks.psmcfa'],label)
                manifest=json.loads((directory/'manifest.json').read_text())
                assert manifest['workers']==manifest['requested_workers']==1 and manifest['failed_replicates']==0
                for i in range(30):compare_output(canon[i],(directory/f'replicate-{i:02d}.psmc').read_bytes())
                if name=='simd':
                    assert manifest['nonfinite_replicates']==3
                    for i in range(30):assert json.loads((directory/f'replicate-{i:02d}.stats.json').read_text())['simd_selected']=='avx'
                r.update(directory=str(directory),manifest_sha256=sha256(directory/'manifest.json'),rss_scope='one Rust scheduler process including its one numerical worker')
            entry['runs'].append(dict(implementation=name,kind='warmup' if rep==0 else 'measured',repeat=rep,all_30_outputs_exact=True,**r))
            save('bench/phase-3-benchmark.json',report)
        print(f'Serial batch repetition {rep} finished',flush=True)
    entry['summary']={name:summary([r for r in entry['runs'] if r['implementation']==name]) for name in ['vanilla','phase2','simd']}
    entry['ratios']={name:{field:entry['summary'][name][field]['median']/entry['summary']['simd'][field]['median'] for field in ['wall_seconds','child_cpu_seconds']} for name in ['vanilla','phase2']}
    verify_binaries(provenance)
    report['status']='passed_synthetic_timing_checks';report['completed_utc']=dt.datetime.now(dt.timezone.utc).isoformat()
    save('bench/phase-3-benchmark.json',report)
    print(json.dumps({'status':report['status'],'batch_ratios':entry['ratios']},indent=2))

if __name__=='__main__':main()

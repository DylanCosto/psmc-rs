#!/usr/bin/env python3
"""Verify follow-up evidence; never turn a descriptive numerical screen into a pass."""
import json,os,re,subprocess
from pathlib import Path
from common import ROOT,save,sha256

def main():
    os.chdir(ROOT)
    names=['analysis','screen','bounded-screen','bounded-validation','bounded-performance','strict-regression']
    reports={n:json.load(open(f'bench/equivalent-followup-{n}.json')) for n in names}
    for n in names[:-1]:assert reports[n]['status']=='completed',n
    assert not reports['screen']['screen_pass'] and reports['bounded-screen']['screen_pass']
    legacy=reports['strict-regression'];passes=0;obsolete=[];traces=0
    for backend,entry in legacy['backend_reports'].items():
        for c in json.load(open(entry['report']))['cases']:
            if c['status']=='passed':passes+=1
            else:
                assert backend in ['cpu','scalar'] and c['name']=='reject_equivalent_mode',c
                obsolete.append(dict(backend=backend,name=c['name']))
        assert entry['full_bootstrap_finite']==27 and entry['full_bootstrap_pathologies']==[16,26,28]
        traces+=len(entry['snapshots'])
    assert (passes,traces,len(obsolete))==(338,10,2)
    output_count=0
    for n in ['screen','bounded-screen','bounded-validation','bounded-performance']:
        for run in reports[n]['runs']+reports[n].get('strict_controls',[]):
            assert run['exit_code']==0 and not run['nonfinite_records_beyond_initial_RI']
            assert sha256(run['output'])==run['output_sha256']
            for out in run.get('outputs',[]):assert sha256(out['path'])==out['sha256'];output_count+=1
    counter_checks=[]
    for run in reports['bounded-validation']['runs']:
        if run.get('mode')!='equivalent' or 'outputs' not in run:continue
        removed=0
        for out in run['outputs']:
            path=Path(out['path']);new=json.load(open(path.with_suffix('.stats.json')))
            old=json.load(open(Path('work/equivalent/validation')/f"{run['dataset']}-equivalent-batch"/path.with_suffix('.stats.json').name))
            assert old['model_updates']-new['model_updates']==new['iterations']
            assert 0<=old['structured_fallbacks']-new['structured_fallbacks']<=new['iterations']
            for key in ['sequence_visits','sequence_evaluations','cache_hits']:assert new[key]==old[key]
            removed+=old['model_updates']-new['model_updates']
        counter_checks.append(dict(dataset=run['dataset'],removed_estep_refreshes=removed))
    perf=reports['bounded-performance'];validation=reports['bounded-validation']
    digest=sha256('target/release/psmc-rs')
    assert perf['binaries']['candidate']['sha256']==validation['binaries']['candidate']['sha256']==digest
    assert sha256('bin/psmc-rs-v0.5.0')==perf['binaries']['baseline']['sha256']
    assert sha256(legacy['provenance']['binaries']['candidate']['path'])==digest
    archives=['work/equivalent-followup/full-buffer-candidate/runner.py','work/equivalent-followup/bounded-screen-runner.py','bench/equivalent_followup.py']
    hashes={sha256(p) for p in archives}
    for n in ['screen','bounded-screen','bounded-validation','bounded-performance']:assert reports[n]['runner_sha256'] in hashes,n
    assert reports['screen']['binaries']['candidate']['sha256']==sha256('work/equivalent-followup/full-buffer-candidate/psmc-rs')
    tests={}
    for name,path,expected in [('full_release','work/equivalent-followup/bounded-final-release.log',[47,0,4]),('cpu_debug','work/equivalent-followup/bounded-message-debug.log',[24,0,0]),('cpu_message_release','work/equivalent-followup/bounded-message-release.log',[23,0,0])]:
        text=Path(path).read_text();assert 'FAILED' not in text
        results=re.findall(r'test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored;',text)
        actual=[sum(int(t[i]) for t in results) for i in range(3)];assert actual==expected,(name,actual)
        tests[name]=dict(passed=actual[0],failed=actual[1],ignored=actual[2],log_sha256=sha256(path))
    analysis=reports['analysis'];assert analysis['source_sha256']==sha256('bench/equivalent-analysis.json')
    assert analysis['ridge']['raw_sha256']==sha256('work/equivalent-followup/ridge.jsonl')
    assert analysis['ridge']['source_sha256']==sha256('crates/psmc-cpu/examples/equivalent_ridge.rs')
    for p,h in analysis['ridge']['inputs'].items():assert sha256(p)==h
    inputs={}
    for data in json.load(open('bench/equivalent-c-baseline.json'))['datasets'].values():
        for key in ['original','blocks']:
            assert sha256(data[key])==data[key+'_sha256'];inputs[data[key]]=data[key+'_sha256']
        for sample in data['samples']:
            assert sha256(sample['path'])==sample['sha256'];inputs[sample['path']]=sample['sha256']
    assert Path('bench/experiments/equivalent-full-buffer.patch').read_bytes()==Path('work/equivalent-followup/full-buffer-candidate/candidate.patch').read_bytes()
    result=dict(status='completed',base_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),decision='promote_bounded_lockstep_in_opt_in_equivalent' if perf['performance_gate'] else 'reject_bounded_lockstep_performance',strict_default=True,scientific_equivalence_qualified=False,interpretation='Historical fixed/per-fit numerical screens are not calibrated scientific tests. Conditional-lambda diagnostic supports weak identification. This engineering change must reproduce the prior structured outputs exactly.',strict_passed=passes,ordered_traces=traces,obsolete_availability_checks=obsolete,verified_bootstrap_outputs=output_count,tests=tests,counter_checks=counter_checks,hardware_not_run=['CUDA','ARM/NEON'],binary_sha256=digest,inputs=inputs,rejected_source_patch_sha256=sha256('bench/experiments/equivalent-full-buffer.patch'),sources={str(p):sha256(p) for p in [Path('Cargo.toml'),Path('Cargo.lock'),*Path('crates').rglob('*.rs'),*Path('crates').rglob('Cargo.toml')]},reports={f'bench/equivalent-followup-{n}.json':sha256(f'bench/equivalent-followup-{n}.json') for n in names},runners={p:sha256(p) for p in archives},environment=dict(cpu=next(x.split(':',1)[1].strip() for x in Path('/proc/cpuinfo').read_text().splitlines() if x.startswith('model name')),rustc=subprocess.check_output(['rustc','-vV'],text=True),libc=subprocess.check_output(['getconf','GNU_LIBC_VERSION'],text=True).strip()))
    save('bench/equivalent-followup-audit.json',result)
    print(json.dumps({k:result[k] for k in ['status','decision','strict_passed','ordered_traces','verified_bootstrap_outputs']},indent=2))
if __name__=='__main__':main()

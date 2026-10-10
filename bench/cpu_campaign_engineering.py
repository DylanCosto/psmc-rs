#!/usr/bin/env python3
"""Sequential isolated-build CPU engineering screen; never installs a candidate."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import resource
import shutil
import statistics
import subprocess
import time
from common import ROOT, save, sha256
from phase1_differential import compare_output
from phase2_common import clean_env, source_hashes, verify_binaries
from phase3_common import resource_policy


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--family',choices=['kernels','model','tails'],default='kernels')
    options=parser.parse_args()
    if options.family=='kernels':
        from cpu_campaign_kernel_variants import prepare
        labels=['unroll8','unroll16','tile64','tile256']
        candidate_source='bench/cpu_campaign_kernel_variants.py'
    elif options.family=='model':
        from cpu_campaign_model_variants import prepare
        labels=['grid','invariants']
        candidate_source='bench/cpu_campaign_model_variants.py'
    else:
        from cpu_campaign_tail_variants import prepare
        labels=['masked','masked-wide']
        candidate_source='bench/cpu_campaign_tail_variants.py'
    os.chdir(ROOT)
    policy=resource_policy()
    before=source_hashes()
    provenance=json.loads(Path('bench/phase-3-validation.json').read_text())['provenance']
    verify_binaries(provenance)
    stamp=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    raw=Path('bench/cpu-campaign-engineering')/(options.family+'-'+stamp)
    raw.mkdir(parents=True)
    report_path=Path('bench/cpu-campaign-'+options.family+'.json')
    env=clean_env()
    assert not any(env.get(k) for k in ['RUSTFLAGS','CARGO_ENCODED_RUSTFLAGS','CARGO_TARGET_DIR','RUSTC_WRAPPER','RUSTC_WORKSPACE_WRAPPER','CARGO_BUILD_TARGET'])
    assert not any(k.startswith('CARGO_PROFILE_') and v for k,v in env.items())
    env.update(CARGO_BUILD_JOBS='1',RUST_TEST_THREADS='1',CARGO_NET_OFFLINE='true')
    binaries={'phase3a':provenance['binaries']['candidate']}
    kernels={'phase3a':provenance['binaries']['kernel']}
    report=dict(status='running',family=options.family,resource_policy=policy,raw_directory=str(raw),
                provenance=provenance,source_sha256=before,binaries=binaries,kernel_binaries=kernels,
                tests=[],cases=[],kernels=[],runner_sha256=sha256(__file__),candidate_source_sha256=sha256(candidate_source))
    save(report_path,report)
    try:
        for label in labels:
            scratch=ROOT/'work'/f'cpu-engineering-{stamp}-{label}'
            scratch.mkdir()
            for name in ['Cargo.toml','Cargo.lock','rust-toolchain.toml']: shutil.copy2(name,scratch/name)
            shutil.copytree('crates',scratch/'crates')
            if Path('.cargo').exists(): shutil.copytree('.cargo',scratch/'.cargo')
            prepare(scratch,label)
            hashes={str(p.relative_to(scratch)):sha256(p) for p in sorted((scratch/'crates').rglob('*.rs'))}
            # Preserve the generated changed sources beside the measurements.
            for name,digest in hashes.items():
                if before.get(name)!=digest:
                    dest=raw/'sources'/label/name
                    dest.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copy2(scratch/name,dest)
            command=['cargo','build','--release','--locked','--offline','--jobs','1','--workspace','--examples','--bins']
            result=subprocess.run(command,cwd=scratch,env=env,capture_output=True,text=True)
            (raw/f'{label}.build.log').write_text((result.stdout+result.stderr).replace(str(ROOT),'${PROJECT}'))
            assert result.returncode==0,f'{label} build failed'
            for profile in ['debug','release']:
                test=['cargo','test','--locked','--offline','--jobs','1','--workspace']+(['--release'] if profile=='release' else [])+['--','--test-threads=1']
                result=subprocess.run(test,cwd=scratch,env=env,capture_output=True,text=True)
                log=raw/f'{label}-{profile}.test.log'
                log.write_text((result.stdout+result.stderr).replace(str(ROOT),'${PROJECT}'))
                report['tests'].append(dict(label=label,profile=profile,command=test,returncode=result.returncode,log=str(log),sha256=sha256(log)))
                save(report_path,report)
                assert result.returncode==0,f'{label} {profile} tests failed'
            for store,name in [(binaries,'psmc-rs'),(kernels,'examples/simd_bench')]:
                dest=raw/(label+('-kernel' if store is kernels else ''))
                shutil.copy2(scratch/'target/release'/name,dest)
                dest.chmod(0o555)
                store[label]=dict(path=str(dest),sha256=sha256(dest),source_sha256=hashes,build_command=command)
            save(report_path,report)
            print(json.dumps(dict(built_and_tested=label)),flush=True)
        def run(command,base):
            stats=base.with_suffix('.rss')
            timed=['/usr/bin/time','-f','%M','-o',str(stats),*command]
            old=resource.getrusage(resource.RUSAGE_CHILDREN)
            start=time.perf_counter()
            result=subprocess.run(timed,env=env,capture_output=True)
            wall=time.perf_counter()-start
            new=resource.getrusage(resource.RUSAGE_CHILDREN)
            base.with_suffix('.stdout').write_bytes(result.stdout)
            base.with_suffix('.stderr').write_bytes(result.stderr)
            assert result.returncode==0,(command,result.stderr[-500:])
            return result.stdout,dict(command=timed,cpu_seconds=new.ru_utime-old.ru_utime+new.ru_stime-old.ru_stime,
                wall_seconds=wall,peak_rss_kib=int(stats.read_text().strip()))
        def summarize(runs,extra=()):
            return {label:{key:dict(median=statistics.median(r[key] for r in runs if r['label']==label and not r['warmup']),
                minimum=min(r[key] for r in runs if r['label']==label and not r['warmup']),
                maximum=max(r[key] for r in runs if r['label']==label and not r['warmup']))
                for key in ['cpu_seconds','wall_seconds','peak_rss_kib',*extra]} for label in binaries}
        def order(rep):
            names=list(binaries)
            return names[rep%len(names):]+names[:rep%len(names)]
        cases=[dict(id='k23-n30',input='tests/fixtures/workload.psmcfa',pattern='4+5*3+4',rounds=30),
               dict(id='k64-n5',input='tests/fixtures/profile.psmcfa',pattern='4+25*2+4+6',rounds=5),
               dict(id='bootstrap-00-k23-n30',input='tests/fixtures/bootstrap/replicate-00.psmcfa',pattern='4+5*3+4',rounds=30),
               dict(id='hmm-bootstrap-10-k23-n30',input='tests/fixtures/cpu-campaign-hmm/bootstrap-10.psmcfa',pattern='4+5*3+4',rounds=30)]
        for case in cases:
            expected=None
            runs=[]
            for rep in range(6):
                for label in order(rep):
                    base=raw/f'{case["id"]}-{rep}-{label}'
                    output=base.with_suffix('.psmc')
                    command=[binaries[label]['path'],'--backend','cpu','--simd','auto','--seed','42','-o',str(output),'-p',case['pattern'],'-N',str(case['rounds']),'-t','15','-r','4','-I','0',case['input']]
                    _,timing=run(command,base)
                    data=output.read_bytes()
                    if expected is None: expected=data
                    else: compare_output(expected,data)
                    runs.append(dict(label=label,rep=rep,warmup=rep==0,output_sha256=sha256(output),**timing))
            summary=summarize(runs)
            report['cases'].append(dict(**case,input_sha256=sha256(case['input']),runs=runs,summary=summary,exact_output_match=True))
            save(report_path,report)
            print(json.dumps(dict(id=case['id'],cpu_medians={label:v['cpu_seconds']['median'] for label,v in summary.items()})),flush=True)
        if options.family in ('kernels','tails'):
            for states in [23,64]:
                runs=[]
                checksum=None
                for rep in range(6):
                    for label in order(rep):
                        base=raw/f'kernel-k{states}-{rep}-{label}'
                        command=[kernels[label]['path'],'auto',str(states),'4000','5','3']
                        stdout,timing=run(command,base)
                        data=json.loads(stdout)
                        assert data['exact_check'] and data['simd_selected']=='avx'
                        if checksum is None: checksum=data['checksum']
                        else: assert checksum==data['checksum']
                        runs.append(dict(label=label,rep=rep,warmup=rep==0,section_wall_seconds=data['seconds'],kernel_result=data,**timing))
                summary=summarize(runs,['section_wall_seconds'])
                report['kernels'].append(dict(states=states,runs=runs,summary=summary,exact_check=True))
                save(report_path,report)
                print(json.dumps(dict(kernel_states=states,section_medians={label:v['section_wall_seconds']['median'] for label,v in summary.items()})),flush=True)
        assert source_hashes()==before
        verify_binaries(provenance)
        for item in list(binaries.values())+list(kernels.values()): assert sha256(item['path'])==item['sha256']
        shutil.copy2(__file__,raw/'runner.py')
        shutil.copy2(candidate_source,raw/Path(candidate_source).name)
        report['status']='screened_not_promoted'
        report['limitations']=['Exploratory whole-output and isolated exactness gate; full C/internal/30-bootstrap/safety gates precede promotion.',
            'One warmup and five rotated measured runs on a shared host; CPU time does not remove cache/frequency contention.',
            'Peak RSS is per inference process, not aggregate system memory.',
            'Kernel process CPU time includes untimed dense exact checks; section wall times exclude them. Neither is a full inference speedup.']
    except Exception as error:
        report['status']='failed'
        report['error']=repr(error)
        raise
    finally:
        save(report_path,report)


if __name__=='__main__': main()

#!/usr/bin/env python3
"""Balanced ABBA/BAAB confirmation of a 64-state-only wide AVX candidate."""
import datetime as dt
import json
import os
from pathlib import Path
import resource
import shutil
import statistics
import subprocess
import time
from common import ROOT,save,sha256
from phase1_differential import compare_output
from phase2_common import clean_env,source_hashes,verify_binaries
from phase3_common import resource_policy
from cpu_campaign_kernel_variants import unroll


def main():
    os.chdir(ROOT)
    policy=resource_policy()
    before=source_hashes()
    provenance=json.loads(Path('bench/phase-3-validation.json').read_text())['provenance']
    verify_binaries(provenance)
    stamp=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    raw=Path('bench/cpu-campaign-engineering')/('confirm-'+stamp)
    raw.mkdir(parents=True)
    scratch=ROOT/'work'/('cpu-confirm-'+stamp)
    scratch.mkdir()
    for name in ['Cargo.toml','Cargo.lock','rust-toolchain.toml']: shutil.copy2(name,scratch/name)
    shutil.copytree('crates',scratch/'crates')
    if Path('.cargo').exists(): shutil.copytree('.cargo',scratch/'.cargo')
    unroll(scratch,16)
    source=scratch/'crates/psmc-cpu/src/simd.rs'
    text=source.read_text()
    assert text.count('let wide = n / 16 * 16;')==2
    source.write_text(text.replace('let wide = n / 16 * 16;','let wide = if n == 64 { n } else { 0 };'))
    shutil.copy2(source,raw/'simd.rs')
    env=clean_env()
    assert not any(env.get(k) for k in ['RUSTFLAGS','CARGO_ENCODED_RUSTFLAGS','CARGO_TARGET_DIR','RUSTC_WRAPPER'])
    assert not any(k.startswith('CARGO_PROFILE_') and v for k,v in env.items())
    env.update(CARGO_BUILD_JOBS='1',RUST_TEST_THREADS='1',CARGO_NET_OFFLINE='true')
    report=dict(status='running',resource_policy=policy,provenance=provenance,raw_directory=str(raw),source_sha256=before,
        generated_source_sha256=sha256(source),runner_sha256=sha256(__file__),tests=[],cases=[],
        design='Prespecified 64-state-only specialization after isolated K64 kernel improvement; retain original four-lane loop elsewhere. Six ABBA/BAAB blocks per case following one warmup per executable; every result retained. No claim based on a selected fastest run.')
    path=Path('bench/cpu-campaign-confirm.json')
    save(path,report)
    try:
        for profile in ['debug','release']:
            command=['cargo','test','--locked','--offline','--jobs','1','--workspace']+(['--release'] if profile=='release' else [])+['--','--test-threads=1']
            result=subprocess.run(command,cwd=scratch,env=env,capture_output=True,text=True)
            log=raw/(profile+'.test.log')
            log.write_text((result.stdout+result.stderr).replace(str(ROOT),'${PROJECT}'))
            report['tests'].append(dict(command=command,returncode=result.returncode,log=str(log),sha256=sha256(log)))
            assert result.returncode==0
        command=['cargo','build','--release','--locked','--offline','--jobs','1']
        result=subprocess.run(command,cwd=scratch,env=env,capture_output=True,text=True)
        (raw/'build.log').write_text((result.stdout+result.stderr).replace(str(ROOT),'${PROJECT}'))
        assert result.returncode==0
        candidate=raw/'candidate'
        shutil.copy2(scratch/'target/release/psmc-rs',candidate)
        candidate.chmod(0o555)
        binaries={'phase3a':provenance['binaries']['candidate'], 'candidate':dict(path=str(candidate),sha256=sha256(candidate))}
        report['binaries']=binaries
        cases=[dict(id='k23-n30',input='tests/fixtures/workload.psmcfa',pattern='4+5*3+4',rounds=30),
               dict(id='k64-n5',input='tests/fixtures/profile.psmcfa',pattern='4+25*2+4+6',rounds=5),
               dict(id='hmm-bootstrap-10-k23-n30',input='tests/fixtures/cpu-campaign-hmm/bootstrap-10.psmcfa',pattern='4+5*3+4',rounds=30),
               dict(id='mixed-k64-n30',input='tests/fixtures/cpu-campaign/mixed-50000.psmcfa',pattern='4+25*2+4+6',rounds=30)]
        for case in cases:
            args=['-p',case['pattern'],'-N',str(case['rounds']),'-t','15','-r','4','-I','0',case['input']]
            oracle=raw/(case['id']+'-vanilla.psmc')
            cmd=[provenance['binaries']['vanilla']['path'],'-o',str(oracle),*args]
            result=subprocess.run(cmd,env=env,capture_output=True)
            assert result.returncode==0
            (raw/(case['id']+'-vanilla.stderr')).write_bytes(result.stderr)
            expected=oracle.read_bytes()
            runs=[]
            for block in range(-1,6):
                order=['phase3a','candidate'] if block==-1 else (['phase3a','candidate','candidate','phase3a'] if block%2==0 else ['candidate','phase3a','phase3a','candidate'])
                for position,label in enumerate(order):
                    base=raw/f'{case["id"]}-{block}-{position}-{label}'
                    output=base.with_suffix('.psmc')
                    rss=base.with_suffix('.rss')
                    command=['/usr/bin/time','-f','%M','-o',str(rss),binaries[label]['path'],'--backend','cpu','--simd','auto','--seed','42','-o',str(output),*args]
                    u0=resource.getrusage(resource.RUSAGE_CHILDREN)
                    start=time.perf_counter()
                    result=subprocess.run(command,env=env,capture_output=True)
                    wall=time.perf_counter()-start
                    u1=resource.getrusage(resource.RUSAGE_CHILDREN)
                    base.with_suffix('.stderr').write_bytes(result.stderr)
                    assert result.returncode==0
                    compare_output(expected,output.read_bytes())
                    runs.append(dict(block=block,position=position,label=label,warmup=block==-1,command=command,
                                     cpu_seconds=u1.ru_utime-u0.ru_utime+u1.ru_stime-u0.ru_stime,wall_seconds=wall,peak_rss_kib=int(rss.read_text()),output_sha256=sha256(output)))
            ratios=[]
            for block in range(6):
                b=sum(r['cpu_seconds'] for r in runs if r['block']==block and r['label']=='phase3a')
                c=sum(r['cpu_seconds'] for r in runs if r['block']==block and r['label']=='candidate')
                ratios.append(b/c)
            summary={label:{key:dict(median=statistics.median(r[key] for r in runs if r['label']==label and not r['warmup']),minimum=min(r[key] for r in runs if r['label']==label and not r['warmup']),maximum=max(r[key] for r in runs if r['label']==label and not r['warmup'])) for key in ['cpu_seconds','wall_seconds','peak_rss_kib']} for label in binaries}
            report['cases'].append(dict(**case,input_sha256=sha256(case['input']),oracle_command=cmd,oracle_sha256=sha256(oracle),runs=runs,summary=summary,paired_cpu_ratios=ratios,paired_ratio_median=statistics.median(ratios),blocks_candidate_faster=sum(x>1 for x in ratios),exact_output_match=True))
            save(path,report)
            print(json.dumps(dict(id=case['id'],paired_cpu_ratios=ratios,paired_ratio_median=statistics.median(ratios))),flush=True)
        assert source_hashes()==before
        verify_binaries(provenance)
        assert sha256(candidate)==binaries['candidate']['sha256']
        shutil.copy2(__file__,raw/'runner.py')
        report['status']='screened_not_promoted'
        report['limitations']=['Balanced neighboring comparisons reduce order bias but do not remove shared-hardware interference.',
            'Full isolated and printed-output gates pass; complete internal snapshots and serial bootstrap integration still precede any promotion.',
            '64-state specialization only; other shapes retain the original loop. No universal state-count or production speedup claim.']
    except Exception as error:
        report['status']='failed'; report['error']=repr(error)
        raise
    finally: save(path,report)


if __name__=='__main__': main()

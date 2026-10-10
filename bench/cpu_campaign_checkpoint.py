#!/usr/bin/env python3
"""Exact checkpoint/recompute memory-time experiment, never a full-fit speed claim."""
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
from phase2_common import clean_env,source_hashes
from phase3_common import resource_policy


def main():
    os.chdir(ROOT)
    policy=resource_policy()
    before=source_hashes()
    stamp=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    raw=Path('bench/cpu-campaign-engineering')/('checkpoint-'+stamp)
    raw.mkdir(parents=True)
    scratch=ROOT/'work'/('cpu-checkpoint-'+stamp)
    scratch.mkdir()
    for name in ['Cargo.toml','Cargo.lock','rust-toolchain.toml']: shutil.copy2(name,scratch/name)
    shutil.copytree('crates',scratch/'crates')
    if Path('.cargo').exists(): shutil.copytree('.cargo',scratch/'.cargo')
    source=Path('bench/cpu_campaign_checkpoint.rs')
    example=Path('bench/cpu_campaign_checkpoint_bench.rs')
    shutil.copy2(source,scratch/'crates/psmc-cpu/src/checkpoint_candidate.rs')
    shutil.copy2(example,scratch/'crates/psmc-cpu/examples/checkpoint_bench.rs')
    with (scratch/'crates/psmc-cpu/src/lib.rs').open('a') as stream: stream.write('\npub mod checkpoint_candidate;\n')
    env=clean_env()
    assert not any(env.get(k) for k in ['RUSTFLAGS','CARGO_ENCODED_RUSTFLAGS','CARGO_TARGET_DIR','RUSTC_WRAPPER'])
    assert not any(k.startswith('CARGO_PROFILE_') and v for k,v in env.items())
    env.update(CARGO_BUILD_JOBS='1',RUST_TEST_THREADS='1',CARGO_NET_OFFLINE='true')
    report=dict(status='running',resource_policy=policy,raw_directory=str(raw),source_sha256=before,
         experiment_source_sha256=sha256(source),example_sha256=sha256(example),runner_sha256=sha256(__file__),tests=[],cases=[])
    path=Path('bench/cpu-campaign-checkpoint.json')
    save(path,report)
    try:
        for profile in ['debug','release']:
            command=['cargo','test','--locked','--offline','--jobs','1','--workspace']+(['--release'] if profile=='release' else [])+['--','--test-threads=1']
            result=subprocess.run(command,cwd=scratch,env=env,capture_output=True,text=True)
            log=raw/(profile+'.test.log')
            log.write_text((result.stdout+result.stderr).replace(str(ROOT),'${PROJECT}'))
            report['tests'].append(dict(command=command,returncode=result.returncode,log=str(log),sha256=sha256(log)))
            save(path,report)
            assert result.returncode==0,'See checkpoint test log'
        command=['cargo','build','--release','--locked','--offline','--jobs','1','-p','psmc-cpu','--example','checkpoint_bench']
        result=subprocess.run(command,cwd=scratch,env=env,capture_output=True,text=True)
        (raw/'build.log').write_text((result.stdout+result.stderr).replace(str(ROOT),'${PROJECT}'))
        assert result.returncode==0
        binary=raw/'checkpoint-bench'
        shutil.copy2(scratch/'target/release/examples/checkpoint_bench',binary)
        binary.chmod(0o555)
        report['binary']=dict(path=str(binary),sha256=sha256(binary),command=command)
        for n,length in [(23,20000),(64,20000),(23,200000),(64,200000)]:
            checks=[]
            expected=None
            for tile in [64,256,1024]:
                command=[str(binary),'check',str(n),str(length),'2',str(tile)]
                result=subprocess.run(command,env=env,capture_output=True,text=True)
                assert result.returncode==0,result.stderr
                data=json.loads(result.stdout)
                if expected is None: expected=data['checksum']
                else: assert expected==data['checksum']
                checks.append(dict(command=command,result=data))
            runs=[]
            labels=['baseline','cp64','cp256','cp1024']
            for rep in range(6):
                for label in labels[rep%4:]+labels[:rep%4]:
                    mode='baseline' if label=='baseline' else 'checkpoint'
                    tile=256 if label=='baseline' else int(label[2:])
                    command=[str(binary),mode,str(n),str(length),'2',str(tile)]
                    base=raw/f'k{n}-l{length}-{rep}-{label}'
                    rss=base.with_suffix('.rss')
                    timed=['/usr/bin/time','-f','%M','-o',str(rss),*command]
                    usage0=resource.getrusage(resource.RUSAGE_CHILDREN)
                    started=time.perf_counter()
                    result=subprocess.run(timed,env=env,capture_output=True)
                    wall=time.perf_counter()-started
                    usage1=resource.getrusage(resource.RUSAGE_CHILDREN)
                    base.with_suffix('.stdout').write_bytes(result.stdout)
                    base.with_suffix('.stderr').write_bytes(result.stderr)
                    assert result.returncode==0,result.stderr
                    data=json.loads(result.stdout)
                    assert data['checksum']==expected
                    runs.append(dict(label=label,rep=rep,warmup=rep==0,command=timed,result=data,wall_seconds=wall,
                                     cpu_seconds=usage1.ru_utime-usage0.ru_utime+usage1.ru_stime-usage0.ru_stime,peak_rss_kib=int(rss.read_text())))
            summary={label:{key:dict(median=statistics.median(r[key] for r in runs if r['label']==label and not r['warmup']),
                                    minimum=min(r[key] for r in runs if r['label']==label and not r['warmup']),
                                    maximum=max(r[key] for r in runs if r['label']==label and not r['warmup'])) for key in ['cpu_seconds','wall_seconds','peak_rss_kib']} for label in labels}
            report['cases'].append(dict(states=n,bins=length,repeats=2,checks=checks,runs=runs,summary=summary))
            save(path,report)
            print(json.dumps(dict(states=n,bins=length,summary=summary)),flush=True)
        assert source_hashes()==before
        assert sha256(binary)==report['binary']['sha256']
        for file in [source,example,Path(__file__)]: shutil.copy2(file,raw/file.name)
        report['status']='screened_not_promoted'
        report['limitations']=['Isolated fixed-model HMM experiment, not integrated into fitting or snapshots.',
            'Exact checks run in separate processes so baseline message allocation cannot contaminate checkpoint RSS.',
            'Candidate recomputes forward and backward messages once; no sequence boundaries or count addends change.',
            'Shared-host timings; no full-fit, real-genome or multiworker claim.']
    except Exception as error:
        report['status']='failed'; report['error']=repr(error)
        raise
    finally: save(path,report)


if __name__=='__main__': main()

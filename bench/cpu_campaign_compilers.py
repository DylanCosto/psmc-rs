#!/usr/bin/env python3
"""Single-CPU compiler/PGO screen; no source or release-profile mutation."""
import bisect
import datetime as dt
import itertools
import json
import os
from pathlib import Path
import random
import resource
import shutil
import statistics
import subprocess
import time
from common import ROOT, save, sha256, write_fasta
from phase1_differential import compare_output
from phase2_common import clean_env, source_hashes, verify_binaries
from phase3_common import resource_policy


def main():
    os.chdir(ROOT)
    policy = resource_policy()
    before = source_hashes()
    provenance = json.loads(Path('bench/cpu-campaign-profile.json').read_text())['provenance']
    verify_binaries(provenance)
    stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    raw = Path('bench/cpu-campaign-compilers')/stamp
    raw.mkdir(parents=True)
    scratch = ROOT/'work'/('cpu-compilers-'+stamp)
    scratch.mkdir()
    for name in ['Cargo.toml','Cargo.lock','rust-toolchain.toml']:
        shutil.copy2(name,scratch/name)
    shutil.copytree('crates',scratch/'crates')
    if Path('.cargo').exists(): shutil.copytree('.cargo',scratch/'.cargo')
    env = clean_env()
    assert not any(env.get(k) for k in ['RUSTFLAGS','CARGO_ENCODED_RUSTFLAGS','CARGO_TARGET_DIR','RUSTC_WRAPPER'])
    assert not any(k.startswith('CARGO_PROFILE_') and v for k,v in env.items())
    env.update(CARGO_BUILD_JOBS='1',RUST_TEST_THREADS='1',CARGO_NET_OFFLINE='true')
    binaries = {'phase3a':provenance['binaries']['phase3a']}
    builds = []
    target = 'x86_64-unknown-linux-gnu'
    def build(label,opt,lto,flags=''):
        targetdir=scratch/('target-'+label)
        overrides=dict(CARGO_TARGET_DIR=str(targetdir),CARGO_PROFILE_RELEASE_OPT_LEVEL=str(opt),
                       CARGO_PROFILE_RELEASE_LTO=lto,CARGO_PROFILE_RELEASE_CODEGEN_UNITS='1',RUSTFLAGS=flags)
        command=['cargo','build','--release','--locked','--offline','--jobs','1','--target',target]
        result=subprocess.run(command,cwd=scratch,env={**env,**overrides},capture_output=True,text=True)
        (raw/f'{label}.build.log').write_text((result.stdout+result.stderr).replace(str(ROOT),'${PROJECT}'))
        assert result.returncode==0,label
        dest=raw/label
        shutil.copy2(targetdir/target/'release/psmc-rs',dest)
        dest.chmod(0o555)
        record=dict(path=str(dest),sha256=sha256(dest),overrides={k:v.replace(str(ROOT),'${PROJECT}') for k,v in overrides.items()},command=command)
        builds.append(dict(label=label,**record))
        return record
    for label,opt,lto in [('opt3',3,'false'),('opt2-thin',2,'thin'),('opt3-thin',3,'thin'),('opt3-fat',3,'fat')]:
        binaries[label]=build(label,opt,lto)
        print(json.dumps(dict(built=label)),flush=True)
    # PGO training input uses a different RNG seed and newly generated records,
    # not resampled or shortened versions of any held-out benchmark input.
    model=json.loads(Path('tests/fixtures/cpu-campaign-hmm/generating-model.jsonl').read_text().splitlines()[0])
    rng=random.Random(20261013)
    initial=list(itertools.accumulate(model['initial']))
    transitions=[list(itertools.accumulate(row)) for row in model['transition']]
    def draw(cdf):
        value=bisect.bisect_left(cdf,rng.random())
        assert value<len(cdf)
        return value
    records=[]
    for i,length in enumerate([8192,12289,8191]):
        state=draw(initial)
        symbols=[]
        for u in range(length):
            state=draw(transitions[state])
            symbol='T' if rng.random()<model['emission'][0][state] else 'K'
            symbols.append('N' if 300<=u%1024<350 else symbol)
        records.append((f'pgo_training_{i}',''.join(symbols)))
    training=raw/'training.psmcfa'
    write_fasta(training,records)
    sysroot=Path(subprocess.check_output(['rustc','--print','sysroot'],text=True).strip())
    profdata=sysroot/'lib/rustlib'/target/'bin/llvm-profdata'
    assert profdata.is_file(),'Install matching Rust 1.90 llvm-tools-preview component before PGO.'
    profile_dir=scratch/'pgo-data'
    profile_dir.mkdir()
    generator=build('pgo-generate',3,'thin',f'-Cprofile-generate={profile_dir}')
    train_runs=[]
    for name,pattern in [('k4','2+2'),('k23','4+5*3+4'),('k64','4+25*2+4+6')]:
        args=['--backend','cpu','--simd','auto','--seed','42','-p',pattern,'-N','5','-t','15','-r','4','-I','0',str(training)]
        outputs=[]
        for label,record in [('train',generator),('oracle',binaries['phase3a'])]:
            output=raw/f'training-{name}-{label}.psmc'
            command=[record['path'],'-o',str(output),*args]
            run=subprocess.run(command,env=env,capture_output=True)
            (raw/f'training-{name}-{label}.stderr').write_bytes(run.stderr)
            assert run.returncode==0
            outputs.append(output.read_bytes())
            train_runs.append(dict(label=label,command=command,output_sha256=sha256(output)))
        compare_output(*outputs)
    merged=raw/'merged.profdata'
    profiles=sorted(profile_dir.glob('*.profraw'))
    assert profiles
    merge=[str(profdata),'merge','-o',str(merged),*[str(p) for p in profiles]]
    result=subprocess.run(merge,capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    binaries['pgo-opt3-thin']=build('pgo-opt3-thin',3,'thin',f'-Cprofile-use={ROOT/merged} -Cllvm-args=-pgo-warn-missing-function')
    pgo=dict(training_seed=20261013,training_input=str(training),training_sha256=sha256(training),runs=train_runs,
             llvm_profdata_sha256=sha256(profdata),merge_command=[s.replace(str(ROOT),'${PROJECT}').replace(str(Path.home()),'${USER_HOME}') for s in merge],
             merged_sha256=sha256(merged),raw_profiles={p.name:sha256(p) for p in profiles})
    cases=[dict(id='k23-n30',input='tests/fixtures/workload.psmcfa',pattern='4+5*3+4',rounds=30),
           dict(id='k64-n5',input='tests/fixtures/profile.psmcfa',pattern='4+25*2+4+6',rounds=5),
           dict(id='bootstrap-00-k23-n30',input='tests/fixtures/bootstrap/replicate-00.psmcfa',pattern='4+5*3+4',rounds=30),
           dict(id='hmm-bootstrap-10-k23-n30',input='tests/fixtures/cpu-campaign-hmm/bootstrap-10.psmcfa',pattern='4+5*3+4',rounds=30)]
    results=[]
    for case in cases:
        assert sha256(case['input'])!=pgo['training_sha256']
        runs=[]
        expected=None
        for rep in range(6):
            labels=list(binaries)
            labels=labels[rep%len(labels):]+labels[:rep%len(labels)]
            for label in labels:
                output=raw/f'{case["id"]}-{rep}-{label}.psmc'
                command=[binaries[label]['path'],'--backend','cpu','--simd','auto','--seed','42','-o',str(output),'-p',case['pattern'],'-N',str(case['rounds']),'-t','15','-r','4','-I','0',case['input']]
                usage0=resource.getrusage(resource.RUSAGE_CHILDREN)
                start=time.perf_counter()
                run=subprocess.run(command,env=env,capture_output=True)
                wall=time.perf_counter()-start
                usage1=resource.getrusage(resource.RUSAGE_CHILDREN)
                cpu=(usage1.ru_utime-usage0.ru_utime)+(usage1.ru_stime-usage0.ru_stime)
                (raw/f'{case["id"]}-{rep}-{label}.stderr').write_bytes(run.stderr)
                assert run.returncode==0
                data=output.read_bytes()
                if expected is None: expected=data
                else: compare_output(expected,data)
                runs.append(dict(label=label,rep=rep,warmup=rep==0,command=command,cpu_seconds=cpu,wall_seconds=wall,output_sha256=sha256(output)))
        summary={label:{kind:dict(median=statistics.median(r[kind] for r in runs if r['label']==label and not r['warmup']),
                                 minimum=min(r[kind] for r in runs if r['label']==label and not r['warmup']),
                                 maximum=max(r[kind] for r in runs if r['label']==label and not r['warmup'])) for kind in ['cpu_seconds','wall_seconds']} for label in binaries}
        results.append(dict(**case,input_sha256=sha256(case['input']),runs=runs,summary=summary,exact_output_match=True))
        print(json.dumps(dict(id=case['id'],summary=summary)),flush=True)
    assert source_hashes()==before
    verify_binaries(provenance)
    for item in binaries.values(): assert sha256(item['path'])==item['sha256']
    shutil.copy2(__file__,raw/'runner.py')
    save('bench/cpu-campaign-compilers.json',dict(status='screened_not_promoted',resource_policy=policy,raw_directory=str(raw),
         provenance=provenance,source_sha256=before,binaries=binaries,builds=builds,pgo=pgo,cases=results,runner_sha256=sha256(__file__),
         documentation=['https://doc.rust-lang.org/rustc/profile-guided-optimization.html','https://doc.rust-lang.org/cargo/reference/profiles.html'],
         limitations=['Exploratory gate only; full strict gate required before promotion.','All builds retain binary64 and portable target; no target-cpu=native, fast-math or FMA option.',
                     'One training seed with distinct independently generated observations; held-out cases never trained.',
                     'Shared-host timing ranges retained. Final benchmarking must also report RSS and complete batches.']))


if __name__=='__main__': main()

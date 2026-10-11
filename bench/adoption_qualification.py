#!/usr/bin/env python3
"""Frozen, bounded production qualification; never uploads genomic data."""
import bisect,fcntl,hashlib,json,math,os,resource,shutil,signal,statistics,subprocess,sys,tarfile,time
from pathlib import Path
import known_truth as p
from known_truth_200mb import BANDS
from hg001_genome_run import timing
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'work/adoption-qualification';GIB=1024**3
GENOME=ROOT/'work/hg001-genome/HG001_GRCh38_autosomes.psmcfa'
HG002=ROOT/'work/adoption-input/HG002_GRCh38_chr1.psmcfa'
SEED=20261011

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()
def save(path,value):Path(path).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
def available():return int(next(l.split()[1] for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:')))*1024

def child():
    resource.setrlimit(resource.RLIMIT_AS,(12*GIB,12*GIB));resource.setrlimit(resource.RLIMIT_FSIZE,(512*1024**2,512*1024**2))
    os.nice(10);os.environ['MALLOC_ARENA_MAX']='2';os.execv(sys.argv[2],sys.argv[2:])

def stage(name,command):
    assert available()>=14*GIB and shutil.disk_usage(OUT).free>=25*GIB,'preflight resource floor'
    command=list(map(str,command));started=time.monotonic()
    wrapped=['/usr/bin/time','-v','-o',str(OUT/(name+'.time')),sys.executable,str(Path(__file__).resolve()),'--child',*command]
    with (OUT/(name+'.out')).open('x') as out,(OUT/(name+'.stderr')).open('x') as err,(OUT/'resources.jsonl').open('a',buffering=1) as samples:
        process=subprocess.Popen(wrapped,stdout=out,stderr=err,start_new_session=True)
        def stop(reason):
            save(OUT/'stop.json',{'stage':name,'reason':reason,'pid':process.pid,'time':time.time()})
            try:os.killpg(process.pid,signal.SIGTERM)
            except ProcessLookupError:pass
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
            raise RuntimeError(reason)
        signal.signal(signal.SIGTERM,lambda *_:stop('external SIGTERM'))
        signal.signal(signal.SIGINT,lambda *_:stop('external SIGINT'))
        while True:
            ram=available();disk=shutil.disk_usage(OUT).free;footprint=sum(f.stat().st_size for f in OUT.rglob('*') if f.is_file())
            samples.write(json.dumps(dict(time=time.time(),stage=name,pid=process.pid,available_ram=ram,free_disk=disk,campaign_bytes=footprint))+'\n')
            if ram<4*GIB or disk<25*GIB or footprint>2*GIB:stop('runtime resource floor/footprint guard')
            if process.poll() is not None:break
            time.sleep(2)
        if process.returncode:stop(f'child exit {process.returncode}')
    result=dict(command=command,wall_seconds=time.monotonic()-started,timing=timing(OUT/(name+'.time')),exit_code=process.returncode,output_sha256=sha(OUT/(name+'.out')),stderr_sha256=sha(OUT/(name+'.stderr')))
    save(OUT/(name+'.done.json'),result);print(name,'completed',round(result['wall_seconds'],2),flush=True)
    return result

def build_reference():
    archive=ROOT/'work/psmc-source-vanilla.tar'
    expected=json.loads((ROOT/'reference/build-vanilla.json').read_text())['source_archive_sha256']
    assert sha(archive)==expected
    records={}
    for mode,flags in [('c-o2','-O2 -ffp-contract=off'),('c-fma','-O2 -ffp-contract=fast -mfma')]:
        directory=OUT/mode;directory.mkdir()
        with tarfile.open(archive) as tar:tar.extractall(directory,filter='data')
        include=ROOT/'work/deps/zlib/usr/include'
        flags+=f' -Wno-unused-function -I{include}'
        command=['make','-j2','CC=gcc',f'CFLAGS={flags}',f'CCFLAGS={flags}','LIBS=-lm -l:libz.so.1']
        with (directory/'build.log').open('w') as log:subprocess.run(command,cwd=directory,stdout=log,stderr=log,check=True)
        shutil.copy2(directory/'psmc',OUT/'binaries'/mode)
        records[mode]={'flags':flags,'source_archive_sha256':expected,'compiler':subprocess.check_output(['gcc','--version'],text=True).splitlines()[0]}
    return records

def logs(params):
    result={}
    for band,(a,b) in BANDS.items():
        times=[a*(b/a)**(i/128) for i in range(128)]
        result[band]=[math.log(params['n0']*params['lambdas'][max(0,bisect.bisect_right(params['group_starts_generations'],t)-1)]) for t in times]
    return result

def read_fit(path,bins):
    text=path.read_text();_,params=p.curve(text)
    likelihood=float([l.split()[1] for l in text.splitlines() if l.startswith('LK\t')][-1])
    finite=all(math.isfinite(float(w)) for l in text.splitlines() if l.startswith(('LK\t','TR\t','RS\t','PA\t')) for w in (l.split()[2:] if l.startswith('PA\t') else l.split()[1:]))
    return dict(params=params,curves=logs(params),legacy_lk=likelihood,bins=bins,finite_trajectory=finite,sha256=sha(path))

def compare(a,b):
    bands={}
    for band in BANDS:
        diffs=[abs(x-y) for x,y in zip(a['curves'][band],b['curves'][band])]
        bands[band]={'rms':math.sqrt(statistics.mean(d*d for d in diffs)),'max':max(diffs)}
    result=dict(bands=bands,theta_relative=abs(b['params']['theta']/a['params']['theta']-1),rho_relative=abs(b['params']['rho']/a['params']['rho']-1),legacy_lk_per_bin=abs(a['legacy_lk']-b['legacy_lk'])/a['bins'])
    result['exploratory_screen']=a['finite_trajectory'] and b['finite_trajectory'] and all(bands[k]['rms']<=.01 for k in ['primary_early','primary_late']) and result['theta_relative']<=.001 and result['rho_relative']<=.001 and result['legacy_lk_per_bin']<=1e-6
    return result

def analyze():
    frozen=json.loads((OUT/'frozen.json').read_text());panels=[]
    for dataset,input_file in [('hg001-chr22',ROOT/'work/hg001-genome/chromosomes/chr22.psmcfa'),('hg002-chr1',HG002)]:
        bins=sum(len(l.strip()) for l in input_file.read_text().splitlines() if not l.startswith('>'))
        for pattern in ['4+5*3+4','8+8+8+8']:
            label=dataset+'-'+pattern.replace('*','x');fits={m:read_fit(OUT/(label+'-'+m+'.out'),bins) for m in ['c-o2','c-fma','strict','equivalent']}
            exact=p.numerical((OUT/(label+'-c-o2.out')).read_text())==p.numerical((OUT/(label+'-strict.out')).read_text())
            control=compare(fits['c-o2'],fits['c-fma']);alternate=compare(fits['strict'],fits['equivalent'])
            panels.append(dict(dataset=dataset,pattern=pattern,strict_c_exact=exact,compiler_control=control,equivalent_comparison=alternate,screen_calibrated=control['exploratory_screen'],fits=fits))
    manifests={mode:json.loads((OUT/mode/'manifest.json').read_text()) for mode in ['strict','equivalent']}
    assert all(len(m['replicates'])==30 and m['failed_replicates']==0 for m in manifests.values())
    pairs=[]
    for index in range(30):
        reports={m:manifests[m]['replicates'][index] for m in manifests};assert reports['strict']['source_indices']==reports['equivalent']['source_indices']
        traces={m:sha(OUT/m/f'replicate-{index:02}.draws.jsonl') for m in manifests};assert len(set(traces.values()))==1
        fits={m:read_fit(OUT/m/f'replicate-{index:02}.psmc',reports[m]['length']) for m in manifests}
        stats={m:json.loads((OUT/m/f'replicate-{index:02}.stats.json').read_text()) for m in manifests}
        pairs.append(dict(index=index,comparison=compare(fits['strict'],fits['equivalent']),fits=fits,stats=stats,trace_sha256=traces['strict']))
    uncertainty={};flagged=set()
    for band in BANDS:
        sd=[statistics.stdev(pair['fits']['strict']['curves'][band][i] for pair in pairs) for i in range(128)]
        ratios=[];undefined=0
        for pair in pairs:
            differences=[abs(x-y) for x,y in zip(pair['fits']['strict']['curves'][band],pair['fits']['equivalent']['curves'][band])]
            ratio=[d/s if s else None for d,s in zip(differences,sd)];undefined+=sum(v is None for v in ratio)
            finite=[v for v in ratio if v is not None];maximum=max(finite) if finite else None
            pair.setdefault('uncertainty_max_ratio',{})[band]=maximum;ratios.extend(finite)
            if band.startswith('primary') and (maximum is None or maximum>.1):flagged.add(pair['index'])
        uncertainty[band]=dict(strict_sample_sd=sd,max_ratio=max(ratios) if ratios else None,undefined_ratios=undefined)
    for pair in pairs:
        if not pair['comparison']['exploratory_screen']:flagged.add(pair['index'])
    report=dict(schema=1,frozen=frozen,additional_patterns=panels,bootstrap_pairs=pairs,uncertainty=uncertainty,diagnostic_required=sorted(flagged),scientific_scope='Exploratory bounds and empirical uncertainty; no whole-genome C compiler-noise distribution or demographic truth claim',runs={f.stem.removesuffix('.done'):json.loads(f.read_text()) for f in OUT.glob('*.done.json')})
    save(OUT/'report.json',report);print('completed, diagnostics required:',sorted(flagged),flush=True)

def main():
    OUT.mkdir(exist_ok=False)
    with (OUT/'run.lock').open('x') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);lock.write(str(os.getpid()));lock.flush()
        assert not subprocess.check_output(['git','status','--porcelain'],cwd=ROOT)
        assert sha(GENOME)=='9d8633f04981b2b24114cad540368f46c508bf4290a976c430a182afcd55a112'
        assert sha(HG002)=='16d0f60777857fc724d46464da84c9b46c0755d3dbd7f678dfc88f1caed9bc14'
        (OUT/'binaries').mkdir();shutil.copy2(ROOT/'target/release/psmc-rs',OUT/'binaries/rust');build=build_reference()
        binary=OUT/'binaries/rust'
        save(OUT/'frozen.json',dict(commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),protocol_sha256=sha(ROOT/'docs/adoption-qualification-protocol.md'),runner_sha256=sha(__file__),binary_hashes={p.name:sha(p) for p in (OUT/'binaries').iterdir()},input_sha256={str(p.relative_to(ROOT)):sha(p) for p in [GENOME,HG002]},builds=build,version=subprocess.check_output([binary,'--version'],text=True).strip(),created=time.time()))
        stage('split',[binary,'split','--block-bins','50000','--output',OUT/'blocks.psmcfa',GENOME])
        # Start with the longest stage while retaining completed-fit checkpoints.
        for mode in ['strict','equivalent']:
            stage('bootstrap-'+mode,[binary,'bootstrap','--mode',mode,'--seed',str(SEED),'--replicates','30','--workers','16','--memory-mib','8192','--progress','--output-dir',OUT/mode,*p.FIT,OUT/'blocks.psmcfa'])
        for dataset,input_file in [('hg001-chr22',ROOT/'work/hg001-genome/chromosomes/chr22.psmcfa'),('hg002-chr1',HG002)]:
            for pattern in ['4+5*3+4','8+8+8+8']:
                fit=['-p',pattern,'-N','30','-t','15','-r','5','-I','0']
                for mode in ['c-o2','c-fma','strict','equivalent']:
                    name=dataset+'-'+pattern.replace('*','x')+'-'+mode
                    command=['/usr/bin/taskset','-c',str(min(os.sched_getaffinity(0))),OUT/'binaries'/mode,*fit,input_file] if mode.startswith('c-') else [binary,'--mode',mode,'--seed',str(SEED),'--record-workers','4','--memory-mib','4096','--stats',OUT/(name+'.stats.json'),*fit,input_file]
                    stage(name,command)
        analyze()

if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--child':child()
    elif len(sys.argv)>1 and sys.argv[1]=='--analyze':analyze()
    else:
        try:main()
        except BaseException as e:
            if OUT.exists():save(OUT/'failure.json',{'error':repr(e),'time':time.time()})
            raise

#!/usr/bin/env python3
"""Prospective diagnostic runner; see docs/stable-model-protocol.md."""
import hashlib,json,math,os,random,resource,shutil,subprocess,time,sys
from pathlib import Path
from pilot_decimal_model import model as decimal_model
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'work/stable-model'
BINARY=ROOT/'target/release/examples/stable_model_check'
CPU=min(os.sched_getaffinity(0))

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def guarded():
    os.sched_setaffinity(0,{CPU});os.nice(10)
    resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3))
    resource.setrlimit(resource.RLIMIT_FSIZE,(512*1024**2,512*1024**2))
def run(args,**kwargs):
    p=subprocess.run([str(x) for x in args],cwd=ROOT,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,preexec_fn=guarded,**kwargs)
    if p.returncode:raise RuntimeError(p.stderr)
    return p.stdout

def groups(pattern):
    out=[]; g=0
    for term in pattern.split('+'):
        a=list(map(int,term.split('*')));repeat,width=(1,a[0]) if len(a)==1 else a
        for _ in range(repeat):out.extend([g]*width);g+=1
    return out

def main():
    available=int(next(l.split()[1] for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:')))*1024
    assert available>=4*1024**3 and shutil.disk_usage(ROOT).free>=25*1024**3
    analyze_only='--analyze-existing' in sys.argv
    if not analyze_only: OUT.mkdir(exist_ok=False)
    rng=random.Random(20261011)
    cases=[]
    for pattern in ['2+2+2','4+5*3+4','4+25*2+4+6']:
        gs=groups(pattern);nfree=max(gs)+1
        for scale in [0.1,1,10,1e3,1e6,1e9]:
            cases.append(dict(label=f'{pattern}-lambda-{scale}',pattern=pattern,params=[.01,.002,15.]+[scale]*nfree))
        for i in range(50):
            cases.append(dict(label=f'{pattern}-sweep-{i}',pattern=pattern,params=[10**rng.uniform(-4,-1),10**rng.uniform(-5,-2),rng.uniform(.5,30)]+[10**rng.uniform(-1,7) for _ in range(nfree)]))
    for case in ['bottleneck-01','bottleneck-03','bottleneck-09','expansion-09']:
        path=ROOT/'work/pilot-surface'/f'{case}.matrix-points.json'
        for p in json.loads(path.read_text()):
            cases.append(dict(label=case+'-'+p['label'],pattern='4+25*2+4+6',params=p['params'],pilot=case,pilot_label=p['label']))
    (OUT/'points.json').write_text(json.dumps(cases,indent=2)+'\n')
    results=[]; failures=[]
    matrices={}
    for pattern in dict.fromkeys(p['pattern'] for p in cases):
        selected=[p for p in cases if p['pattern']==pattern]
        raw=(OUT/(pattern.replace('*','x')+'.matrices')).read_text() if analyze_only else run([BINARY,'matrices',pattern],input=''.join(' '.join(map(repr,p['params']))+'\n' for p in selected))
        (OUT/(pattern.replace('*','x')+'.matrices')).write_text(raw)
        lines=raw.splitlines();assert len(lines)==len(selected)
        gs=groups(pattern);n=len(gs)
        for point,line in zip(selected,lines):
            label=point['label']
            try: oracle=decimal_model(point['params'],gs,50)
            except Exception as e:
                results.append(dict(label=label,status='oracle_domain_excluded',error=str(e)));continue
            if line=='invalid':
                failures.append(label);results.append(dict(label=label,status='candidate_invalid'));continue
            candidate=list(map(float,line.split()));assert len(candidate)==len(oracle)
            max_abs=max(abs(a-b) for a,b in zip(candidate,oracle))
            tolerance_ratio=max(abs(a-b)/(1e-14+1e-12*abs(b)) for a,b in zip(candidate,oracle))
            stationary=max(abs(sum(candidate[k]*candidate[n+k*n+j] for k in range(n))-candidate[j]) for j in range(n))
            normalization=max([abs(sum(candidate[:n])-1),*[abs(sum(candidate[n+k*n:n+(k+1)*n])-1) for k in range(n)]])
            valid=all(math.isfinite(x) and 0<=x<=1 for x in candidate)
            passed=valid and tolerance_ratio<=1 and stationary<=1e-12 and normalization<=1e-12
            if not passed:failures.append(label)
            record=dict(label=label,status='passed' if passed else 'failed',max_abs_error=max_abs,max_tolerance_ratio=tolerance_ratio,stationary_residual=stationary,normalization_residual=normalization)
            if 'lambda-' in label and ('1000000' in label or '1000000000' in label):
                high=decimal_model(point['params'],gs,80);record['decimal_50_80_max_difference']=max(abs(a-b) for a,b in zip(oracle,high))
            results.append(record)
            if point.get('pilot_label') in ['strict-80','equivalent-80']:
                matrices[label]=(point,candidate,oracle)
    endpoints=[]
    for case in ['bottleneck-01','bottleneck-03','bottleneck-09','expansion-09']:
        matrix=OUT/(case+'.endpoints');lines=[]
        for name in ['strict','equivalent']:
            p,c,o=matrices[f'{case}-{name}-80']
            for label,values in [('candidate',c),('decimal',o)]:lines.append(f'{name}-{label} '+' '.join(map(repr,p['params']+values)))
        matrix.write_text('\n'.join(lines)+'\n')
        directory=ROOT/'work/qualification/panel'/case
        raw=(OUT/(case+'.likelihood.jsonl')).read_text() if analyze_only else run([ROOT/'target/release/examples/pilot_matrix_likelihood',directory/'input.psmcfa',directory/'strict.out',matrix])
        (OUT/(case+'.likelihood.jsonl')).write_text(raw)
        records=[json.loads(l) for l in raw.splitlines()]
        for name in ['strict','equivalent']:
            a=next(r for r in records if r['label']==name+'-candidate');b=next(r for r in records if r['label']==name+'-decimal')
            delta=a['ll']-b['ll'];passed=abs(delta)<=1e-8
            if not passed:failures.append(case+'-'+name+'-LL')
            endpoints.append(dict(case=case,mode=name,ll_candidate=a['ll'],ll_decimal=b['ll'],difference=delta,status='passed' if passed else 'failed',input_sha256=sha(directory/'input.psmcfa'),matrix_sha256=sha(matrix)))
    fits=[]
    for pattern in ['2+2+2','4+5*3+4','4+25*2+4+6']:
        for mode in ['literal','stable']:
            raw=(OUT/f'{pattern.replace("*","x")}-{mode}.json').read_text() if analyze_only else run([BINARY,'fit',pattern,ROOT/'tests/fixtures/workload.psmcfa',mode])
            fit=json.loads(raw);fit.update(pattern=pattern,mode=mode,nonfinite_last_estep=not math.isfinite(fit['last_estep_ll']));fits.append(fit)
            (OUT/f'{pattern.replace("*","x")}-{mode}.json').write_text(raw)
    # Independently evaluate the six final vectors with Decimal construction,
    # including the literal fit whose last E-step was nonfinite.
    for fit in fits:
        name=fit['pattern'].replace('*','x')+'-'+fit['mode']; params=fit['params']
        oracle=decimal_model(params,groups(fit['pattern']),50)
        high=decimal_model(params,groups(fit['pattern']),80)
        assert oracle==high
        matrix=OUT/(name+'.decimal-matrix')
        matrix.write_text('final '+' '.join(map(repr,params+oracle))+'\n')
        pa=OUT/(name+'.pa');pa.write_text('PA\t'+fit['pattern']+' '+' '.join(map(repr,params))+'\n')
        raw=(OUT/(name+'.decimal-ll')).read_text() if analyze_only else run([
            '/usr/bin/time','-f','peak_rss_kib=%M','-o',OUT/(name+'.decimal-time'),
            ROOT/'target/release/examples/pilot_matrix_likelihood',ROOT/'tests/fixtures/workload.psmcfa',pa,matrix])
        (OUT/(name+'.decimal-ll')).write_text(raw)
        result=json.loads(raw)
        fit['independent_decimal_ll']=result['ll']
        fit['independent_ll_minus_engine']=result['ll']-fit['final_ll']
        fit['decimal_50_80_identical']=True
    report=dict(schema=1,source_base=run(['git','rev-parse','HEAD']).strip(),candidate_source_sha256=sha(ROOT/'crates/psmc-cli/examples/support/stable_model.rs'),binary_sha256=sha(BINARY),protocol_sha256=sha(ROOT/'docs/stable-model-protocol.md'),oracle_source_sha256=sha(ROOT/'bench/pilot_decimal_model.py'),nonfinite_encoding='null with explicit nonfinite_last_estep; raw logs retain NaN',scope='diagnostic only; production unchanged',failures=failures,components=results,endpoints=endpoints,fits=fits,raw_sha256={str(p.relative_to(ROOT)):sha(p) for p in OUT.iterdir() if p.is_file()},max_child_rss_kib=None if analyze_only else resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,analysis_only=analyze_only)
    def clean(value):
        if isinstance(value,float) and not math.isfinite(value):return None
        if isinstance(value,list):return [clean(x) for x in value]
        if isinstance(value,dict):return {k:clean(v) for k,v in value.items()}
        return value
    (ROOT/'bench/stable-model-results.json').write_text(json.dumps(clean(report),indent=2,allow_nan=False)+'\n')
    print(json.dumps(dict(component_count=len(results),failures=failures,oracle_excluded=sum(r['status']=='oracle_domain_excluded' for r in results),max_error=max(r.get('max_abs_error',0) for r in results),endpoint_max_ll_difference=max(abs(r['difference']) for r in endpoints),fits=fits)))

if __name__=='__main__':main()

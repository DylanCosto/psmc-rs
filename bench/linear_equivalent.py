#!/usr/bin/env python3
"""Prospective linear E-step controls, human validation and paired timings."""
import argparse,json,math,statistics,os
from pathlib import Path
from common import ROOT,save,sha256,timed_run,read_fasta,draw_bootstrap
from equivalent_analysis import read,grid,curve,difference
from equivalent_c_baseline import ARGS
from phase2_common import clean_env
from phase1_differential import compare_output
RAW=Path('work/linear-equivalent'); REPORT=Path('bench/linear-equivalent')
METRICS={'curve_max_log':1e-6,'theta_relative':1e-6,'rho_relative':1e-6,'ll_per_bin':1e-10}
def describe(rows):
    return {k:dict(median=statistics.median(r[k] for r in rows),p90=sorted(r[k] for r in rows)[math.ceil(.9*len(rows))-1]) for k in METRICS}
def sd_fraction(a,b,points,sd):
    return max(abs(x-y)/s if s else (0 if x==y else math.inf) for x,y,s in zip(curve(a,points),curve(b,points),sd))
def base():
    c=json.load(open('bench/equivalent-c-baseline.json')); data={}
    for label,ds in c['datasets'].items():
        runs={(r['build'],r['kind'],r.get('index')):r for r in c['runs'] if r['dataset']==label}
        points=grid(read(runs['o2','original',None]['output']))
        curves=[curve(read(runs['o2','bootstrap',i]['output']),points) for i in range(30)]
        sd=[statistics.stdev(row[j] for row in curves) for j in range(256)]
        rows=[]
        for kind,i in [('original',None)]+[('bootstrap',i) for i in range(30)]:
            a=read(runs['o2',kind,i]['output']);b=read(runs['fma',kind,i]['output'])
            inp=ds['original'] if i is None else ds['samples'][i]['path'];bins=sum(len(s) for _,s in read_fasta(inp))
            rows.append(dict(kind=kind,index=i,bins=bins,difference=difference(a,b,points,bins),sd_fraction=sd_fraction(a,b,points,sd),a_path=runs['o2',kind,i]['output'],b_path=runs['fma',kind,i]['output']))
        data[label]=dict(points=points,sd=sd,rows=rows)
    return c,data

def main():
    ap=argparse.ArgumentParser();ap.add_argument('stage',choices=['controls','validation','performance']);args=ap.parse_args();os.chdir(ROOT)
    c,data=base();RAW.mkdir(exist_ok=True)
    controls_path=Path(str(REPORT)+'-controls.json')
    if args.stage=='controls':
        out=dict(protocol_sha256=sha256('docs/linear-equivalent.md'),baseline_sha256=sha256('bench/equivalent-c-baseline.json'),datasets={},passed=True)
        for label,d in data.items():
            stats=describe([r['difference'] for r in d['rows']]);limits={k:{s:max(METRICS[k],4*v) for s,v in vals.items()} for k,vals in stats.items()}
            passed=max(r['sd_fraction'] for r in d['rows'])<=.1 and all(stats[k][s]<=limits[k][s] for k in stats for s in stats[k])
            out['datasets'][label]=dict(distribution=stats,limits=limits,max_sd_fraction=max(r['sd_fraction'] for r in d['rows']),passed=passed,rows=d['rows']);out['passed'] &= passed
        save(controls_path,out);print(json.dumps({k:{x:y for x,y in v.items() if x!='rows'} for k,v in out['datasets'].items()},indent=2));return
    controls=json.load(open(controls_path));assert controls['passed'];assert controls['protocol_sha256']==sha256('docs/linear-equivalent.md')
    raw=RAW/args.stage;raw.mkdir()
    binary='work/linear-equivalent/linear-tested';candidate_sha=sha256(binary)
    out=dict(status='running',binary_sha256=candidate_sha,protocol_sha256=controls['protocol_sha256'],runner_sha256=sha256(__file__),runs=[],datasets={})
    path=Path(str(REPORT)+'-'+args.stage+'.json')
    def run(cmd,tag):
        r=timed_run(cmd,ROOT/raw/tag,env=clean_env(),timeout=3600);assert r['exit_code']==0,r;r['tag']=tag;r['cpu_seconds']=r['user_seconds']+r['system_seconds'];out['runs'].append(r);save(path,out);print(tag,round(r['wall_seconds'],3),flush=True);return r
    def batch(bin,label,tag,mode='equivalent'):
        ds=c['datasets'][label];dest=raw/tag
        r=run(['taskset','-c','0-15',bin,'bootstrap','--mode',mode,'--workers','16','--memory-mib','16384','--replicates','30','--seed',str(ds['samples'][0]['seed']),'--output-dir',str(dest),*ARGS,ds['blocks']],tag+'-time')
        manifest=json.load(open(dest/'manifest.json'));assert manifest['failed_replicates']==manifest['nonfinite_replicates']==0
        records=read_fasta(ds['blocks'])
        for i in range(30):
            indices,draws=draw_bootstrap(records,ds['samples'][i]['seed']);assert indices==manifest['replicates'][i]['source_indices']
            actual=[json.loads(l) for l in (dest/f'replicate-{i:02}.draws.jsonl').read_text().splitlines()];assert actual[:-1]==[dict(event='bootstrap_draw',draw=j,**x) for j,x in enumerate(draws)]
        r['output_dir']=str(dest);return dest,r
    if args.stage=='validation':
        for label,d in data.items():
            original=run([binary,'--mode','equivalent',*ARGS,c['datasets'][label]['original']],label+'-original')['output']
            dest,_=batch(binary,label,label+'-batch')
            rows=[]
            for ref in d['rows']:
                i=ref['index'];p=original if i is None else dest/f'replicate-{i:02}.psmc';a=read(ref['a_path']);b=read(p)
                assert all(math.isfinite(x) and x>0 for x in b['lambdas']+[b['theta'],b['rho']]) and math.isfinite(b['ll'])
                delta=difference(a,b,d['points'],ref['bins']);fraction=sd_fraction(a,b,d['points'],d['sd'])
                rows.append(dict(index=i,path=str(p),sha256=sha256(p),difference=delta,sd_fraction=fraction,ridge_required=delta['curve_max_log']>max(.01,4*ref['difference']['curve_max_log'])))
            stats=describe([r['difference'] for r in rows]);limits=controls['datasets'][label]['limits']
            passed=all(stats[k][s]<=limits[k][s] for k in stats for s in stats[k]) and max(r['sd_fraction'] for r in rows)<=.1
            out['datasets'][label]=dict(rows=rows,distribution=stats,distribution_and_sd_passed=passed,max_sd_fraction=max(r['sd_fraction'] for r in rows));save(path,out)
            strict=run([binary,'--mode','strict',*ARGS,c['datasets'][label]['original']],label+'-strict')['output']
            compare_output(Path(d['rows'][0]['a_path']).read_bytes(),Path(strict).read_bytes())
        dest,_=batch(binary,'hg001','hg001-strict','strict')
        for i in range(30):compare_output(Path(data['hg001']['rows'][i+1]['a_path']).read_bytes(),(dest/f'replicate-{i:02}.psmc').read_bytes())
    else:
        for rep in range(4):
            for which in (['baseline','candidate'] if rep%2==0 else ['candidate','baseline']):
                bin='bin/psmc-rs-v0.5.1' if which=='baseline' else binary
                _,r=batch(bin,'hg001',f'{which}-{rep}');r.update(which=which,repeat=rep);save(path,out)
        out['summary']={w:{k:statistics.median(r[k] for r in out['runs'] if r['which']==w and r['repeat']>0) for k in ['wall_seconds','cpu_seconds','peak_rss_kib']} for w in ['baseline','candidate']}
        out['wall_reduction']=1-out['summary']['candidate']['wall_seconds']/out['summary']['baseline']['wall_seconds']
        out['faster_pairs']=sum(next(r for r in out['runs'] if r['which']=='candidate' and r['repeat']==rep)['wall_seconds']<next(r for r in out['runs'] if r['which']=='baseline' and r['repeat']==rep)['wall_seconds'] for rep in [1,2,3])
        out['passed']=out['wall_reduction']>=.05 and out['faster_pairs']>=2
    assert sha256(binary)==candidate_sha
    out['status']='completed';save(path,out)
if __name__=='__main__':main()

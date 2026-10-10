#!/usr/bin/env python3
"""Report full-fit differences without treating compiler variation as a guarantee."""
import bisect,itertools,json,math,os,statistics
from pathlib import Path
from common import ROOT,save,sha256
from phase1_differential import compare_output

def read(path):
    rounds=[]; current=None
    for line in Path(path).read_text().splitlines():
        p=line.split()
        if not p:continue
        if p[0]=='RD':
            current=dict(round=int(p[1]),times=[],lambdas=[]);rounds.append(current)
        elif current is not None:
            if p[0]=='LK':current['ll']=float(p[1])
            elif p[0]=='TR':current['theta'],current['rho']=map(float,p[1:3])
            elif p[0]=='RS':current['times'].append(float(p[2]));current['lambdas'].append(float(p[3]))
            elif p[0]=='PA':
                # PA retains nine decimal places; TR/RS retain only six.
                values=list(map(float,p[2:]));current['theta'],current['rho']=values[:2]
                widths=[]
                for term in p[1].split('+'):
                    count,width=map(int,term.split('*')) if '*' in term else (1,int(term))
                    widths.extend([width]*count)
                assert len(values)==3+len(widths), 'human baseline expects no explicit grid/divergence'
                current['lambdas']=[value for value,width in zip(values[3:],widths) for _ in range(width)]

    assert len(rounds)==31,path
    return rounds[-1]
def grid(model):
    a=model['times'][1];b=model['times'][-1]
    return [math.exp(math.log(a)+(i+.5)/256*math.log(b/a)) for i in range(256)]
def curve(model,points):
    return [math.log(model['lambdas'][max(0,bisect.bisect_right(model['times'],t)-1)]) for t in points]
def difference(a,b,points,bins):
    ac=curve(a,points);bc=curve(b,points);d=[abs(x-y) for x,y in zip(ac,bc)]
    return dict(curve_max_log=max(d),curve_rms_log=math.sqrt(statistics.mean(x*x for x in d)),
        interval_max_log=max(abs(math.log(x/y)) for x,y in zip(a['lambdas'],b['lambdas'])),
        theta_relative=abs(a['theta']-b['theta'])/abs(a['theta']),rho_relative=abs(a['rho']-b['rho'])/abs(a['rho']),
        ll_absolute=abs(a['ll']-b['ll']),ll_per_bin=abs(a['ll']-b['ll'])/bins,
        endpoint_relative=abs(a['times'][-1]-b['times'][-1])/a['times'][-1])
def main():
    os.chdir(ROOT)
    c=json.load(open('bench/equivalent-c-baseline.json'));v=json.load(open('bench/equivalent-validation.json'))
    assert c['status']==v['status']=='completed'
    report=dict(status='completed',runner_sha256=sha256(__file__),reports={p:sha256(p) for p in ['bench/equivalent-c-baseline.json','bench/equivalent-validation.json']},datasets={},strict_exact_outputs=0)
    for label,data in c['datasets'].items():
        cr={(r['build'],r['kind'],r.get('index')):r for r in c['runs'] if r['dataset']==label}
        vr={}
        for r in v['runs']:
            if r['dataset']!=label:continue
            if r['kind']=='original':vr[(r['mode'],'original',None)]=r['output']
            else:
                for output in r['outputs']:vr[(r['mode'],'bootstrap',output['index'])]=output['path']
        original=read(cr['o2','original',None]['output']);points=grid(original)
        bootstrap_curves=[curve(read(cr['o2','bootstrap',i]['output']),points) for i in range(30)]
        sd=[statistics.stdev(row[j] for row in bootstrap_curves) for j in range(len(points))]
        ds=dict(grid=points,bootstrap_log_curve_sd=sd,comparisons=[])
        for kind,index in [('original',None)]+[('bootstrap',i) for i in range(30)]:
            models={build:read(cr[build,kind,index]['output']) for build in c['selected_builds']}
            ref=models['o2'];equiv=read(vr['equivalent',kind,index])
            for name,model in [*models.items(),('equivalent',equiv)]:
                assert all(math.isfinite(x) and x>0 for x in model['lambdas']+[model['theta'],model['rho']]), (label,kind,index,name,'nonfinite/nonpositive full fit; no equivalence claim')
                assert math.isfinite(model['ll']), (label,kind,index,name,'nonfinite likelihood')
            a=Path(cr['o2',kind,index]['output']).read_bytes();b=Path(vr['strict',kind,index]).read_bytes()
            compare_output(a,b);report['strict_exact_outputs']+=1
            bins=sum(len(s) for _,s in __import__('common').read_fasta(data['original'] if kind=='original' else data['samples'][index]['path']))
            pairs=[difference(models[x],models[y],points,bins) for x,y in itertools.combinations(models,2)]
            envelope={k:max(row[k] for row in pairs) for k in pairs[0]}
            delta=difference(ref,equiv,points,bins)
            err=[abs(a-b) for a,b in zip(curve(ref,points),curve(equiv,points))]
            ratios=[e/s if s>0 else (0.0 if e==0 else None) for e,s in zip(err,sd)]
            within=all(delta[k]<=envelope[k] for k in ['curve_max_log','theta_relative','rho_relative','ll_per_bin'])
            screen=delta['curve_max_log']<=.01 and delta['theta_relative']<=.001 and delta['rho_relative']<=.001 and delta['ll_per_bin']<=1e-6
            ds['comparisons'].append(dict(kind=kind,index=index,compiler_envelope=envelope,equivalent_difference=delta,
                within_compiler_envelope=within,exploratory_screen=screen,max_bootstrap_sd_fraction=max(ratios) if all(x is not None for x in ratios) else None,
                below_one_percent_bootstrap_sd=all(x is not None and x<=.01 for x in ratios)))
        ds['summary']=dict(compiler_envelope_pass=sum(r['within_compiler_envelope'] for r in ds['comparisons']),exploratory_screen_pass=sum(r['exploratory_screen'] for r in ds['comparisons']),bootstrap_spread_screen_pass=sum(r['below_one_percent_bootstrap_sd'] for r in ds['comparisons']),cases=len(ds['comparisons']),
            max_equivalent_differences={k:max(r['equivalent_difference'][k] for r in ds['comparisons']) for k in ds['comparisons'][0]['equivalent_difference']},
            max_compiler_envelopes={k:max(r['compiler_envelope'][k] for r in ds['comparisons']) for k in ds['comparisons'][0]['compiler_envelope']})
        report['datasets'][label]=ds
    report['interpretation']='Compiler spread is empirical sensitivity, not a bound on valid inference. Use nine-decimal PA parameters for theta/rho/lambda, six-decimal RS times and LK likelihood. Printed precision limits zero-difference claims. Common-grid curves are piecewise constant log lambda on 256 logarithmically spaced interval-midpoint times from the original O2 fit. Interval-index error is also reported. LL is the legacy reported E-step likelihood, preceding the last M-step. No population-level validation is claimed.'
    save('bench/equivalent-analysis.json',report)
    print(json.dumps({k:d['summary'] for k,d in report['datasets'].items()},indent=2))
if __name__=='__main__':main()

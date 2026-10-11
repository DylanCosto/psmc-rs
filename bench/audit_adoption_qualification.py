#!/usr/bin/env python3
"""Independent integrity and numerical audit of the frozen adoption campaign."""
import bisect,hashlib,json,math,statistics,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'work/adoption-qualification'
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text())
def relative(value):
    if isinstance(value,str):return value.replace(str(ROOT)+'/','')
    if isinstance(value,list):return [relative(v) for v in value]
    if isinstance(value,dict):return {k:relative(v) for k,v in value.items()}
    return value

def check_rounds(path):
    text=path.read_text();rounds=[int(l.split()[1]) for l in text.splitlines() if l.startswith('RD\t')]
    assert rounds==list(range(31)),path
    assert sum(l=='//' for l in text.splitlines())==31,path
    return text

def independent_curve(text,band):
    pa=[l.split() for l in text.splitlines() if l.startswith('PA\t')][-1]
    theta,rho,mt,*lambdas=map(float,pa[2:]);n0=theta/(4*2.5e-8*100)
    widths=[]
    for term in pa[1].split('+'):
        factors=list(map(int,term.split('*')))
        widths.extend([factors[-1]]*(factors[0] if len(factors)==2 else 1))
    n=sum(widths);beta=math.log1p(mt/.1)/(n-1);indices=[0]
    for w in widths[:-1]:indices.append(indices[-1]+w)
    starts=[.1*math.expm1(beta*k)*2*n0 for k in indices]
    lo,hi=band
    return [math.log(n0*lambdas[max(0,bisect.bisect_right(starts,lo*(hi/lo)**(i/128))-1)]) for i in range(128)]

def main():
    report=read(OUT/'report.json');frozen=report['frozen'];commit=frozen['commit']
    assert not (OUT/'stop.json').exists() and not (OUT/'failure.json').exists()
    for name,digest in frozen['binary_hashes'].items():assert sha(OUT/'binaries'/name)==digest
    for path,digest in frozen['input_sha256'].items():assert sha(ROOT/path)==digest
    for path,key in [('docs/adoption-qualification-protocol.md','protocol_sha256'),('bench/adoption_qualification.py','runner_sha256')]:
        assert sha(ROOT/path)==frozen[key]
        assert hashlib.sha256(subprocess.check_output(['git','show',f'{commit}:{path}'],cwd=ROOT)).hexdigest()==frozen[key]
    resources=[json.loads(l) for l in (OUT/'resources.jsonl').read_text().splitlines()]
    assert min(r['available_ram'] for r in resources)>=4*1024**3
    assert min(r['free_disk'] for r in resources)>=25*1024**3
    assert max(r['campaign_bytes'] for r in resources)<=2*1024**3
    for name,run in report['runs'].items():
        assert run==read(OUT/(name+'.done.json')) and run['exit_code']==0
        assert sha(OUT/(name+'.out'))==run['output_sha256']
        assert sha(OUT/(name+'.stderr'))==run['stderr_sha256']
        time_text=(OUT/(name+'.time')).read_text()
        assert 'Exit status: 0' in time_text
        assert str(OUT/'binaries/rust') in run['command'] or str(OUT/'binaries/c-o2') in run['command'] or str(OUT/'binaries/c-fma') in run['command']
        if name.startswith('bootstrap-'):
            assert '--workers' in run['command'] and run['command'][run['command'].index('--workers')+1]=='16'
            assert run['command'][run['command'].index('--memory-mib')+1]=='8192'
    exact=[]
    for panel in report['additional_patterns']:
        label=panel['dataset']+'-'+panel['pattern'].replace('*','x')
        texts={m:check_rounds(OUT/(label+'-'+m+'.out')) for m in ['c-o2','c-fma','strict','equivalent']}
        remove=lambda t:'\n'.join(l for l in t.splitlines() if not l.startswith('MM\tVersion:'))
        value=remove(texts['c-o2'])==remove(texts['strict']);assert value==panel['strict_c_exact'];exact.append(value)
    bands={'recent':(1000,5000),'primary_early':(5000,20000),'primary_late':(20000,80000),'ancient':(80000,200000)}
    all_curves={band:{mode:[] for mode in ['strict','equivalent']} for band in bands}
    hashes={};stats_totals={mode:{'model_updates':0,'structured_fallbacks':0} for mode in ['strict','equivalent']}
    for mode in ['strict','equivalent']:
        manifest=read(OUT/mode/'manifest.json');assert manifest['failed_replicates']==0 and len(manifest['replicates'])==30
        assert manifest['workers']<=16 and manifest['memory_mib']==8192 and manifest['mode']==mode
        for i in range(30):
            base=OUT/mode/f'replicate-{i:02}'
            marker=base.with_suffix('.complete').read_text().splitlines();assert marker[0]=='PSMC-COMPLETE-1' and len(marker)==5
            for suffix,line in zip(['psmc','stats.json','draws.jsonl'],marker[2:]):
                path=Path(str(base)+'.'+suffix);digest=sha(path);assert line==digest+' '+suffix;hashes[str(path.relative_to(ROOT))]=digest
            text=check_rounds(base.with_suffix('.psmc'))
            assert sha(base.with_suffix('.psmc'))==report['bootstrap_pairs'][i]['fits'][mode]['sha256']
            stat=read(Path(str(base)+'.stats.json'));assert stat==report['bootstrap_pairs'][i]['stats'][mode]
            assert marker[1]==str(stat['nonfinite_output']).lower()
            for key in stats_totals[mode]:stats_totals[mode][key]+=stat[key]
            for band,limits in bands.items():
                values=independent_curve(text,limits);reported=report['bootstrap_pairs'][i]['fits'][mode]['curves'][band]
                assert all(abs(a-b)<1e-12 for a,b in zip(values,reported));all_curves[band][mode].append(values)
    maxima={}
    for band,curves in all_curves.items():
        sd=[statistics.stdev(row[k] for row in curves['strict']) for k in range(128)]
        ratios=[abs(a[k]-b[k])/sd[k] for a,b in zip(curves['strict'],curves['equivalent']) for k in range(128) if sd[k]>0]
        maximum=max(ratios) if ratios else None;maxima[band]=maximum
        if maximum is not None:assert abs(maximum-report['uncertainty'][band]['max_ratio'])<1e-10
    audit=dict(integrity_passed=True,strict_c_exact=all(exact),whole_genome_pairs=30,replicate_artifact_hashes=hashes,
        uncertainty_max_ratios=maxima,stats_totals=stats_totals,diagnostic_required=report['diagnostic_required'],
        min_available_ram_gib=min(r['available_ram'] for r in resources)/1024**3,
        min_free_disk_gib=min(r['free_disk'] for r in resources)/1024**3,
        max_campaign_gib=max(r['campaign_bytes'] for r in resources)/1024**3,
        raw_report_sha256=sha(OUT/'report.json'),protocol_commit=commit)
    (ROOT/'bench/adoption-qualification-results.json').write_text(json.dumps(relative(report),indent=2,allow_nan=False)+'\n')
    (ROOT/'bench/adoption-qualification-audit.json').write_text(json.dumps(audit,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:v for k,v in audit.items() if k!='replicate_artifact_hashes'},indent=2))
if __name__=='__main__':main()

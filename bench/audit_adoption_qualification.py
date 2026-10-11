#!/usr/bin/env python3
"""Independent integrity and numerical audit of the frozen adoption campaign."""
import bisect,hashlib,json,math,statistics,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'work/adoption-qualification'
BANDS={'recent':(1000,5000),'primary_early':(5000,20000),'primary_late':(20000,80000),'ancient':(80000,200000)}
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text())
def relative(value):
    if isinstance(value,str):return value.replace(str(ROOT)+'/','')
    if isinstance(value,list):return [relative(v) for v in value]
    if isinstance(value,dict):return {k:relative(v) for k,v in value.items()}
    return value

def sequences(path):
    records=[]
    for line in path.read_text().splitlines():
        if line.startswith('>'):records.append([line[1:].split()[0], []])
        else:records[-1][1].append(line.strip())
    return [(name, ''.join(parts)) for name,parts in records]

def verify_split():
    original=sequences(ROOT/'work/hg001-genome/HG001_GRCh38_autosomes.psmcfa')
    blocks=sequences(OUT/'blocks.psmcfa');expected=[]
    for _,sequence in original:
        start=0
        while start<len(sequence):
            end=len(sequence) if len(sequence)-start<75000 else start+50000
            expected.append(sequence[start:end]);start=end
    assert [sequence for _,sequence in blocks]==expected
    assert sum(map(len,expected))==28750027 and len(original)==22
    return list(map(len,expected))

def verify_draws(path, lengths, seed, replicate):
    records=[json.loads(line) for line in path.read_text().splitlines()]
    state=((seed & 0xffffffff)<<16)|0x330e;total=0;selected=[];target=sum(lengths)
    for i,record in enumerate(records[:-1]):
        state=(state*0x5deece66d+0xb)&((1<<48)-1)
        index=int(len(lengths)*state/(1<<48));length=lengths[index]
        before=total;remaining=target-total;excess=total+length-target
        accepted=excess<=0 or (remaining>0 and excess<remaining)
        stop=remaining>=0 and excess>=0
        if accepted:total+=length;selected.append(index)
        assert record==dict(event='bootstrap_draw',draw=i,source_index=index,length=length,
            accepted=accepted,before_length=before,after_length=total,target_length=target,stop=stop)
        assert stop==(i==len(records)-2)
    assert records[-1]==dict(event='bootstrap_end',accepted_sequences=len(selected),length=total,target_length=target)
    assert selected==replicate['source_indices'] and total==replicate['length']

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

def independent_comparison(a,b,bins):
    bands={}
    for name,limits in BANDS.items():
        diffs=[abs(x-y) for x,y in zip(independent_curve(a,limits),independent_curve(b,limits))]
        bands[name]=dict(rms=math.sqrt(sum(v*v for v in diffs)/len(diffs)),max=max(diffs))
    def params(t):return list(map(float,[l.split()[2:] for l in t.splitlines() if l.startswith('PA\t')][-1]))
    pa,pb=params(a),params(b)
    assert all(math.isfinite(v) and v>0 for v in pa+pb)
    def lk(t):return float([l.split()[1] for l in t.splitlines() if l.startswith('LK\t')][-1])
    def finite(t):
        return all(math.isfinite(float(v)) for l in t.splitlines() if l.startswith(('LK\t','TR\t','RS\t','PA\t'))
                   for v in (l.split()[2:] if l.startswith('PA\t') else l.split()[1:]))
    result=dict(bands=bands,theta_relative=abs(pb[0]/pa[0]-1),rho_relative=abs(pb[1]/pa[1]-1),legacy_lk_per_bin=abs(lk(a)-lk(b))/bins)
    result['exploratory_screen']=finite(a) and finite(b) and all(bands[k]['rms']<=.01 for k in ['primary_early','primary_late']) and result['theta_relative']<=.001 and result['rho_relative']<=.001 and result['legacy_lk_per_bin']<=1e-6
    return result

def same(a,b):
    if isinstance(a,dict):
        assert a.keys()==b.keys()
        for key in a:same(a[key],b[key])
    elif isinstance(a,float):assert math.isclose(a,b,rel_tol=1e-12,abs_tol=1e-14),(a,b)
    else:assert a==b,(a,b)

def main():
    report=read(OUT/'report.json');frozen=report['frozen'];commit=frozen['commit']
    assert not (OUT/'stop.json').exists()
    continuation=None
    if (OUT/'failure.json').exists():
        failure=read(OUT/'failure.json');continuation=read(OUT/'continuation.json')
        assert failure['error']=="AssertionError('preflight resource floor')"
        assert continuation['status']=='completed' and continuation['frozen_commit']==commit
        assert sha(OUT/'failure.json')==continuation['preserved_failure_sha256']
        assert sha(OUT/'strict/manifest.json')==continuation['preserved_strict_manifest_sha256']
        source=subprocess.check_output(['git','show',f"{continuation['source_commit']}:bench/continue_adoption_qualification.py"],cwd=ROOT)
        assert hashlib.sha256(source).hexdigest()==continuation['continuation_sha256']
        assert sorted(s['name'] for s in continuation['stages'])==sorted(name for name in report['runs'] if name not in ['split','bootstrap-strict'])
        assert all(s['available_ram']>=14*1024**3 and s['free_disk']>=25*1024**3 for s in continuation['stages'])
    for name,digest in frozen['binary_hashes'].items():assert sha(OUT/'binaries'/name)==digest
    for path,digest in frozen['input_sha256'].items():assert sha(ROOT/path)==digest
    for path,key in [('docs/adoption-qualification-protocol.md','protocol_sha256'),('bench/adoption_qualification.py','runner_sha256')]:
        assert sha(ROOT/path)==frozen[key]
        assert hashlib.sha256(subprocess.check_output(['git','show',f'{commit}:{path}'],cwd=ROOT)).hexdigest()==frozen[key]
    for path in ['bench/known_truth.py','bench/known_truth_200mb.py','bench/hg001_genome_run.py']:
        assert (ROOT/path).read_bytes()==subprocess.check_output(['git','show',f'{commit}:{path}'],cwd=ROOT)
    assert set(report['runs'])=={'split','bootstrap-strict','bootstrap-equivalent'}|{
        f'{data}-{pattern}-{mode}' for data in ['hg001-chr22','hg002-chr1']
        for pattern in ['4+5x3+4','8+8+8+8'] for mode in ['c-o2','c-fma','strict','equivalent']}
    lengths=verify_split()
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
        parsed={}
        for line in time_text.splitlines():
            for prefix,key in [('User time (seconds):','user_seconds'),('System time (seconds):','system_seconds'),('Maximum resident set size (kbytes):','peak_rss_kib')]:
                if line.strip().startswith(prefix):parsed[key]=float(line.strip()[len(prefix):])
        assert parsed==run['timing'] and 0<parsed['peak_rss_kib']<12*1024**2
        assert run['wall_seconds']>0
        assert str(OUT/'binaries/rust') in run['command'] or str(OUT/'binaries/c-o2') in run['command'] or str(OUT/'binaries/c-fma') in run['command']
        if name.startswith('bootstrap-'):
            assert '--workers' in run['command'] and run['command'][run['command'].index('--workers')+1]=='16'
            assert run['command'][run['command'].index('--memory-mib')+1]=='8192'
        elif name!='split':
            command=run['command']
            if name.endswith(('c-o2','c-fma')):
                assert command[:2]==['/usr/bin/taskset','-c'] and command[2].isdigit()
            else:
                assert command[command.index('--record-workers')+1]=='4'
                assert command[command.index('--memory-mib')+1]=='4096'
    exact=[];additional_stats={}
    for panel in report['additional_patterns']:
        label=panel['dataset']+'-'+panel['pattern'].replace('*','x')
        texts={m:check_rounds(OUT/(label+'-'+m+'.out')) for m in ['c-o2','c-fma','strict','equivalent']}
        def numerical_bytes(mode):
            return b''.join(line for line in (OUT/(label+'-'+mode+'.out')).read_bytes().splitlines(keepends=True) if not line.startswith(b'MM\tVersion:'))
        value=numerical_bytes('c-o2')==numerical_bytes('strict');assert value==panel['strict_c_exact'];exact.append(value)
        input_path=ROOT/('work/hg001-genome/chromosomes/chr22.psmcfa' if panel['dataset']=='hg001-chr22' else 'work/adoption-input/HG002_GRCh38_chr1.psmcfa')
        bins=sum(len(sequence) for _,sequence in sequences(input_path))
        control=independent_comparison(texts['c-o2'],texts['c-fma'],bins)
        same(control,panel['compiler_control'])
        same(independent_comparison(texts['strict'],texts['equivalent'],bins),panel['equivalent_comparison'])
        assert control['exploratory_screen']==panel['screen_calibrated']
        for mode in ['strict','equivalent']:
            path=OUT/(label+'-'+mode+'.stats.json');stat=read(path)
            assert stat['mode']==mode and stat['iterations']==30 and stat['seed']==20261011
            additional_stats[label+'-'+mode]=dict(sha256=sha(path),stats=stat)
    bands=BANDS
    all_curves={band:{mode:[] for mode in ['strict','equivalent']} for band in bands}
    hashes={};traces={};texts_by_mode={};stats_totals={mode:{'model_updates':0,'structured_fallbacks':0} for mode in ['strict','equivalent']}
    for mode in ['strict','equivalent']:
        texts_by_mode[mode]=[]
        manifest=read(OUT/mode/'manifest.json');assert manifest['failed_replicates']==0 and len(manifest['replicates'])==30
        assert manifest['workers']<=16 and manifest['memory_mib']==8192 and manifest['mode']==mode
        assert manifest['seed']==20261011 and manifest['states']==64 and manifest['iterations']==30
        assert manifest['requested_workers']==16 and manifest['backend']=='cpu'
        assert manifest['input_bytes']+manifest['estimated_metadata_bytes']+manifest['workers']*manifest['estimated_worker_bytes']<=8192*1024**2
        for i in range(30):
            base=OUT/mode/f'replicate-{i:02}'
            marker=base.with_suffix('.complete').read_text().splitlines();assert marker[0]=='PSMC-COMPLETE-1' and len(marker)==5
            for suffix,line in zip(['psmc','stats.json','draws.jsonl'],marker[2:]):
                path=Path(str(base)+'.'+suffix);digest=sha(path);assert line==digest+' '+suffix;hashes[str(path.relative_to(ROOT))]=digest
            text=check_rounds(base.with_suffix('.psmc'))
            texts_by_mode[mode].append(text)
            assert sha(base.with_suffix('.psmc'))==report['bootstrap_pairs'][i]['fits'][mode]['sha256']
            stat=read(Path(str(base)+'.stats.json'));assert stat==report['bootstrap_pairs'][i]['stats'][mode]
            assert marker[1]==str(stat['nonfinite_output']).lower()
            replicate=manifest['replicates'][i]
            assert replicate['index']==i and replicate['seed']==20261011+i
            assert stat['seed']==20261011+i and stat['mode']==mode and stat['iterations']==30
            trace=Path(str(base)+'.draws.jsonl')
            verify_draws(trace,lengths,20261011+i,replicate)
            if mode=='strict':traces[i]=sha(trace)
            assert sha(trace)==traces[i]==report['bootstrap_pairs'][i]['trace_sha256']
            for key in stats_totals[mode]:stats_totals[mode][key]+=stat[key]
            for band,limits in bands.items():
                values=independent_curve(text,limits);reported=report['bootstrap_pairs'][i]['fits'][mode]['curves'][band]
                assert all(abs(a-b)<1e-12 for a,b in zip(values,reported));all_curves[band][mode].append(values)
    flagged=set()
    for i,pair in enumerate(report['bootstrap_pairs']):
        comparison=independent_comparison(texts_by_mode['strict'][i],texts_by_mode['equivalent'][i],pair['fits']['strict']['bins'])
        same(comparison,pair['comparison'])
        if not comparison['exploratory_screen']:flagged.add(i)
    maxima={}
    for band,curves in all_curves.items():
        sd=[statistics.stdev(row[k] for row in curves['strict']) for k in range(128)]
        ratios=[abs(a[k]-b[k])/sd[k] for a,b in zip(curves['strict'],curves['equivalent']) for k in range(128) if sd[k]>0]
        maximum=max(ratios) if ratios else None;maxima[band]=maximum
        if maximum is not None:assert abs(maximum-report['uncertainty'][band]['max_ratio'])<1e-10
        if band.startswith('primary'):
            for i,(a,b) in enumerate(zip(curves['strict'],curves['equivalent'])):
                values=[abs(a[k]-b[k])/sd[k] for k in range(128) if sd[k]>0]
                if not values or max(values)>.1:flagged.add(i)
    assert sorted(flagged)==report['diagnostic_required']
    audit=dict(integrity_passed=True,strict_c_exact=all(exact),whole_genome_pairs=30,replicate_artifact_hashes=hashes,
        split_boundaries_and_content_verified=True,independent_rng_draws_verified=True,
        independent_screens_verified=True,additional_stats=additional_stats,
        preserved_preflight_pause=continuation,
        uncertainty_max_ratios=maxima,stats_totals=stats_totals,diagnostic_required=report['diagnostic_required'],
        min_available_ram_gib=min(r['available_ram'] for r in resources)/1024**3,
        min_free_disk_gib=min(r['free_disk'] for r in resources)/1024**3,
        max_campaign_gib=max(r['campaign_bytes'] for r in resources)/1024**3,
        raw_report_sha256=sha(OUT/'report.json'),protocol_commit=commit)
    (ROOT/'bench/adoption-qualification-results.json').write_text(json.dumps(relative(report),indent=2,allow_nan=False)+'\n')
    (ROOT/'bench/adoption-qualification-audit.json').write_text(json.dumps(audit,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:v for k,v in audit.items() if k!='replicate_artifact_hashes'},indent=2))
if __name__=='__main__':main()

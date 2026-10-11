#!/usr/bin/env python3
"""Verify the linear milestone evidence and every declared numerical/performance gate."""
import json,re
from pathlib import Path
from common import ROOT,save,sha256,read_fasta

def main():
    import os;os.chdir(ROOT)
    controls=json.load(open('bench/linear-equivalent-controls.json'));v=json.load(open('bench/linear-equivalent-validation.json'));p=json.load(open('bench/linear-equivalent-performance.json'))
    assert controls['passed'] and v['status']==p['status']=='completed' and p['passed']
    assert v['binary_sha256']==p['binary_sha256']==sha256('work/linear-equivalent/linear-tested')
    assert v['protocol_sha256']==p['protocol_sha256']==controls['protocol_sha256']==sha256('docs/linear-equivalent.md')
    baseline=json.load(open('bench/equivalent-c-baseline.json'));out=dict(status='completed',passed=True,base_commit='9aff5a5',binary_sha256=v['binary_sha256'],protocol_sha256=v['protocol_sha256'],reference_commit='82fa2ada83ee463fe1251b562ae3d60e82d7ad6a',datasets={},tests={},performance=p['summary'],wall_reduction=p['wall_reduction'])
    for name,d in v['datasets'].items():
        assert d['distribution_and_sd_passed'];ridges=[]
        for row in d['rows']:
            assert sha256(row['path'])==row['sha256'];text=Path(row['path']).read_text();assert len(re.findall(r'^QU\t',text,re.M))==31 and not re.search(r'^QD\t',text,re.M)
            if row['ridge_required']:
                i=row['index'];r=json.load(open(f'bench/linear-equivalent-ridge-{name}-{i}.json'));assert all(sha256(path)==h for path,h in r['inputs'].items())
                ds=baseline['datasets'][name];inp=ds['original'] if i is None else ds['samples'][i]['path'];bins=sum(len(s) for _,s in read_fasta(inp));e=r['rows'][0];deltas={k:abs(e[k])/bins for k in ['ll_delta','q_on_strict_counts_delta','q_on_equivalent_counts_delta']};assert max(deltas.values())<=1e-8
                ridges.append(dict(index=i,deltas_per_bin=deltas,max_lambda_slice_ll_change=max(abs(x['ll_delta_from_base']) for x in r['rows'][1:])))
        stats=[json.load(open(Path('work/linear-equivalent/validation')/(name+'-batch')/f'replicate-{i:02}.stats.json')) for i in range(30)]
        out['datasets'][name]=dict(fits=len(d['rows']),max_bootstrap_sd_fraction=d['max_sd_fraction'],distribution=d['distribution'],ridge_diagnostics=ridges,optimizer_callbacks=sum(s['model_updates'] for s in stats),structured_fallbacks=sum(s['structured_fallbacks'] for s in stats))
    for label in ['release-tests','debug-tests']:
        path=f'work/linear-equivalent/{label}.log';t=Path(path).read_text();assert 'FAILED' not in t and 'error:' not in t
        rows=re.findall(r'test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored',t);assert rows
        out['tests'][label]=dict(passed=sum(int(x[0]) for x in rows),failed=sum(int(x[1]) for x in rows),ignored=sum(int(x[2]) for x in rows),log_sha256=sha256(path))
    assert 'error:' not in Path('work/linear-equivalent/all-features.log').read_text()
    out['not_run']=['CUDA hardware (four ignored tests)','ARM/NEON hardware','hosted CI']
    out['limits']='Two public chromosome panels and two C compiler builds. Engineering acceptance, not general scientific equivalence. Performance comparison is to v0.5.1 equivalent; historical C timing is not a contemporaneous paired baseline. Scheduling is a separate milestone.'
    out['sources']={str(f):sha256(f) for f in Path('crates').rglob('*.rs')}
    out['reports']={str(f):sha256(f) for f in Path('bench').glob('linear-equivalent-*.json') if not f.name.endswith('audit.json')}
    save('bench/linear-equivalent-audit.json',out);print(json.dumps(out,indent=2))
if __name__=='__main__':main()

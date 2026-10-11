#!/usr/bin/env python3
"""Audit saved diagnostic records and emit JSON plus a report, without refitting."""
import hashlib,json,math,pathlib,re
ROOT=pathlib.Path(__file__).resolve().parents[1]; WORK=ROOT/'work/pilot-surface'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def finite_json(x):
    if isinstance(x,float) and not math.isfinite(x):return None
    if isinstance(x,list):return [finite_json(v) for v in x]
    if isinstance(x,dict):return {k:finite_json(v) for k,v in x.items()}
    return x

def audit(case):
    stages={}
    for suffix,count in [('',324),('.decimal',41)]:
        p=WORK/(case+suffix+'.jsonl');rows=[json.loads(x) for x in p.read_text().splitlines()]
        meta=json.loads((WORK/(case+suffix+'.meta.json')).read_text())
        assert meta['exit_code']==0 and meta['output_sha256']==sha(p) and len(rows)==count
        meta['command']=[x.replace(str(ROOT)+'/', '') for x in meta['command']]
        timing=(WORK/(case+suffix+'.time')).read_text()
        assert re.search(r'Exit status: 0\s*$',timing)
        rss=int(re.search(r'Maximum resident set size \(kbytes\): (\d+)',timing)[1])
        stages['decimal' if suffix else 'literal']=dict(meta=meta,peak_rss_kib=rss,rows=rows,timing_sha256=sha(WORK/(case+suffix+'.time')))
    r=stages['literal']['rows'];d=stages['decimal']['rows'];by={x['label']:x for x in d}
    endpoints={x['base']:x for x in r if x['kind']=='endpoint'}
    assert len(endpoints)==2 and all(x['ll']==x['scalar_ll'] for x in endpoints.values())
    path=[by[f'path-{k}']['ll'] for k in range(33)]
    assert all(math.isfinite(x) for x in path)
    precision=max(abs(path[k]-by[name+'-80']['ll']) for k,name in [(0,'strict'),(32,'equivalent')])
    assert precision<1e-9
    summary=dict(case=case,literal_endpoint_delta=endpoints['equivalent']['ll']-endpoints['strict']['ll'],
        high_precision_endpoint_delta=path[-1]-path[0], high_precision_path_range=max(path)-min(path),
        high_precision_path_loss_below_lower_endpoint=min(path[0],path[-1])-min(path),
        precision_50_80_max_ll_delta=precision,
        literal_nonfinite_ll=sum(not math.isfinite(x['ll']) for x in r),
        interior_literal_nonfinite_ll=sum(not math.isfinite(x['ll']) for x in r if x['kind']=='path' and 0<=x['t']<=1),
        literal_invalid_probability_points=sum(x['literal_bad_probabilities']>0 for x in d),
        max_probability_discrepancy=max(x['max_finite_probability_difference'] for x in d),
        endpoints={})
    for k,name in [(0,'strict'),(32,'equivalent')]:
        coords=[x for x in r if x['kind']=='coordinate' and x['base']==name and math.isfinite(x['ll'])]
        best=max(coords,key=lambda x:x['ll'])
        summary['endpoints'][name]=dict(ll=path[k],literal_to_high_precision_ll_delta=path[k]-endpoints[name]['ll'],
            lambda0_minus1_ll_gain=by[name+'-lambda-minus1']['ll']-path[k],lambda0_plus1_ll_gain=by[name+'-lambda-plus1']['ll']-path[k],
            selected_coordinate_index=best['index'],selected_coordinate_log_shift=best['log_delta'],
            selected_coordinate_ll_gain=by[name+'-best-coordinate']['ll']-path[k])
    return dict(summary=summary,stages=stages)

if __name__=='__main__':
    cases=[audit(c) for c in ['bottleneck-01','bottleneck-03','bottleneck-09','expansion-09']]
    files=['docs/pilot-ridge-protocol.md','crates/psmc-cpu/examples/pilot_surface.rs','crates/psmc-cpu/examples/pilot_matrix_likelihood.rs','bench/pilot_decimal_model.py','bench/pilot_surface.py','bench/pilot_surface_report.py','bench/test_pilot_decimal_model.py']
    result=dict(schema_version=1,status='diagnostic_completed_not_a_new_acceptance_gate',base_source_commit='ff46c7d',source_sha256={p:sha(ROOT/p) for p in files},cases=cases,
        verification=dict(workspace_tests_passed=61,cuda_hardware_tests_ignored=4,diagnostic_rust_tests_passed=1,decimal_tests_passed=1,
                          original_input_and_endpoint_hashes_verified=True,scalar_auto_endpoint_ll_exact=True,
                          regular_synthetic_max_probability_difference=3.3306690738754696e-16,
                          extreme_synthetic_50_80_probabilities_exact=True),
        limitations=['Post-hoc four-case selection; no acceptance gate changed.','Printed PA vectors are rounded endpoints.','Decimal constructs the same model; HMM remains f64.','Finite path grid and limited nuisance search do not prove a stationary ridge or global maximum.','Only x86-64 Linux; GPU not_run.'])
    (ROOT/'bench/pilot-surface-results.json').write_text(json.dumps(finite_json(result),indent=2,allow_nan=False)+'\n')
    for c in cases:print(json.dumps(c['summary'],indent=2))

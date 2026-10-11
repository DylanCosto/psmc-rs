#!/usr/bin/env python3
"""Reassess the existing panel descriptively; no post-hoc scientific pass gate."""
import json,statistics
from pathlib import Path
from common import ROOT,save,sha256

def main():
    source=ROOT/'bench/equivalent-analysis.json';r=json.loads(source.read_text())
    out=dict(status='completed',runner_sha256=sha256(__file__),source_sha256=sha256(source),datasets={})
    for name,data in r['datasets'].items():
        rows=data['comparisons'];a=[x['equivalent_difference']['curve_max_log'] for x in rows];b=[x['compiler_envelope']['curve_max_log'] for x in rows]
        def describe(v):
            s=sorted(v);return dict(median=statistics.median(v),mean=statistics.mean(v),p90_nearest_rank=s[27],maximum=max(v))
        out['datasets'][name]=dict(structured_vs_strict=describe(a),c_fma_vs_c_o2=describe(b),structured_greater_than_c=sum(x>y for x,y in zip(a,b)),cases=len(rows),c_curve_screen_failures=[dict(index=x['index'],kind=x['kind'],difference=x['compiler_envelope']['curve_max_log']) for x in rows if x['compiler_envelope']['curve_max_log']>.01],structured_curve_screen_failures=[x['index'] for x in rows if x['equivalent_difference']['curve_max_log']>.01],maximum_bootstrap_sd_fraction=max(x['max_bootstrap_sd_fraction'] for x in rows))
        out['datasets'][name]['metric_distributions']={metric:dict(structured_vs_strict=describe([row['equivalent_difference'][metric] for row in rows]),c_fma_vs_c_o2=describe([row['compiler_envelope'][metric] for row in rows])) for metric in rows[0]['equivalent_difference']}
    raw=ROOT/'work/equivalent-followup/ridge.jsonl';ridge=[json.loads(l) for l in raw.read_text().splitlines()]
    inputs=['work/equivalent/c-baseline/hg001-sample-13.psmcfa','work/equivalent/validation/hg001-strict-batch/replicate-13.psmc','work/equivalent/validation/hg001-equivalent-batch/replicate-13.psmc']
    out['ridge']=dict(raw_sha256=sha256(raw),source_sha256=sha256(ROOT/'crates/psmc-cpu/examples/equivalent_ridge.rs'),inputs={p:sha256(ROOT/p) for p in inputs},results=ridge,interpretation='Fresh strict CPU likelihood and common-count Q using nine-decimal printed PA parameters. The lambda-only slice is effectively flat at the reported precision, supporting weak identification, not proving general equivalence. Endpoint Q differences around 1.8e-4 exceed the suggested 1e-4. Other fitted parameters also differ. Slice is not a profile likelihood: no nuisance parameters were reoptimized. Tiny irregularities include binary64 model evaluation noise.')
    out['decision']='Original tests preserved as historical engineering screens. Neither the fixed 0.01 screen nor a per-fit two-build envelope calibrates scientific equivalence; C itself fails the former. Descriptive distributions are broadly similar centrally, with a structured tail outlier. No new pass threshold selected from inspected results. Bootstrap SD remains context, not a confidence band or proof of acceptable bias.'
    save(ROOT/'bench/equivalent-followup-analysis.json',out)
if __name__=='__main__':main()

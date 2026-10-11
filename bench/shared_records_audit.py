#!/usr/bin/env python3
"""Audit scheduler exactness, source provenance and mode-specific timing gates."""
import json,re,os
from pathlib import Path
from common import ROOT,save,sha256
from phase1_differential import compare_output

def main():
 os.chdir(ROOT);v=json.load(open('bench/shared-records-final-validation.json'));p=json.load(open('bench/shared-records-final-performance.json'))
 assert v['status']==p['status']=='completed'
 assert v['binary_sha256']==p['binary_sha256']==sha256('work/shared-records/candidate')
 assert v['protocol_sha256']==p['protocol_sha256']==sha256('docs/shared-record-scheduling.md')
 baseline=json.load(open('bench/equivalent-c-baseline.json'));inputs={}
 for dataset in baseline['datasets'].values():
  for kind in ['original','blocks']:
   path=dataset[kind];assert sha256(path)==dataset[kind+'_sha256'];inputs[path]=sha256(path)
  for sample in dataset['samples']:
   assert sha256(sample['path'])==sample['sha256'];inputs[sample['path']]=sample['sha256']
 checked=0;helpers=0
 for report in [v,p]:
  for r in report['runs']:
   helpers+=r.get('helper_jobs',0)
   assert sha256(r['output'])==r['output_sha256']
   if r.get('outputs'):
    dest=Path(r['command'][r['command'].index('--output-dir')+1]);assert json.load(open(dest/'manifest.json'))['workers']==16
   for item in r.get('outputs',[]):
    path=Path(item['path']);assert sha256(path)==item['sha256']
    ref=(Path('work/linear-equivalent/validation')/(r['dataset']+'-batch')/path.name) if r['mode']=='equivalent' else (Path('work/equivalent/validation')/(r['dataset']+'-strict-batch')/path.name)
    compare_output(ref.read_bytes(),path.read_bytes());checked+=1
 assert helpers>0
 synthetic=0
 for mode in ['strict','equivalent']:
  runs={x['tag']:x for x in v['runs']}
  compare_output(*(Path(runs[f'single-{mode}-{workers}']['output']).read_bytes() for workers in [1,16]))
  root=Path('work/shared-records/final-validation')
  for i in range(8):
   ref=(root/f'synthetic-{mode}-1-on'/f'replicate-{i:02}.psmc').read_bytes()
   for cache in ['on','off']:
    compare_output(ref,(root/f'synthetic-{mode}-4-{cache}'/f'replicate-{i:02}.psmc').read_bytes());synthetic+=1

 tests={}
 for label in ['release-tests-final','debug-tests-final']:
  path=Path('work/shared-records')/(label+'.log');text=path.read_text();assert 'FAILED' not in text and 'error:' not in text
  rows=re.findall(r'test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored',text);assert rows
  tests[label]=dict(passed=sum(int(x[0]) for x in rows),failed=sum(int(x[1]) for x in rows),ignored=sum(int(x[2]) for x in rows),sha256=sha256(path))
 assert 'error:' not in Path('work/shared-records/all-features-final.log').read_text()
 regression=json.load(open('bench/shared-records-strict-regression.json'))
 applicable=0;obsolete=[];snapshots=0
 for backend,entry in regression['backend_reports'].items():
  child=json.load(open(entry['report']))
  for case in child['cases']:
   if case['status']=='passed': applicable+=1;snapshots+=int(case['name'].startswith('snapshot_exact_'))
   else:
    assert backend in ['cpu','scalar'] and case['name']=='reject_equivalent_mode',case
    obsolete.append(dict(backend=backend,name=case['name']))
 assert applicable==338 and len(obsolete)==2 and snapshots==10
 # The broad regression was frozen just before the CLI-only admission fix.
 # Every arithmetic/optimizer/IO source is identical to the final artifact.
 for path,h in regression['provenance']['source_sha256_at_freeze'].items():
  if path.startswith('crates/') and path!='crates/psmc-cli/src/batch.rs':assert sha256(path)==h,path
 out=dict(status='completed' ,base_commit='9d1e89c',binary_sha256=v['binary_sha256'],protocol_sha256=v['protocol_sha256'],inputs=inputs,checked_bootstrap_outputs=checked,synthetic_comparisons=synthetic,single_fit_comparisons=2,helper_jobs=helpers,tests=tests,strict_regression=dict(applicable_passed=applicable,exact_snapshots=snapshots,obsolete_rejections=obsolete,raw_status=regression['status'],scope='Same arithmetic source; regression before CLI-only memory-admission fix. Final binary reruns golden and human tests.'),performance=p['summary'],default_promotion=all(x['nonregression_gate'] for x in p['summary'].values()),sources={str(f):sha256(f) for f in Path('crates').rglob('*.rs')},reports={str(f):sha256(f) for f in Path('bench').glob('shared-records-*.json') if not f.name.endswith(('audit.json','install.json'))},not_run=['non-Linux affinity/hardware','ARM/NEON','CUDA hardware (four ignored tests)','hosted CI'],limits='Frequency is a core-performance heuristic on this host; portable fallback remains. Scheduler output matches each mode exactly, not equivalent vs strict. Single-fit timings are screens. Historical vanilla-C timings are not a new paired comparison.')
 save('bench/shared-records-audit.json',out);print(json.dumps({k:x for k,x in out.items() if k not in ['sources','reports']},indent=2))
if __name__=='__main__':main()

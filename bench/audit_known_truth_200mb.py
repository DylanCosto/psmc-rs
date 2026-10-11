#!/usr/bin/env python3
"""Audit panel provenance, physical units, complete records and numerical comparisons."""
import argparse,json,math,shlex
from pathlib import Path
import known_truth as p
import known_truth_200mb as panel

def main():
 a=argparse.ArgumentParser(description=__doc__);a.add_argument('--panel',type=Path,required=True);a=a.parse_args();root=a.panel.resolve()
 r=json.loads((root/'report.json').read_text());f=json.loads((root/'frozen.json').read_text())
 assert r['metadata']==f
 assert f['protocol_sha256']==p.sha(p.ROOT/'docs/known-truth-200mb-protocol.md')
 assert f['runner_sha256']==p.sha(p.ROOT/'bench/known_truth_200mb.py')
 assert f['shared_helper_sha256']==p.sha(p.ROOT/'bench/known_truth.py')
 for name,h in f['binary_hashes'].items():assert p.sha(root/'binaries'/name)==h
 assert len(r['cases'])==30
 assert {(x['history'],x['index']) for x in r['cases']}=={(h,i) for h in panel.HISTORIES for i in range(10)}
 checks=[]
 for c in r['cases']:
  assert c['status']=='complete',c
  d=root/f"{c['history']}-{c['index']:02}"
  assert p.sha(d/'input.psmcfa')==c['input_sha256']
  seqs=[''.join(chunk.splitlines()[1:]) for chunk in (d/'input.psmcfa').read_text().split('>')[1:]]
  assert len(seqs)==20 and all(len(s)==100000 and set(s)<=set('TK') for s in seqs)
  command=shlex.split(c['history2ms_command'])
  n0=panel.HISTORIES[c['history']][0][1]
  assert command[:3]==['msHOT-lite','2','20']
  assert float(command[command.index('-t')+1])==4*n0*2.5e-8*10000000
  pos=command.index('-r');assert math.isclose(float(command[pos+1]),4*n0*5e-9*10000000,rel_tol=1e-14)
  assert command[pos+2]=='10000000'
  events=[list(map(float,command[i+1:i+4])) for i,x in enumerate(command) if x=='-en']
  assert events==[[t/(4*n0),1.,n/n0] for t,n in panel.HISTORIES[c['history']][1:]]
  j=list(panel.HISTORIES).index(c['history'])*10+c['index'];assert c['seeds']==[11001+73*j,22009+137*j,33007+193*j]
  texts={m:(d/f'{m}.out').read_text() for m in ['c','strict','equivalent']}
  assert p.numerical(texts['c'])==p.numerical(texts['strict'])
  params={m:p.curve(text)[1] for m,text in texts.items()}
  assert params==c['parameters']
  for mode in texts:assert p.sha(d/f'{mode}.out')==c['runs'][mode]['output_sha256']
  # Independent pooling of the retained curves verifies band summaries, not
  # just the runner's declared boolean. PA reconstruction is tested separately.
  for b,metrics in c['bands'].items():
   start,end=panel.BANDS[b]
   times=[start*(end/start)**(i/128) for i in range(128)]
   history=panel.HISTORIES[c['history']]
   true=[math.log(next(n for edge,n in reversed(history) if edge<=t)) for t in times]
   assert all(math.isclose(x,y,rel_tol=1e-12,abs_tol=1e-14) for x,y in zip(true,metrics['truth_log_curve']))
   for mode in texts:
    values=params[mode]
    reconstructed=[math.log(values['n0']*values['lambdas'][max(i for i,edge in enumerate(values['group_starts_generations']) if edge<=t)]) for t in times]
    assert len(metrics['log_curves'][mode])==128
    assert all(math.isclose(x,y,rel_tol=1e-12,abs_tol=1e-14) for x,y in zip(reconstructed,metrics['log_curves'][mode]))
    error=math.sqrt(sum((x-y)**2 for x,y in zip(metrics['log_curves'][mode],metrics['truth_log_curve']))/128)
    assert math.isclose(error,metrics['rmse'][mode],rel_tol=1e-12,abs_tol=1e-14)
  checks.append({'history':c['history'],'index':c['index'],'bins':sum(map(len,seqs)),'strict_c_exact':True,'ms_units_and_events':True})
 assert panel.summarize(r['cases'])==r['summary']
 audit={'panel_sha256':p.sha(root/'report.json'),'protocol_sha256':f['protocol_sha256'],'audit_checks_passed':True,'panel_criteria_passed':r['passed'],'checked_datasets':30,'checked_fits':90,'checks':checks,'scope':'200 Mb idealized histories; whole-genome masks/real input/hosted CI not_run'}
 p.save(root/'audit.json',audit);print(json.dumps({k:v for k,v in audit.items() if k!='checks'},indent=2))
if __name__=='__main__':main()

#!/usr/bin/env python3
"""Bounded post-hoc pilot diagnostics; original files are hash checked before use."""
import subprocess,pathlib,json,hashlib,os,time
import argparse
parser=argparse.ArgumentParser()
parser.add_argument('--decimal',action='store_true')
args=parser.parse_args()
root=pathlib.Path.cwd(); out=root/'work/pilot-surface'; out.mkdir(parents=True,exist_ok=True)
binary=root/('target/release/examples/pilot_matrix_likelihood' if args.decimal else 'target/release/examples/pilot_surface')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for case in ['bottleneck-01','bottleneck-03','bottleneck-09','expansion-09']:
 p=root/'work/qualification/panel'/case
 files=[p/'input.psmcfa',p/'strict.out',p/'equivalent.out']
 old=json.loads((p/'result.json').read_text())
 assert sha(files[0])==old['input_sha256']
 for mode,f in zip(['strict','equivalent'],files[1:]): assert sha(f)==old['runs'][mode]['output_sha256']
 suffix='.decimal' if args.decimal else ''
 if args.decimal:
  subprocess.run(['python3','bench/pilot_decimal_model.py',case],check=True,timeout=120)
  evaluate_files=[files[0],files[1],out/(case+'.matrices')]
 else: evaluate_files=files
 cmd=['taskset','-c',str(min(os.sched_getaffinity(0))),'/usr/bin/time','-v','-o',str(out/(case+suffix+'.time')),str(binary),*map(str,evaluate_files)]
 start=time.time()
 with (out/(case+suffix+'.jsonl')).open('x') as f, (out/(case+suffix+'.stderr')).open('x') as err:
  r=subprocess.run(cmd,stdout=f,stderr=err,timeout=1800)
 evidence={'case':case,'stage':'decimal' if args.decimal else 'literal','command':[x.replace(str(root)+'/', '') for x in cmd],'binary_sha256':sha(binary),'input_sha256':sha(files[0]),'strict_sha256':sha(files[1]),'equivalent_sha256':sha(files[2]),'seconds':time.time()-start,'exit_code':r.returncode,'output_sha256':sha(out/(case+suffix+'.jsonl'))}
 (out/(case+suffix+'.meta.json')).write_text(json.dumps(evidence,indent=2)+'\n')
 print(case,r.returncode,round(evidence['seconds'],2),flush=True)
 if r.returncode: raise SystemExit(r.returncode)

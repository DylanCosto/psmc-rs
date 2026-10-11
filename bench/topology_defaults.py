#!/usr/bin/env python3
import json,subprocess,os,argparse
from pathlib import Path
root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description='i5-12600K affinity regression; requires CPUs 0-15 available')
parser.add_argument('--output',type=Path,required=True)
out=parser.parse_args().output.resolve()
if not set(range(16)).issubset(os.sched_getaffinity(0)): raise SystemExit('not_run: this host-specific screen needs allowed CPUs 0-15')
out.mkdir(parents=True,exist_ok=False)
binary=root/'target/release/psmc-rs'
results=[]
for mode in ['strict','equivalent']:
    expected=None
    for name,mask in [('all','0-15'),('p_only','0-3'),('e_only','12-15'),('mixed','0,12')]:
        dest=out/f'{mode}-{name}'
        cmd=['taskset','-c',mask,str(binary),'bootstrap','--mode',mode,'--workers','4','--replicates','4','--seed','42','--output-dir',str(dest),'-p','2+2+2','-N','3','-t','5','-I','0',str(root/'tests/fixtures/repeated.psmcfa')]
        subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=120)
        outputs=[p.read_bytes() for p in sorted(dest.glob('replicate-*.psmc'))]
        if expected is None: expected=outputs
        assert outputs==expected,(mode,name)
        manifest=json.loads((dest/'manifest.json').read_text())
        results.append({'mode':mode,'affinity':mask,'exact':True,'manifest':manifest})
(out/'report.json').write_text(json.dumps(results,indent=2)+'\n')
print('All 32 affinity-restricted bootstrap fits match in their mode.')

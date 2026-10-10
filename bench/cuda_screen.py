"""Early exact end-to-end CUDA counts screen, before resident-message decisions."""
import os,json
from pathlib import Path
from common import ROOT,save,sha256,timed_run
from phase1_differential import compare_output

def main():
    os.chdir(ROOT)
    env=dict(os.environ,PSMC_NVRTC_LIBRARY=json.loads(Path('bench/cuda-environment.json').read_text())['nvrtc_path'])
    oracle=json.loads(Path('bench/hg-benchmark.json').read_text())['canonical_outputs'][1]['path']
    report=dict(status='running',baseline_sha256=sha256('bin/psmc-rs-v0.3.3'),candidate_sha256=sha256('work/cuda/final-candidate'),runs=[])
    for mode,tile in [('cpu',16384),('cuda',16384),('cuda',65536),('cuda',4096)]:
        prefix=f'work/cuda/final-screen/{mode}-{tile}'
        binary='bin/psmc-rs-v0.3.3' if mode=='cpu' else 'work/cuda/final-candidate'
        cmd=['taskset','-c','0',binary,'--backend',mode,'--seed','42','-p','4+25*2+4+6','-N','30','-t','15','-r','5','-I','0']
        if mode=='cuda':cmd+=['--cuda-tile-sites',str(tile)]
        cmd+=['work/hg-input/bootstrap-01.psmcfa']
        result=timed_run(cmd,ROOT/prefix,env=env,timeout=1800)
        assert result['exit_code']==0,result
        result['comparison']=compare_output(Path(oracle).read_bytes(),Path(result['output']).read_bytes())
        report['runs'].append(result);save('bench/cuda-screen.json',report)
        print(mode,tile,result['wall_seconds'],result['user_seconds']+result['system_seconds'],flush=True)
    report['status']='passed';save('bench/cuda-screen.json',report)
if __name__=='__main__':main()

"""Fixed complete-batch CPU affinity screen, preserving every bootstrap draw."""
import os,json,argparse
from pathlib import Path
from common import ROOT,save,sha256,timed_run,read_fasta,draw_bootstrap
from phase2_common import clean_env
from phase1_differential import compare_output
RAW=Path('work/exhaust/schedule');REPORT='bench/exhaust-schedule.json'
def main():
    os.chdir(ROOT);RAW.mkdir(parents=True)
    data=json.load(open('bench/hg-input.json'));canonical=json.load(open('bench/hg-benchmark.json'))['canonical_outputs'];records=read_fasta(data['blocks'])
    binary='work/exhaust/cpu/baseline/target/release/psmc-rs'
    configs=[('all16','0-15',16),('pcores12','0-11',12),('physical10','0,2,4,6,8,10,12-15',10),('pcores6','0,2,4,6,8,10',6),('all12','0-15',12)]
    r=dict(status='running',binary=binary,binary_sha256=sha256(binary),input_sha256=sha256(data['blocks']),configs=configs,runs=[],protocol='Two rotations for screening only; fastest new candidate needs fresh fixed paired acceptance.')
    for rep in range(2):
        order=configs if rep==0 else configs[::-1]
        for label,affinity,workers in order:
            out=RAW/f'{label}-{rep}'
            cmd=['taskset','-c',affinity,binary,'bootstrap','--backend','cpu','--workers',str(workers),'--memory-mib','16384','--replicates','30','--seed',str(data['seed']),'--output-dir',str(out),'-p','4+25*2+4+6','-N','30','-t','15','-r','5','-I','0',data['blocks']]
            run=timed_run(cmd,ROOT/RAW/f'{label}-{rep}-time',env=clean_env(),timeout=1800);assert run['exit_code']==0
            manifest=json.loads((out/'manifest.json').read_text());assert manifest['failed_replicates']==0
            for i,c in enumerate(canonical):
                assert sha256(c['path'])==c['sha256'];compare_output(Path(c['path']).read_bytes(),(out/f'replicate-{i:02}.psmc').read_bytes())
                selected,draws=draw_bootstrap(records,data['seed']+i);assert manifest['replicates'][i]['source_indices']==selected
            run.update(label=label,repeat=rep,exact_outputs=30,cpu_seconds=run['user_seconds']+run['system_seconds'],admitted_workers=manifest['workers']);r['runs'].append(run);save(REPORT,r);print(label,rep,run['wall_seconds'],flush=True)
    r['status']='screened';save(REPORT,r)
if __name__=='__main__':main()

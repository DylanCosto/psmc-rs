"""Additional public-human, extended-fixture, error and scheduler CUDA gates."""
import os,json,subprocess
from pathlib import Path
from common import ROOT,save,sha256,timed_run
from phase1_differential import compare_output

def main():
    os.chdir(ROOT);raw=Path('work/cuda/delivery');raw.mkdir(exist_ok=True)
    binary='work/cuda/final-candidate';digest=sha256(binary)
    env=dict(os.environ,PSMC_NVRTC_LIBRARY=json.load(open('bench/cuda-environment.json'))['nvrtc_path'])
    report=dict(status='running',binary_sha256=digest,runner_sha256=sha256(__file__),extended=[],human=[],controls=[])
    def check_binary():assert sha256(binary)==digest
    for source in ['bench/cpu-campaign-fixtures.json','bench/cpu-campaign-hmm-fixtures.json']:
        previous=json.load(open(source));assert previous['status']=='passed'
        for case in previous['cases']:
            check_binary();oracle=next(r for r in case['runs'] if r['label']=='vanilla')
            assert sha256(oracle['output'])==oracle['sha256'] and sha256(case['input'])==case['input_sha256']
            out=raw/(case['id']+'.psmc');cmd=[binary,'--backend','cuda','--seed','42','-o',str(out),*oracle['command'][3:]]
            p=subprocess.run(cmd,env=env,capture_output=True,timeout=600);(raw/(case['id']+'.stderr')).write_bytes(p.stderr)
            assert p.returncode==0,p.stderr
            comparison=compare_output(Path(oracle['output']).read_bytes(),out.read_bytes())
            report['extended'].append(dict(id=case['id'],command=cmd,input_sha256=case['input_sha256'],oracle_sha256=oracle['sha256'],output=str(out),comparison=comparison,finite=case['finite']))
            save('bench/cuda-delivery.json',report)
    for label,input_file,oracle in [('hg001','work/hg-input/NA12878_chr22.psmcfa','bench/hg/pilot/vanilla.psmc'),('hg002','work/cpu-next/hg002/HG002_GRCh38_chr1.psmcfa','work/cpu-next/large/vanilla.psmc')]:
        check_binary();cmd=[binary,'--backend','cuda','--seed','42','--stats',str(raw/(label+'.stats.json')),'-p','4+25*2+4+6','-N','30','-t','15','-r','5','-I','0',input_file]
        result=timed_run(cmd,ROOT/raw/label,env=env,timeout=1800);assert result['exit_code']==0
        result.update(input_sha256=sha256(input_file),oracle_sha256=sha256(oracle),comparison=compare_output(Path(oracle).read_bytes(),Path(result['output']).read_bytes()),stats=json.loads((raw/(label+'.stats.json')).read_text()))
        assert not result['nonfinite_records_beyond_initial_RI'];report['human'].append(result);save('bench/cuda-delivery.json',report);print(label,result['wall_seconds'],flush=True)
    base=[binary,'--backend','cuda','-N','1','tests/fixtures/tiny.psmcfa']
    for name,cmd,variables in [
        ('missing-nvrtc',base,dict(env,PSMC_NVRTC_LIBRARY='/definitely/missing/libnvrtc.so')),
        ('tile-zero',[binary,'--backend','cuda','--cuda-tile-sites','0','tests/fixtures/tiny.psmcfa'],env),
        ('tile-overflow',[binary,'--backend','cuda','--cuda-tile-sites','1048577','tests/fixtures/tiny.psmcfa'],env),
        ('zero-device-budget',[binary,'--backend','cuda','--cuda-memory-mib','0','tests/fixtures/tiny.psmcfa'],env),
        ('insufficient-device-budget',[binary,'--backend','cuda','--cuda-memory-mib','1','tests/fixtures/tiny.psmcfa'],env),
        ('too-many-states',[binary,'--backend','cuda','-p','1025*1','tests/fixtures/tiny.psmcfa'],env),
        ('cpu-only-rejects-cuda',['work/cuda/cpu-only-target/release/psmc-rs','--backend','cuda','tests/fixtures/tiny.psmcfa'],env),
    ]:
        p=subprocess.run(cmd,env=variables,capture_output=True,timeout=60);assert p.returncode!=0 and b'psmc-rs:' in p.stderr
        report['controls'].append(dict(name=name,command=cmd,returncode=p.returncode,stderr=p.stderr.decode()));save('bench/cuda-delivery.json',report)
    # Memory admission and order independence on the same eight complete fits.
    for label,workers,budget,reverse in [('forward',4,1024,False),('reverse',4,16,True)]:
        out=raw/label;cmd=[binary,'bootstrap','--backend','cuda','--workers',str(workers),'--replicates','8','--seed','20261009','--memory-mib','512','--cuda-memory-mib',str(budget),'--output-dir',str(out),'-N','3','tests/fixtures/blocks.psmcfa']
        if reverse:cmd+=['--task-order','reverse']
        p=subprocess.run(cmd,env=env,capture_output=True,timeout=180);assert p.returncode==0,p.stderr
        manifest=json.loads((out/'manifest.json').read_text());assert manifest['workers']*manifest['cuda_worker_buffer_bytes']<=budget*1024*1024
        if reverse:
            assert manifest['workers']==2
            for i in range(8):compare_output((raw/'forward'/f'replicate-{i:02}.psmc').read_bytes(),(out/f'replicate-{i:02}.psmc').read_bytes())
        report['controls'].append(dict(name='scheduler-'+label,command=cmd,manifest=manifest));save('bench/cuda-delivery.json',report)
    report['status']='passed';save('bench/cuda-delivery.json',report)
if __name__=='__main__':main()

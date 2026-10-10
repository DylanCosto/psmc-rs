"""Audit the second-look evidence and the final promote/retain decision."""
import argparse,json,os,re,subprocess
from pathlib import Path
from common import ROOT,save,sha256,read_fasta,draw_bootstrap
from phase1_differential import compare_output

def main():
    os.chdir(ROOT);p=argparse.ArgumentParser();p.add_argument('--decision',required=True,choices=['retain','promote']);args=p.parse_args()
    reports={str(p):json.loads(p.read_text()) for p in sorted(Path('bench').glob('relook-*.json')) if p.name!='relook-audit.json'}
    for name,r in reports.items():assert r['status'] in ['passed','passed_exactness','screened','repaired','installed'],(name,r['status'])
    acceptance=reports['bench/relook-batches-accept.json'];assert args.decision==('promote' if acceptance['performance_gate'] else 'retain')
    build=reports['bench/relook-build.json'];old=json.load(open('bench/exhaust-final-build.json'))
    for label,entry in build['binaries'].items():assert sha256(entry['path'])==entry['sha256']
    for group in ['source_sha256','configuration_sha256']:
        for path,digest in build[group].items():assert sha256(Path('work/relook/final-build/source')/path)==digest
    for step in build['steps']:assert step['returncode']==0 and sha256(step['log'])==step['sha256']
    unit_counts=[sum(map(int,re.findall(r'test result: ok\. (\d+) passed',Path(build['steps'][i]['log']).read_text()))) for i in [1,2]]
    assert unit_counts==[41,45] and build['assembly']['fma']==build['assembly']['horizontal']==0
    assert sha256('bin/psmc-rs-v0.4.1')==old['binaries']['cpu']['sha256']
    if args.decision=='retain':
        for group in ['source_sha256','configuration_sha256']:
            for path,digest in old[group].items():assert sha256(path)==digest,path
        assert not subprocess.check_output(['git','diff','30efe0b','--','crates','Cargo.toml','Cargo.lock','rust-toolchain.toml'])
        assert sha256('bin/psmc-rs')==sha256('target/release/psmc-rs')==old['binaries']['cpu']['sha256']
        assert sha256('bin/psmc-rs-cuda')==old['binaries']['cuda']['sha256']
    else:
        for name in ['bench/relook-full-validation.json','bench/relook-validation.json','bench/relook-cuda-control.json']:
            assert reports[name]['status']=='passed'
        for group in ['source_sha256','configuration_sha256']:
            for path,digest in build[group].items():assert sha256(path)==digest

    counts={}
    for name in ['probe','cycles']:
        r=reports['bench/relook-'+name+'.json']
        assert r['runner_sha256']==sha256('bench/relook_'+name+'.py')
        for c in r['cases']:
            assert sha256(c['input'])==c['input_sha256'] and sha256(c['oracle'])==c['oracle_sha256']
            assert sha256(c['run']['output'])==c['run']['output_sha256']
            compare_output(Path(c['oracle']).read_bytes(),Path(c['run']['output']).read_bytes())
        counts[name]=len(r['cases'])
    for name in ['counts','forward','q']:
        r=reports['bench/relook-'+name+'.json'];cases={c['id']:c for c in r['cases']}
        for c in cases.values():assert sha256(c['input'])==c['input_sha256'] and sha256(c['oracle'])==c['oracle_sha256']
        variants=r.get('variants',r.get('binaries'))
        for v in variants.values():assert sha256(v.get('binary',v.get('path')))==v['sha256']
        for row in r['runs']:
            assert sha256(row['output'])==row['output_sha256'];compare_output(Path(cases[row['case']]['oracle']).read_bytes(),Path(row['output']).read_bytes())
        counts[name]=len(r['runs'])
    data=json.load(open('bench/hg-input.json'));records=read_fasta(data['blocks']);canonical=json.load(open('bench/hg-benchmark.json'))['canonical_outputs'];batches=[]
    for phase in ['probe','screen','accept']:
        r=reports['bench/relook-batches-'+phase+'.json'];assert r['runner_sha256']==sha256('bench/relook_batches.py')
        for row in r['runs']:
            manifest_path=Path(row['manifest']);manifest=json.loads(manifest_path.read_text());assert manifest['failed_replicates']==manifest['nonfinite_replicates']==0
            outputs=[]
            for i,c in enumerate(canonical):
                assert sha256(c['path'])==c['sha256'];out=manifest_path.parent/f'replicate-{i:02}.psmc';compare_output(Path(c['path']).read_bytes(),out.read_bytes())
                selected,draws=draw_bootstrap(records,data['seed']+i);assert manifest['replicates'][i]['source_indices']==selected
                actual=[json.loads(line) for line in (manifest_path.parent/f'replicate-{i:02}.draws.jsonl').read_text().splitlines()]
                assert actual[:-1]==[dict(event='bootstrap_draw',draw=j,**d) for j,d in enumerate(draws)]
                outputs.append(dict(path=str(out),sha256=sha256(out)))
            batches.append(dict(manifest=str(manifest_path),sha256=sha256(manifest_path),outputs=outputs))
        counts['batches-'+phase]=30*len(r['runs'])
    assert reports['bench/relook-reproduction.json']['status']=='passed'
    result=dict(status='passed',decision=args.decision,runner_sha256=sha256(__file__),baseline='30efe0b',
        installed_cpu_sha256=sha256('bin/psmc-rs'),installed_cuda_sha256=sha256('bin/psmc-rs-cuda'),
        candidate=build['binaries']['cpu'],unit_tests=unit_counts,outputs_rechecked=counts,total_outputs_rechecked=sum(counts.values()),
        batches=batches,performance_gate=acceptance['performance_gate'],wall_reduction=acceptance['wall_reduction'],cpu_reduction=acceptance['cpu_reduction'],faster_pairs=acceptance['faster_pairs'],
        reports={},
        limitation='Shared host; finite public chromosome controls and fixed 30 bootstraps. No significance claim for other hardware, whole genomes or private inputs.')
    result['reports']={n:dict(status=r['status'],sha256=sha256(n)) for n,r in reports.items()}
    result['runners']={str(p):sha256(p) for p in Path('bench').glob('relook_*.py')}
    save('bench/relook-audit.json',result)
    print({k:result[k] for k in ['status','decision','total_outputs_rechecked','wall_reduction','cpu_reduction','faster_pairs']},flush=True)
if __name__=='__main__':main()

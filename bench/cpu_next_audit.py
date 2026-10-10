#!/usr/bin/env python3
"""Reproduce candidate sources and recheck every retained performance output."""
import argparse,io,json,os,re,subprocess,tarfile
from pathlib import Path
from common import ROOT,save,sha256
from cpu_campaign_build import source_hashes
from cpu_next_candidates import BASE,prepare
from phase1_differential import compare_output
from phase2_common import verify_binaries

def main():
    os.chdir(ROOT);p=argparse.ArgumentParser();p.add_argument('--decision',choices=['promote','retain'],required=True);o=p.parse_args()
    names=['profile','hg002-input','hg002-sampling','screen','combination','gates','build','validation','extended','scheduler','review','large','scaling','batches','confirmation']
    reports={n:json.loads(Path('bench/cpu-next-'+n+'.json').read_text()) for n in names}
    for n,r in reports.items():assert r['status']==('built' if n=='build' else 'prepared_not_fitted' if n=='hg002-sampling' else 'passed'),n
    runners={'profile':'profile','hg002-input':'hg002','hg002-sampling':'large','screen':'candidates','combination':'combine','gates':'gates','extended':'extended_gate','review':'review','large':'large','scaling':'scaling','batches':'batches','confirmation':'confirm'}
    for name,suffix in runners.items():assert reports[name]['runner_sha256']==sha256('bench/cpu_next_'+suffix+'.py'),name
    assert reports['large']['input_manifest_sha256']==sha256('bench/cpu-next-hg002-input.json')
    assert reports['batches']['worker_selection']['scaling_report_sha256']==sha256('bench/cpu-next-scaling.json')
    build=reports['build'];batch=reports['batches'];candidate=build['rust_binary']['sha256'];baseline=batch['binaries']['baseline']['sha256']
    assert candidate==batch['binaries']['candidate']['sha256']==reports['large']['binaries']['candidate']['sha256']==reports['validation']['provenance']['binaries']['candidate']['sha256']
    expected_source=build['source_sha256'] if o.decision=='promote' else json.loads(Path('bench/counts-build.json').read_text())['source_sha256']
    assert source_hashes()==expected_source
    assert sha256('target/release/psmc-rs')==(candidate if o.decision=='promote' else baseline)
    assert sha256('work/cpu-next/baseline')==baseline=='24d47084c2914aa44109040b7f5593efb7353621cb0d36ccdb28cd1a060f4c83'
    assert sha256('bin/psmc-rs')==(candidate if o.decision=='promote' else baseline)
    if o.decision=='promote':assert sha256('bin/psmc-rs-v0.3.2')==baseline
    for n in ['validation','extended','scheduler']:
        if 'provenance' in reports[n]:verify_binaries(reports[n]['provenance'])
    checks={}
    def compare(label,oracle,path,digest=None):
        if digest:assert sha256(path)==digest
        compare_output(Path(oracle).read_bytes(),Path(path).read_bytes());checks[label]=checks.get(label,0)+1
    for case in reports['profile']['cases']:
        assert sha256(case['input'])==case['input_sha256'];assert sha256(case['oracle'])==case['oracle_sha256']
        for r in case['runs']:compare('profile',case['oracle'],r['output'],r['output_sha256'])
    cases={c['id']:c for c in reports['screen']['cases']}
    for r in reports['screen']['runs']:compare('screen',cases[r['case']]['oracle'],r['output'],r['output_sha256'])
    for r in reports['combination']['runs']:compare('combination',reports['combination']['case']['oracle'],r['output'],r['output_sha256'])
    human=json.loads(Path('bench/hg-benchmark.json').read_text())['canonical_outputs']
    for c in human:assert sha256(c['path'])==c['sha256']
    for r in reports['scaling']['runs']:
        for c,a in zip(human,r['outputs']):compare('scaling',c['path'],a['path'],a['sha256'])
    assert reports['confirmation']['primary_report_sha256']==sha256('bench/cpu-next-batches.json')
    for r in reports['confirmation']['runs']:
        assert len(r['outputs'])==30 and r['draws_exact']
        for c,a in zip(human,r['outputs']):compare('confirmation',c['path'],a['path'],a['sha256'])
    cases={c['id']:c for c in batch['cases']}
    for path,digest in batch['input_hashes'].items():assert sha256(path)==digest
    for r in batch['runs']:
        oracles=[c['path'] for c in human] if r['case']=='human' else cases[r['case']]['oracles']
        assert len(r['outputs'])==30 and r['draws_exact']
        for c,a in zip(oracles,r['outputs']):compare('batches',c,a['path'],a['sha256'])
    pilot=next(r for r in json.loads(Path('bench/hg-pilot.json').read_text())['runs'] if r['label']=='vanilla')
    assert sha256(pilot['output'])==pilot['output_sha256']
    for r in batch['unsplit']:compare('hg001-unsplit',pilot['output'],r['output'],r['output_sha256'])
    large=reports['large']['runs'];oracle=next(r for r in large if r['label']=='vanilla')
    for r in large:compare('hg002-unsplit',oracle['output'],r['output'],r['output_sha256'])
    for path,digest in reports['hg002-input']['source_files'].items():assert sha256(path)==digest
    hg=reports['hg002-input']['output'];assert sha256(hg['path'])==hg['sha256']
    for r in reports['hg002-sampling']['replicates']:assert sha256(r['path'])==r['sha256']
    for s in reports['gates']['steps']:assert s['returncode']==0 and sha256(s['log'])==s['sha256']
    unit=[sum(map(int,re.findall(r'test result: ok\. (\d+) passed;',Path(s['log']).read_text()))) for s in reports['gates']['steps'] if s['command'][:2]==['cargo','test']]
    assert unit==[35,35]
    # Regenerate numerical experiment sources independently from the pinned git tree.
    raw=Path('work/cpu-next/reproduce');raw.mkdir()
    variants={k:v for k,v in reports['screen']['variants'].items() if k!='baseline'}
    variants['combined']=reports['combination']['binaries']['combined']
    regenerated=[]
    for label,entry in variants.items():
        scratch=raw/label;scratch.mkdir()
        data=subprocess.check_output(['git','archive',BASE,'Cargo.toml','Cargo.lock','rust-toolchain.toml','crates'])
        with tarfile.open(fileobj=io.BytesIO(data)) as tar:tar.extractall(scratch,filter='data')
        for name in (['counts32s8','messages32'] if label=='combined' else [label]):prepare(scratch,name)
        subprocess.run(['cargo','fmt','--all'],cwd=scratch,check=True)
        actual={str(p.relative_to(scratch)):sha256(p) for p in (scratch/'crates').rglob('*.rs')};assert actual==entry['source'],label
        regenerated.append(label)
    assert build['source_sha256']['crates/psmc-cpu/src/simd.rs']==variants['combined']['source']['crates/psmc-cpu/src/simd.rs']
    batch['summary']['human']=reports['confirmation']['pooled_summary']
    effects={case:dict(wall_reduction_percent=100*(1-v['candidate']['wall_seconds']['median']/v['baseline']['wall_seconds']['median']),throughput_ratio=v['baseline']['wall_seconds']['median']/v['candidate']['wall_seconds']['median'],cpu_reduction_percent=100*(1-v['candidate']['cpu_seconds']['median']/v['baseline']['cpu_seconds']['median'])) for case,v in batch['summary'].items()}
    pairs=reports['confirmation']['paired_effects']
    criteria=dict(wall_at_least_two_percent=effects['human']['wall_reduction_percent']>=2,cpu_median_improves=effects['human']['cpu_reduction_percent']>0,wall_positive_pairs=sum(r['wall_reduction_percent']>0 for r in pairs)>=4,cpu_positive_pairs=sum(r['cpu_reduction_percent']>0 for r in pairs)>=4)
    assert o.decision==('promote' if all(criteria.values()) else 'retain'),criteria
    result=dict(status='passed',decision=o.decision,runner_sha256=sha256(__file__),source_matches_expected_release=True,acceptance_criteria=criteria,candidate_sha256=candidate,baseline_sha256=baseline,outputs_rechecked=checks,total_outputs_rechecked=sum(checks.values()),unit_tests=unit,regression_cases=sum(v['passed'] for v in reports['validation']['backend_reports'].values()),regenerated_source_matches=regenerated,effects=effects,pooled_human_summary=reports['confirmation']['pooled_summary'],paired_human_effects=reports['confirmation']['paired_effects'],reports={n:sha256('bench/cpu-next-'+n+'.json') for n in names})
    save('bench/cpu-next-delivery-check.json',result);print(json.dumps(result,indent=2))
if __name__=='__main__':main()

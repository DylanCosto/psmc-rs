"""Extend the exact-repetition diagnostic to sampled short message cycles."""
from pathlib import Path
import json,os
from common import ROOT,save,sha256
os.chdir(ROOT)
source=Path('bench/relook_probe.py').read_text()
source=source.replace("work/relook/probe","work/relook/cycles").replace('bench/relook-probe.json','bench/relook-cycles.json')
needle='        let mut uniform=0usize;'
rust=r'''
        // Sample complete rows every 64 sites; this is a diagnostic, not a skip path.
        let lags=[2usize,3,4,8,16,32,64];
        let mut cycles=[0usize;16]; let mut samples=0usize;
        let mut forward_history=std::collections::HashMap::<Vec<u64>,usize>::new();
        let mut backward_history=std::collections::HashMap::<Vec<u64>,usize>::new();
        let mut history_symbols=[u8::MAX;2];
        if length>128 {
            for u in (65..length-64).step_by(64) {
                samples+=1;
                for (j,&lag) in lags.iter().enumerate() {
                    if observations[u-lag..u].iter().all(|&z|z==observations[u-1]) &&
                        equal(&messages.forward[u*n..(u+1)*n],&messages.forward[(u-lag)*n..(u-lag+1)*n]) {cycles[j*2]+=1;}
                    if observations[u..u+lag].iter().all(|&z|z==observations[u]) &&
                        equal(&messages.backward[u*n..(u+1)*n],&messages.backward[(u+lag)*n..(u+lag+1)*n]) {cycles[j*2+1]+=1;}
                }
                // Full-key equality also finds longer cycles on the sampled grid.
                // Bound each history to 1024 samples; clear at any symbol break.
                for direction in 0..2 {
                    let span=if direction==0 {&observations[u-64..u]} else {&observations[u..u+64]};
                    let row=if direction==0 {&messages.forward[u*n..(u+1)*n]} else {&messages.backward[u*n..(u+1)*n]};
                    let history=if direction==0 {&mut forward_history} else {&mut backward_history};
                    if !span.iter().all(|&z|z==span[0]) || !row.iter().all(|x|x.is_finite()) {history.clear();continue;}
                    if history_symbols[direction]!=span[0] {history.clear();history_symbols[direction]=span[0];}
                    let key:Vec<_>=row.iter().map(|x|x.to_bits()).collect();
                    if history.contains_key(&key) {cycles[14+direction]+=1;}
                    else {if history.len()>=1024 {history.clear();}history.insert(key,u);}
                }
            }
        }
        eprintln!("CYCLES {{\"samples\":{},\"counts\":{:?}}}",samples,cycles);
'''
assert source.count(needle)==1
source=source.replace(needle,rust+needle)
namespace={'__file__':__file__}
exec(compile(source,'relook_cycles_generated','exec'),namespace)
report=json.load(open('bench/relook-cycles.json'))
report['base_runner_sha256']=sha256('bench/relook_probe.py')
report['lags']=[2,3,4,8,16,32,64]
report['scope']='Every 64th interior site of each exact full-fit record evaluation; full finite row-bit equality and homogeneous spans. Last two counts use bounded 1024-entry full-row histories on the sampled grid. Backward equality is only an upper bound until scale-period compatibility is checked.'
for case in report['cases']:
    rows=[json.loads(line[7:]) for line in (Path('work/relook/cycles')/(case['name']+'.stderr')).read_text().splitlines() if line.startswith('CYCLES ')]
    case['cycle_samples']=sum(row['samples'] for row in rows)
    case['cycle_counts']=[sum(row['counts'][i] for row in rows) for i in range(16)]
    print(case['name'],case['cycle_samples'],case['cycle_counts'],flush=True)
save('bench/relook-cycles.json',report)

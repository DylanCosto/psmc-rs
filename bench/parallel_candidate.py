#!/usr/bin/env python3
"""Prepare a disposable deterministic largest-work-first queue experiment."""
from pathlib import Path
import shutil
from common import ROOT


def prepare(destination):
 destination.mkdir()
 for name in ['Cargo.toml','Cargo.lock','rust-toolchain.toml']:shutil.copy2(ROOT/name,destination/name)
 shutil.copytree(ROOT/'crates',destination/'crates')
 if (ROOT/'.cargo').exists():shutil.copytree(ROOT/'.cargo',destination/'.cargo')
 path=destination/'crates/psmc-cli/src/batch.rs';s=path.read_text()
 def replace(old,new):
  nonlocal s
  assert s.count(old)==1,old
  s=s.replace(old,new)
 replace('    reverse: bool,','    order: TaskOrder,')
 replace('            reverse: false,','            order: TaskOrder::Forward,')
 replace('''                self.reverse = match value {
                    "forward" => false,
                    "reverse" => true,
                    _ => return Err("--task-order must be forward or reverse".into()),
                }''','''                self.order = match value {
                    "forward" => TaskOrder::Forward,
                    "reverse" => TaskOrder::Reverse,
                    "balanced" => TaskOrder::Balanced,
                    _ => return Err("--task-order must be forward, reverse or balanced".into()),
                };''')
 replace('struct JobReport {','''#[derive(Clone, Copy)]
enum TaskOrder { Forward, Reverse, Balanced }
impl TaskOrder {
    fn name(self) -> &'static str {
        match self { Self::Forward=>"forward",Self::Reverse=>"reverse",Self::Balanced=>"balanced" }
    }
}

// This changes only independent job dispatch, never a fit's occurrence order.
// Preview uses a separate RNG; job() restarts the identical seed and consumes the
// original draw stream before initializing the model. No shared mutable RNG.
fn dispatch_order(order: TaskOrder, replicates: usize, seed: i64, sequences: &[Sequence], cached: bool) -> Result<Vec<usize>,String> {
    let mut indices:Vec<_>=(0..replicates).collect();
    match order {
        TaskOrder::Forward=>{},
        TaskOrder::Reverse=>indices.reverse(),
        TaskOrder::Balanced=>{
            let mut work=Vec::with_capacity(replicates);
            for i in 0..replicates {
                let (sampled,_)=resample_indices(sequences,&mut LegacyRng::new(seed+i as i64))?;
                let mut seen=std::collections::HashSet::<&[u8]>::new();
                let mut bins=0_usize;
                for j in sampled {
                    let obs=sequences[j].observations.as_slice();
                    if !cached || seen.insert(obs) {
                        bins=bins.checked_add(obs.len()).ok_or("scheduling weight overflow")?;
                    }
                }
                work.push(bins);
            }
            indices.sort_unstable_by_key(|&i|(std::cmp::Reverse(work[i]),i));
        }
    }
    Ok(indices)
}

struct JobReport {''')
 replace('    fs::create_dir(&directory)?;', '''    let dispatch = dispatch_order(config.order, config.replicates, seed, &sequences, options.backend == "cpu" && options.cache)?;
    fs::create_dir(&directory)?;''')
 replace('''                    let index = if config.reverse {
                        config.replicates - 1 - position
                    } else {
                        position
                    };''','''                    let index = dispatch[position];''')
 replace('string(if config.reverse { "reverse" } else { "forward" })','string(config.order.name())')
 s+='''
#[cfg(test)]
mod scheduling_tests {
    use super::*;
    #[test]
    fn independent_dispatch_preserves_all_seed_indices_and_tie_order() {
        let sequences=vec![Sequence{name:"a".into(), observations:vec![0,1,0]},Sequence{name:"alias".into(), observations:vec![0,1,0]}];
        for cached in [true,false] {
            let order=dispatch_order(TaskOrder::Balanced,30,42,&sequences,cached).unwrap();
            // Equal-size identical records yield tied weights, even with caching.
            assert_eq!(order,(0..30).collect::<Vec<_>>());
        }
        let sequences=vec![Sequence{name:"short".into(),observations:vec![1]},Sequence{name:"long".into(),observations:vec![0;100]}];
        let mut order=dispatch_order(TaskOrder::Balanced,30,42,&sequences,true).unwrap();
        order.sort_unstable();assert_eq!(order,(0..30).collect::<Vec<_>>());
    }
}
'''
 path.write_text(s)
 main=destination/'crates/psmc-cli/src/main.rs';main.write_text(main.read_text().replace('--task-order forward|reverse;','--task-order forward|reverse|balanced;'))

if __name__=='__main__':prepare(ROOT/'work/parallel-candidate-v2')

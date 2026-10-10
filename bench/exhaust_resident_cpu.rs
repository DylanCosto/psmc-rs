//! Independent synthetic CPU message tasks for comparison with batched CUDA probe.
use psmc_core::{Pattern, Settings, model::Model, rng::LegacyRng};
use psmc_cpu::Workspace;
use std::{hint::black_box, sync::atomic::{AtomicUsize, Ordering}, time::Instant};
fn main() {
    let args:Vec<_>=std::env::args().collect();
    let jobs:usize=args[1].parse().unwrap();
    let workers:usize=args[2].parse().unwrap();
    let n=64;
    let settings=Settings { pattern:Pattern{text:"64*1".into(),groups:(0..n).collect(),n_free:n},max_t:15.0,alpha:0.1,tr_ratio:4.0,ran_init:0.0,divergence:None,initial_params:None,explicit_times:None };
    let model=Model::new(&settings,100,1000,&mut LegacyRng::new(42));
    let observations:Vec<_>=(0..50001).map(|i|match i%101 {0..=9=>1,31..=50=>2,_=>0}).collect();
    let next=AtomicUsize::new(0);
    let start=Instant::now();
    std::thread::scope(|scope| {
        for _ in 0..workers.min(jobs) {
            scope.spawn(|| {
                let mut workspace=Workspace::new(n);
                let prepared=workspace.prepare(&model);
                loop {
                    let i=next.fetch_add(1,Ordering::Relaxed);
                    if i>=jobs {break;}
                    black_box(workspace.evaluate_without_transitions(&prepared,&observations));
                }
            });
        }
    });
    println!("{{\"jobs\":{jobs},\"workers\":{workers},\"seconds\":{}}}",start.elapsed().as_secs_f64());
}

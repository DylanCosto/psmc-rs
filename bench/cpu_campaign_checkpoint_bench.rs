use psmc_core::{Pattern,Settings,hmm::Counts,model::Model,rng::LegacyRng};
use psmc_cpu::{SimdMode,Workspace,checkpoint_candidate::CheckpointWorkspace};
use std::{hint::black_box,time::Instant};
fn checksum(counts:&Counts,lk:f64,check:f64)->u64 {
    let mut value=lk.to_bits()^check.to_bits();
    for x in counts.a0.iter().chain(&counts.a).chain(&counts.e) { value=value.rotate_left(1)^x.to_bits(); }
    value
}
fn exact(a:&[f64],b:&[f64]) {
    assert_eq!(a.len(),b.len());
    for (&a,&b) in a.iter().zip(b) { assert!(a.to_bits()==b.to_bits() || a.is_nan() && b.is_nan()); }
}
fn main() {
    let args:Vec<_>=std::env::args().collect();
    assert_eq!(args.len(),6,"check|baseline|checkpoint states length repeats tile");
    let mode=&args[1];
    let n:usize=args[2].parse().unwrap(); let length:usize=args[3].parse().unwrap();
    let repeats:usize=args[4].parse().unwrap(); let tile:usize=args[5].parse().unwrap();
    assert!(n>0 && length>0 && repeats>0 && tile>0);
    let settings=Settings{pattern:Pattern{text:String::new(),groups:(0..n).map(|i|i/3).collect(),n_free:(n+2)/3},max_t:15.0,alpha:0.1,tr_ratio:4.0,ran_init:0.0,divergence:None,initial_params:None,explicit_times:None};
    let observations:Vec<_>=(0..length).map(|i|if i%127<9 {1} else if i%1024<50 {2} else {0}).collect();
    let model=Model::new(&settings,observations.iter().filter(|&&v|v==1).count(),observations.iter().filter(|&&v|v<2).count(),&mut LegacyRng::new(42));
    let started=Instant::now();
    let mut result=0_u64;
    if mode=="baseline" {
        let mut workspace=Workspace::new(n);
        for _ in 0..repeats {
            let prepared=workspace.prepare(black_box(&model));
            let (messages,counts)=workspace.evaluate(&prepared,black_box(&observations));
            result=result.wrapping_add(checksum(counts,messages.log_likelihood,messages.backward_check));
        }
    } else if mode=="checkpoint" {
        let mut workspace=CheckpointWorkspace::new(n,tile,SimdMode::Auto);
        for _ in 0..repeats {
            let prepared=workspace.prepare(black_box(&model));
            let (counts,lk,check)=workspace.evaluate(&prepared,black_box(&observations),|_,_,_|{});
            result=result.wrapping_add(checksum(counts,lk,check));
        }
    } else {
        assert_eq!(mode,"check");
        let mut baseline=Workspace::new(n);
        let mut candidate=CheckpointWorkspace::new(n,tile,SimdMode::Auto);
        let prepared=baseline.prepare(&model);
        let (messages,expected)=baseline.evaluate(&prepared,&observations);
        let prepared=candidate.prepare(&model);
        let (actual,lk,check)=candidate.evaluate(&prepared,&observations,|begin,f,b| {
            exact(f,&messages.forward[begin*n..begin*n+f.len()]);
            exact(b,&messages.backward[begin*n..begin*n+b.len()]);
        });
        exact(&actual.a,&expected.a); exact(&actual.e,&expected.e); exact(&actual.a0,&expected.a0);
        exact(&[lk,check],&[messages.log_likelihood,messages.backward_check]);
        result=checksum(actual,lk,check).wrapping_mul(repeats as u64);
    }
    let seconds=started.elapsed().as_secs_f64();
    println!("{{\"mode\":\"{mode}\",\"states\":{n},\"bins\":{length},\"tile\":{tile},\"repeats\":{repeats},\"checksum\":{result},\"section_wall_seconds\":{seconds}}}");
}

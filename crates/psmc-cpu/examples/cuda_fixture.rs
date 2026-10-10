//! Generate a synthetic ordered-message oracle for the isolated CUDA resident probe.
use psmc_core::{Pattern, Settings, hmm, model::Model, rng::LegacyRng};
use psmc_cpu::Workspace;
use std::{io::Write, time::Instant};
fn main() {
    let args: Vec<_> = std::env::args().collect();
    let length: usize = args[1].parse().unwrap();
    let n = 64;
    let settings = Settings {
        pattern: Pattern {
            text: "64*1".into(),
            groups: (0..n).collect(),
            n_free: n,
        },
        max_t: 15.0,
        alpha: 0.1,
        tr_ratio: 4.0,
        ran_init: 0.0,
        divergence: None,
        initial_params: None,
        explicit_times: None,
    };
    let model = Model::new(&settings, 100, 1000, &mut LegacyRng::new(42));
    let observations: Vec<_> = (0..length)
        .map(|i| match i % 101 {
            0..=9 => 1,
            31..=50 => 2,
            _ => 0,
        })
        .collect();
    let mut workspace = Workspace::new(n);
    let prepared = workspace.prepare(&model);
    let started = Instant::now();
    let (m, _) = workspace.evaluate_without_transitions(&prepared, &observations);
    let elapsed = started.elapsed().as_secs_f64();
    let mut file = std::fs::File::create(&args[2]).unwrap();
    file.write_all(&(n as u64).to_le_bytes()).unwrap();
    file.write_all(&(length as u64).to_le_bytes()).unwrap();
    for slice in [
        &model.initial,
        &model.transition,
        &model.emission,
        &hmm::pre_backward(&model),
        &m.forward,
        &m.backward,
        &m.scales,
    ] {
        for x in slice {
            file.write_all(&x.to_le_bytes()).unwrap();
        }
    }
    file.write_all(&observations).unwrap();
    println!(
        "{{\"states\":{n},\"sites\":{length},\"cpu_messages_and_emissions_seconds\":{elapsed}}}"
    );
}

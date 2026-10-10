//! Isolated dense-oracle versus workspace HMM timing. Use a release build and
//! run modes in alternating order on an otherwise idle machine. No fitting or
//! concurrency is performed; this is not an end-to-end workload benchmark.
use psmc_core::{Pattern, Settings, hmm, model::Model, rng::LegacyRng};
use psmc_cpu::{PreparedModel, Workspace};
use std::{hint::black_box, time::Instant};

fn main() {
    let args: Vec<_> = std::env::args().collect();
    assert_eq!(
        args.len(),
        6,
        "kernel_bench dense|cpu states bins repeats records"
    );
    let mode = &args[1];
    assert!(mode == "dense" || mode == "cpu");
    let n: usize = args[2].parse().unwrap();
    let length: usize = args[3].parse().unwrap();
    let repeats: usize = args[4].parse().unwrap();
    let records: usize = args[5].parse().unwrap();
    assert!(n > 1 && length > 0 && repeats > 0 && records > 0);
    let settings = Settings {
        pattern: Pattern {
            text: format!("{n}*1"),
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
    let sequences: Vec<Vec<u8>> = (0..records)
        .map(|record| {
            (0..length + record)
                .map(|i| match (i * 13 + record * 7) % 127 {
                    0..=11 => 1,
                    40..=63 => 2,
                    _ => 0,
                })
                .collect()
        })
        .collect();
    let effective = sequences.iter().flatten().filter(|&&x| x < 2).count();
    let heterozygous = sequences.iter().flatten().filter(|&&x| x == 1).count();
    let mut rng = LegacyRng::new(42);
    let model = Model::new(&settings, heterozygous, effective, &mut rng);
    let mut workspace = Workspace::new(n);
    // Differential check is outside the timing and includes every message and
    // count. The measured process cannot report a speed from mismatched work.
    let prepared = PreparedModel::new(&model);
    let ae = hmm::pre_backward(&model);
    for observations in &sequences {
        let dense = hmm::forward_backward(&model, observations, &ae);
        let counts = hmm::expectation(&model, observations, &dense, &ae);
        let (cpu, cpu_counts) = workspace.evaluate(&prepared, observations);
        assert_eq!(dense.forward, cpu.forward);
        assert_eq!(dense.backward, cpu.backward);
        assert_eq!(dense.scales, cpu.scales);
        assert_eq!(dense.log_likelihood.to_bits(), cpu.log_likelihood.to_bits());
        assert_eq!(dense.backward_check.to_bits(), cpu.backward_check.to_bits());
        assert_eq!(counts.a0, cpu_counts.a0);
        assert_eq!(counts.a, cpu_counts.a);
        assert_eq!(counts.e, cpu_counts.e);
    }
    drop(prepared);
    drop(ae);
    // Do not let the correctness warmup hide the first message-buffer allocation
    // from the workspace measurement. Subsequent records may reuse it normally.
    let mut workspace = Workspace::new(n);
    let mut checksum = 0_u64;
    let started = Instant::now();
    for _ in 0..repeats {
        if mode == "dense" {
            let ae = hmm::pre_backward(black_box(&model));
            for observations in &sequences {
                let messages = hmm::forward_backward(&model, black_box(observations), &ae);
                let counts = hmm::expectation(&model, observations, &messages, &ae);
                black_box((&messages, &counts));
                checksum = checksum
                    .wrapping_add(messages.log_likelihood.to_bits() ^ counts.a[0].to_bits());
            }
        } else {
            let prepared = PreparedModel::new(black_box(&model));
            for observations in &sequences {
                let (messages, counts) = workspace.evaluate(&prepared, black_box(observations));
                black_box((messages, counts));
                checksum = checksum
                    .wrapping_add(messages.log_likelihood.to_bits() ^ counts.a[0].to_bits());
            }
        }
    }
    let elapsed = started.elapsed().as_secs_f64();
    println!(
        "{{\"backend\":\"{mode}\",\"states\":{n},\"first_record_bins\":{length},\"records\":{records},\"repeats\":{repeats},\"seconds\":{elapsed:.9},\"checksum\":{checksum},\"exact_check\":true}}"
    );
}

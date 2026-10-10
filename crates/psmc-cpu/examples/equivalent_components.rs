//! Same-parameter component diagnostic over printed human-fit trajectories.
//! Synthetic observations; source parameters are public test fits.
use psmc_core::{
    Pattern, Settings,
    model::Model,
    rng::LegacyRng,
    structured::{Margins, StructuredModel},
};
use psmc_cpu::Workspace;
fn errors(a: &[f64], b: &[f64], abs: f64) -> (f64, f64, usize) {
    let mut maximum: f64 = 0.0;
    let mut relative: f64 = 0.0;
    let mut failures = 0;
    for (&a, &b) in a.iter().zip(b) {
        let diff = (a - b).abs();
        let scale = a.abs().max(b.abs());
        maximum = maximum.max(diff);
        if scale > 0.0 {
            relative = relative.max(diff / scale);
        }
        if !a.is_finite() || !b.is_finite() || diff > abs + 1e-12 * scale {
            failures += 1;
        }
    }
    (maximum, relative, failures)
}
fn main() {
    let observations: Vec<u8> = (0..2048)
        .map(|i| {
            if i % 31 == 0 {
                1
            } else if i % 19 == 0 {
                2
            } else {
                0
            }
        })
        .collect();
    for (file_index, path) in std::env::args().skip(1).enumerate() {
        let text = std::fs::read_to_string(path).unwrap();
        for (round, line) in text
            .lines()
            .filter(|line| line.starts_with("PA\t"))
            .enumerate()
        {
            let fields: Vec<_> = line.split_whitespace().collect();
            assert_eq!(fields[1], "4+25*2+4+6");
            let mut groups = vec![0; 4];
            for group in 1..=25 {
                groups.extend([group; 2]);
            }
            groups.extend([26; 4]);
            groups.extend([27; 6]);
            let settings = Settings {
                pattern: Pattern {
                    text: fields[1].into(),
                    groups,
                    n_free: 28,
                },
                max_t: 15.0,
                alpha: 0.1,
                tr_ratio: 5.0,
                ran_init: 0.0,
                divergence: None,
                initial_params: Some(fields[2..].iter().map(|s| s.parse().unwrap()).collect()),
                explicit_times: None,
            };
            let model = Model::new(&settings, 2, 1000, &mut LegacyRng::new(42));
            let mut candidate = model.clone();
            let mut factors = StructuredModel::new(64);
            factors.update(&mut candidate, &settings);
            if !factors.eligible(&candidate) {
                println!("{{\"file\":{file_index},\"round\":{round},\"eligible\":false}}");
                continue;
            }
            factors.materialize(&mut candidate);
            let mut dense = Workspace::new(64);
            let prepared = dense.prepare(&model);
            let (expected, expected_counts) = dense.evaluate(&prepared, &observations);
            let mut structured = Workspace::new(64);
            let prepared = structured.prepare(&candidate);
            let (actual, actual_counts) =
                structured.evaluate_structured(&prepared, &observations, &factors);
            let mut counts = expected_counts.clone();
            counts.normalizer();
            let mut margins = Margins::new(64);
            margins.update(&counts);
            for (name, a, b, absolute) in [
                (
                    "transition",
                    &model.transition,
                    &candidate.transition,
                    1e-14,
                ),
                ("forward", &expected.forward, &actual.forward, 1e-14),
                ("backward", &expected.backward, &actual.backward, 1e-14),
                ("counts", &expected_counts.a, &actual_counts.a, 1e-24),
            ] {
                let (abs, rel, failed) = errors(a, b, absolute);
                println!(
                    "{{\"file\":{file_index},\"round\":{round},\"eligible\":true,\"component\":\"{name}\",\"max_abs\":{abs:e},\"max_rel\":{rel:e},\"failed_values\":{failed}}}"
                );
            }
            let a = counts.q(&model);
            let b = factors.q(&counts, &candidate, &margins);
            let (abs, rel, failed) = errors(&[a], &[b], 1e-14);
            println!(
                "{{\"file\":{file_index},\"round\":{round},\"eligible\":true,\"component\":\"Q\",\"max_abs\":{abs:e},\"max_rel\":{rel:e},\"failed_values\":{failed}}}"
            );
        }
    }
}

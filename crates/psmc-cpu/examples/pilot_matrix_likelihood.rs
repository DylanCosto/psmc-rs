//! Post-hoc likelihood geometry; see docs/pilot-ridge-protocol.md.
use psmc_core::{Pattern, Sequence, Settings, model::Model, rng::LegacyRng};
use psmc_cpu::{SimdMode, Workspace};
fn read_model(path: &str) -> (Settings, Model) {
    let text = std::fs::read_to_string(path).unwrap();
    let pa = text
        .lines()
        .filter(|l| l.starts_with("PA\t"))
        .last()
        .unwrap();
    let p: Vec<_> = pa.split_whitespace().collect();
    let mut groups = Vec::new();
    let mut group = 0;
    for term in p[1].split('+') {
        let a: Vec<usize> = term.split('*').map(|x| x.parse().unwrap()).collect();
        let (repeats, width) = if a.len() == 1 {
            (1, a[0])
        } else {
            (a[0], a[1])
        };
        for _ in 0..repeats {
            groups.extend(std::iter::repeat_n(group, width));
            group += 1;
        }
    }
    let s = Settings {
        pattern: Pattern {
            text: p[1].into(),
            groups,
            n_free: group,
        },
        max_t: 15.,
        alpha: 0.1,
        tr_ratio: 5.,
        ran_init: 0.,
        divergence: None,
        initial_params: Some(p[2..].iter().map(|x| x.parse().unwrap()).collect()),
        explicit_times: None,
    };
    let m = Model::new(&s, 2, 1000, &mut LegacyRng::new(42));
    (s, m)
}

fn likelihood(m: &Model, seq: &[Sequence], mode: SimdMode) -> f64 {
    let mut w = Workspace::with_simd(m.n, mode).unwrap();
    let p = w.prepare(m);
    seq.iter()
        .map(|s| {
            w.evaluate_without_transitions(&p, &s.observations)
                .0
                .log_likelihood
        })
        .sum()
}

fn main() {
    let a: Vec<_> = std::env::args().collect();
    assert_eq!(a.len(), 4);
    let (settings, template) = read_model(&a[2]);
    let mut seq: Vec<Sequence> = Vec::new();
    for l in std::fs::read_to_string(&a[1]).unwrap().lines() {
        if let Some(name) = l.strip_prefix('>') {
            seq.push(Sequence {
                name: name.into(),
                observations: Vec::new(),
            });
        } else {
            seq.last_mut().unwrap().observations.extend(
                l.bytes()
                    .filter(|b| !b.is_ascii_whitespace())
                    .map(|b| match b {
                        b'T' => 0,
                        b'K' => 1,
                        _ => 2,
                    }),
            );
        }
    }
    for line in std::fs::read_to_string(&a[3]).unwrap().lines() {
        let mut it = line.split_whitespace();
        let label = it.next().unwrap();
        let values: Vec<f64> = it.map(|x| x.parse().unwrap()).collect();
        let n = template.n;
        let np = template.params.len();
        assert_eq!(values.len(), np + n + n * n + 3 * n);
        let mut m = template.clone();
        m.params.copy_from_slice(&values[..np]);
        m.update(&settings);
        let literal_bad = m
            .initial
            .iter()
            .chain(&m.transition)
            .chain(&m.emission)
            .filter(|x| !x.is_finite() || **x < 0. || **x > 1.)
            .count();
        let values = &values[np..];
        let max_difference = m
            .initial
            .iter()
            .chain(&m.transition)
            .chain(&m.emission)
            .zip(values)
            .filter(|(x, _)| x.is_finite())
            .map(|(x, y)| (x - y).abs())
            .fold(0.0_f64, f64::max);
        m.initial.copy_from_slice(&values[..n]);
        m.transition.copy_from_slice(&values[n..n + n * n]);
        m.emission.copy_from_slice(&values[n + n * n..]);
        assert!(values.iter().all(|x| x.is_finite() && *x >= 0. && *x <= 1.));
        assert!((m.initial.iter().sum::<f64>() - 1.).abs() < 1e-12);
        for row in m.transition.chunks(n) {
            assert!((row.iter().sum::<f64>() - 1.).abs() < 1e-12);
        }
        let ll = likelihood(&m, &seq, SimdMode::Auto);
        assert!(ll.is_finite());
        println!(
            "{{\"label\":\"{label}\",\"ll\":{ll:.17e},\"literal_bad_probabilities\":{literal_bad},\"max_finite_probability_difference\":{max_difference:.17e}}}"
        );
    }
}

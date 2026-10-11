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
fn path(s: &Model, e: &Model, t: f64) -> Vec<f64> {
    if t == 0. {
        return s.params.clone();
    }
    if t == 1. {
        return e.params.clone();
    }
    s.params
        .iter()
        .zip(&e.params)
        .map(|(a, b)| (a.ln() + t * (b.ln() - a.ln())).exp())
        .collect()
}
fn main() {
    let a: Vec<_> = std::env::args().collect();
    assert_eq!(a.len(), 4);
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
    let (settings, s) = read_model(&a[2]);
    let (_, e) = read_model(&a[3]);
    assert_eq!(s.params.len(), e.params.len());
    for (name, m) in [("strict", &s), ("equivalent", &e)] {
        let ll = likelihood(m, &seq, SimdMode::Auto);
        let scalar = likelihood(m, &seq, SimdMode::Off);
        println!(
            "{{\"kind\":\"endpoint\",\"base\":\"{name}\",\"ll\":{ll:.17e},\"scalar_ll\":{scalar:.17e},\"params\":{:?}}}",
            m.params
        );
    }
    for k in -16..=48 {
        let t = k as f64 / 32.;
        let mut m = s.clone();
        m.params = path(&s, &e, t);
        m.update(&settings);
        let ll = likelihood(&m, &seq, SimdMode::Auto);
        println!("{{\"kind\":\"path\",\"t\":{t},\"ll\":{ll:.17e}}}");
    }
    for (name, base) in [("strict", &s), ("equivalent", &e)] {
        for j in 0..base.params.len() {
            for d in [-0.1_f64, -0.01, 0.01, 0.1].into_iter().chain(if j == 3 {
                vec![-1., 1.]
            } else {
                vec![]
            }) {
                let mut m = base.clone();
                m.params[j] *= d.exp();
                m.update(&settings);
                let ll = likelihood(&m, &seq, SimdMode::Auto);
                println!(
                    "{{\"kind\":\"coordinate\",\"base\":\"{name}\",\"index\":{j},\"log_delta\":{d},\"ll\":{ll:.17e}}}"
                );
            }
        }
    }
    for t in [0., 0.25, 0.5, 0.75, 1.] {
        let mut base = s.clone();
        base.params = path(&s, &e, t);
        base.update(&settings);
        let initial = likelihood(&base, &seq, SimdMode::Auto);
        let mut x = [0.; 3];
        let mut calls = 0;
        let mut objective = |x: &[f64]| {
            calls += 1;
            if x.iter().any(|v| !v.is_finite() || v.abs() > 0.25) {
                return f64::INFINITY;
            }
            let mut m = base.clone();
            for j in 0..3 {
                m.params[j] *= x[j].exp();
            }
            m.update(&settings);
            let ll = likelihood(&m, &seq, SimdMode::Auto);
            if ll.is_finite() { -ll } else { f64::INFINITY }
        };
        psmc_core::optimizer::hooke_jeeves(&mut x, &mut objective, 0.01, 1e-5, 128);
        let ll = -objective(&x);
        println!(
            "{{\"kind\":\"nuisance\",\"t\":{t},\"initial_ll\":{initial:.17e},\"ll\":{ll:.17e},\"calls\":{calls},\"log_offsets\":{x:?}}}"
        );
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn endpoints_preserve_bits_and_midpoint_is_geometric() {
        let (settings, mut s) = read_model("../../tests/fixtures/golden/profile-k64.psmc");
        let mut e = s.clone();
        e.params[3] *= 4.;
        e.update(&settings);
        assert_eq!(path(&s, &e, 0.), s.params);
        assert_eq!(path(&s, &e, 1.), e.params);
        let mid = path(&s, &e, 0.5);
        assert!((mid[3] / s.params[3] - 2.).abs() < 1e-12);
        s.params = mid;
        s.update(&settings);
        let seq = vec![Sequence {
            name: "synthetic".into(),
            observations: vec![0, 1, 2, 0, 0, 1],
        }];
        assert_eq!(
            likelihood(&s, &seq, SimdMode::Auto),
            likelihood(&s, &seq, SimdMode::Off)
        );
    }
}

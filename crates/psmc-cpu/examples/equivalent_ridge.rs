//! Re-evaluate printed public-fit parameters on their exact bootstrap observations.
//! Compare both candidates against the SAME expected counts; Q from two different
//! posteriors is not a common objective. No optimization or parameter fitting here.
use psmc_core::{
    Pattern, Sequence, Settings,
    em::{ExpectationBackend, NoObserver},
    model::Model,
    rng::LegacyRng,
};
use psmc_cpu::CpuBackend;
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
    let refs: Vec<_> = seq.iter().collect();
    let (settings, strict) = read_model(&a[2]);
    let (_, equiv) = read_model(&a[3]);
    let mut cpu = CpuBackend::new(strict.n);
    let (mut cs, ls) = cpu.expectation(&strict, &refs, 0, &mut NoObserver).unwrap();
    cs.normalizer();
    let (mut ce, le) = cpu.expectation(&equiv, &refs, 0, &mut NoObserver).unwrap();
    ce.normalizer();
    println!(
        "{{\"kind\":\"endpoints\",\"strict_ll\":{ls:.17e},\"equivalent_ll\":{le:.17e},\"ll_delta\":{:.17e},\"q_on_strict_counts_delta\":{:.17e},\"q_on_equivalent_counts_delta\":{:.17e},\"strict_lambda0\":{:.17e},\"equivalent_lambda0\":{:.17e}}}",
        le - ls,
        cs.q(&equiv) - cs.q(&strict),
        ce.q(&equiv) - ce.q(&strict),
        strict.params[3],
        equiv.params[3]
    );
    for (base_name, base, base_ll) in [("strict", &strict, ls), ("equivalent", &equiv, le)] {
        for i in 0..=8 {
            let t = i as f64 / 8.;
            let mut m = base.clone();
            m.params[3] = ((1. - t) * strict.params[3].ln() + t * equiv.params[3].ln()).exp();
            m.update(&settings);
            let (_, ll) = cpu.expectation(&m, &refs, 0, &mut NoObserver).unwrap();
            println!(
                "{{\"kind\":\"lambda_slice\",\"base\":\"{base_name}\",\"fraction\":{t},\"lambda0\":{:.17e},\"ll_delta_from_base\":{:.17e},\"q_strict_counts_delta\":{:.17e},\"q_equivalent_counts_delta\":{:.17e}}}",
                m.params[3],
                ll - base_ll,
                cs.q(&m) - cs.q(base),
                ce.q(&m) - ce.q(base)
            );
        }
    }
}

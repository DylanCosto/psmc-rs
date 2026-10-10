// Synthetic differential fixture. See README.md for source/license provenance.
#[path = "../../crates/psmc-core/src/math.rs"]
mod math;
#[path = "../../crates/psmc-core/src/model.rs"]
mod model;
#[path = "../../crates/psmc-core/src/rng.rs"]
mod rng;
#[derive(Clone, Debug)]
pub struct Pattern {
    pub text: String,
    pub groups: Vec<usize>,
    pub n_free: usize,
}
impl Pattern {
    pub fn states(&self) -> usize {
        self.groups.len()
    }
}
#[derive(Clone, Debug)]
pub struct Settings {
    pub pattern: Pattern,
    pub max_t: f64,
    pub alpha: f64,
    pub tr_ratio: f64,
    pub ran_init: f64,
    pub divergence: Option<f64>,
    pub initial_params: Option<Vec<f64>>,
    pub explicit_times: Option<Vec<f64>>,
}
fn out(v: &[f64]) {
    use std::io::Write;
    for x in v {
        std::io::stdout().write_all(&x.to_ne_bytes()).unwrap()
    }
}
fn main() {
    let mut rng = rng::LegacyRng::new(42);
    for n in [1, 2, 4, 23, 64] {
        for mode in 0..6 {
            let s = Settings {
                pattern: Pattern {
                    text: String::new(),
                    groups: (0..n).map(|k| k / 3).collect(),
                    n_free: (n + 2) / 3,
                },
                max_t: 15.0,
                alpha: 0.1,
                tr_ratio: 4.0,
                ran_init: if mode >= 4 { 0.1 } else { 0.0 },
                divergence: if mode % 2 == 1 { Some(0.7) } else { None },
                initial_params: None,
                explicit_times: if mode == 2 || mode == 3 {
                    Some((0..n).map(|i| i as f64 * 0.3).collect())
                } else {
                    None
                },
            };
            let mut m = model::Model::new(&s, 23, 177, &mut rng);
            for _ in 0..2 {
                out(&m.params);
                out(&m.t);
                out(&m.sigma);
                out(&[m.c_pi, m.c_sigma]);
                out(&m.initial);
                out(&m.transition);
                out(&m.emission);
                out(&m.avg_times(&s));
                for i in 0..m.params.len() {
                    m.params[i] = m.params[i] * (1.0 + i as f64 * 0.01)
                }
                m.update(&s);
            }
        }
    }
}

//! Isolated construction/fit experiment; never selected by production CLI.
#[path = "support/stable_model.rs"]
mod stable_model;
use psmc_core::{
    Sequence, Settings,
    em::{ExpectationBackend, FitState, NoObserver, Observer},
    hmm::Counts,
    model::Model,
    rng::LegacyRng,
};
use psmc_cpu::{CpuBackend, SimdMode};
use std::io::{self, BufRead};
struct Candidate {
    inner: CpuBackend,
    stable: bool,
    fallbacks: usize,
    updates: usize,
}
impl ExpectationBackend for Candidate {
    fn expectation(
        &mut self,
        m: &Model,
        s: &[&Sequence],
        it: usize,
        o: &mut dyn Observer,
    ) -> io::Result<(Counts, f64)> {
        self.inner.expectation(m, s, it, o)
    }
    fn update_model(&mut self, m: &mut Model, s: &Settings) {
        self.updates += 1;
        if !self.stable {
            self.inner.update_model(m, s);
        } else if !stable_model::update(m, s) {
            self.fallbacks += 1;
            self.inner.update_model(m, s);
        }
    }
}
fn main() {
    let args: Vec<_> = std::env::args().collect();
    let s = Settings {
        pattern: psmc_io::parse_pattern(&args[2]).unwrap(),
        max_t: 15.0,
        alpha: 0.1,
        tr_ratio: 5.0,
        ran_init: 0.0,
        divergence: None,
        initial_params: None,
        explicit_times: None,
    };
    if args[1] == "matrices" {
        for line in io::stdin().lock().lines() {
            let line = line.unwrap();
            let mut m = Model::new(&s, 2, 1000, &mut LegacyRng::new(42));
            m.params = line
                .split_whitespace()
                .map(|x| x.parse().unwrap())
                .collect();
            assert_eq!(m.params.len(), s.pattern.n_free + 3);
            if !stable_model::update(&mut m, &s) {
                println!("invalid");
                continue;
            }
            println!(
                "{}",
                m.initial
                    .iter()
                    .chain(&m.transition)
                    .chain(&m.emission)
                    .map(|v| format!("{v:.17e}"))
                    .collect::<Vec<_>>()
                    .join(" ")
            );
        }
    } else if args[1] == "fit" {
        let seq = psmc_io::read_sequences(&args[3]).unwrap();
        let ordered: Vec<_> = seq.iter().collect();
        let stable = args[4] == "stable";
        let mut backend = Candidate {
            inner: CpuBackend::with_simd(s.pattern.states(), SimdMode::Off).unwrap(),
            stable,
            fallbacks: 0,
            updates: 0,
        };
        let mut state = FitState::new_ordered(&s, &ordered, &mut LegacyRng::new(42));
        backend.update_model(&mut state.model, &s);
        let started = std::time::Instant::now();
        let mut evaluations = 0;
        for iteration in 1..=10 {
            evaluations += state
                .iteration_with_backend(&s, &ordered, iteration, &mut NoObserver, &mut backend)
                .unwrap();
        }
        let ll = backend
            .expectation(&state.model, &ordered, 11, &mut NoObserver)
            .unwrap()
            .1;
        println!(
            "{{\"stable\":{stable},\"seconds\":{},\"final_ll\":{ll:.17e},\"last_estep_ll\":{:.17e},\"evaluations\":{evaluations},\"updates\":{},\"fallbacks\":{},\"params\":{:?}}}",
            started.elapsed().as_secs_f64(),
            state.lk,
            backend.updates,
            backend.fallbacks,
            state.model.params
        );
    } else {
        panic!("matrices PATTERN < parameters; or fit PATTERN INPUT literal|stable");
    }
}

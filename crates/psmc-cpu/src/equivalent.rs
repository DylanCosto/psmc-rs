//! Experimental structured engine with full transition counts and Q normalizer. Cached counts exist only during one expectation call;
//! the immutable model and encoded bytes therefore define their entire lifetime.
use crate::{SimdMode, Workspace};
use psmc_core::{
    Sequence, Settings,
    em::{BackendStats, ExpectationBackend, Observer},
    hmm::Counts,
    model::Model,
    model_workspace::ModelWorkspace,
    structured::{Margins, StructuredModel},
};
use std::{collections::HashMap, io};

pub struct EquivalentBackend {
    workspace: Workspace,
    settings: Settings,
    factors: StructuredModel,
    margins: Margins,
    eligible: bool,
    model_workspace: ModelWorkspace,
    pub profile: bool,
    pub cache_enabled: bool,
    counters: BackendStats,
}

struct Cached {
    counts: Counts,
    likelihood: f64,
    backward_check: f64,
}

impl EquivalentBackend {
    pub fn with_simd(settings: &Settings, mode: SimdMode) -> Result<Self, String> {
        let states = settings.pattern.states();
        Ok(Self {
            settings: settings.clone(),
            factors: StructuredModel::new(states),
            margins: Margins::new(states),
            eligible: false,
            workspace: Workspace::with_simd(states, mode)?,
            model_workspace: ModelWorkspace::new(states),
            profile: false,
            cache_enabled: true,
            counters: BackendStats::default(),
        })
    }
    pub fn simd_kernel(&self) -> &'static str {
        self.workspace.simd_kernel()
    }
}

fn warn(check: f64) {
    if check > 1.0 + 1e-6 || check < 1.0 - 1e-6 {
        eprintln!("++ Underflow may have happened ({check}).");
    }
}

impl ExpectationBackend for EquivalentBackend {
    fn expectation(
        &mut self,
        model: &Model,
        sequences: &[&Sequence],
        iteration: usize,
        observer: &mut dyn Observer,
    ) -> io::Result<(Counts, f64)> {
        // Reconstruct from exactly the current parameters, including the initial model.
        let mut current = model.clone();
        self.update_model(&mut current, &self.settings.clone());
        self.materialize_model(&mut current);
        let prepared = self.workspace.prepare(&current);
        let mut aggregate = Counts::zero(model.n);
        let mut likelihood = 0.0;
        // Only duplicated byte strings warrant a saved count matrix. HashMap
        // iteration order never participates in arithmetic or output order.
        let cache_enabled = self.cache_enabled && !observer.needs_sequence_messages();
        let mut occurrences = HashMap::<&[u8], usize>::new();
        if cache_enabled {
            for sequence in sequences {
                *occurrences.entry(&sequence.observations).or_default() += 1;
            }
        }
        let mut cache = HashMap::<&[u8], Cached>::new();
        for (index, sequence) in sequences.iter().enumerate() {
            self.counters.sequence_visits += 1;
            if self.cache_enabled && observer.needs_sequence_messages() {
                self.counters.snapshot_cache_bypass += 1;
            }
            let observations = sequence.observations.as_slice();
            if let Some(cached) = cache.get(observations) {
                warn(cached.backward_check);
                likelihood += cached.likelihood;
                aggregate.add(&cached.counts); // one repeated addition, including tiny counts, per occurrence
                self.counters.cache_hits += 1;
                continue;
            }
            let (messages, counts) = if self.eligible {
                self.workspace
                    .evaluate_structured(&prepared, observations, &self.factors)
            } else {
                self.workspace.evaluate(&prepared, observations)
            };
            warn(messages.backward_check);
            likelihood += messages.log_likelihood;
            observer.sequence(iteration, index, sequence, messages, counts)?;
            aggregate.add(counts);
            self.counters.sequence_evaluations += 1;
            if occurrences
                .get(observations)
                .is_some_and(|&count| count > 1)
            {
                cache.insert(
                    observations,
                    Cached {
                        counts: counts.clone(),
                        likelihood: messages.log_likelihood,
                        backward_check: messages.backward_check,
                    },
                );
            }
        }
        self.margins.update(&aggregate);
        Ok((aggregate, likelihood))
    }
    fn update_model(&mut self, model: &mut Model, settings: &Settings) {
        self.factors.update(model, settings);
        self.eligible = self.factors.eligible(model);
        if !self.eligible {
            self.model_workspace.update(model, settings);
            self.counters.structured_fallbacks += 1;
        }
        self.counters.model_updates += 1;
    }
    fn materialize_model(&mut self, model: &mut Model) {
        if self.eligible {
            self.factors.materialize(model);
        }
    }
    fn q(&self, counts: &Counts, model: &Model) -> f64 {
        if self.eligible {
            self.factors.q(counts, model, &self.margins)
        } else {
            counts.q(model)
        }
    }
    fn stats(&self) -> BackendStats {
        self.counters.clone()
    }
    fn profiling(&self) -> bool {
        self.profile
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use psmc_core::{
        Pattern,
        em::{DenseBackend, NoObserver},
        hmm,
        rng::LegacyRng,
    };

    fn settings(n: usize) -> Settings {
        Settings {
            pattern: Pattern {
                text: n.to_string(),
                groups: (0..n).map(|k| k / 3).collect(),
                n_free: n.div_ceil(3),
            },
            max_t: 15.0,
            alpha: 0.1,
            tr_ratio: 5.0,
            ran_init: 0.0,
            divergence: None,
            initial_params: None,
            explicit_times: None,
        }
    }
    fn close(a: &[f64], b: &[f64], absolute: f64) {
        assert_eq!(a.len(), b.len());
        for (i, (&a, &b)) in a.iter().zip(b).enumerate() {
            assert!(a.is_finite() && b.is_finite(), "nonfinite [{i}]: {a} {b}");
            assert!(
                (a - b).abs() <= absolute + 1e-12 * a.abs().max(b.abs()),
                "[{i}]: {a} {b}"
            );
        }
    }

    #[test]
    fn factors_messages_counts_and_q_match_dense_at_same_parameters() {
        for n in [2, 3, 4, 7, 23, 64] {
            for variant in 0..4 {
                let mut settings = settings(n);
                if variant == 1 {
                    settings.divergence = Some(0.3);
                }
                if variant == 2 {
                    settings.explicit_times =
                        Some((0..n).map(|k| 15.0 * k as f64 / (n - 1) as f64).collect());
                }
                let mut model = Model::new(&settings, 20, 10000, &mut LegacyRng::new(42));
                if variant == 3 {
                    for (k, p) in model.params[3..].iter_mut().enumerate() {
                        *p = 0.3 + (k % 5) as f64 * 0.6;
                    }
                    model.update(&settings);
                }
                let mut factors = StructuredModel::new(n);
                let mut structured = model.clone();
                factors.update(&mut structured, &settings);
                assert!(factors.eligible(&structured), "n={n} variant={variant}");
                factors.materialize(&mut structured);
                close(&model.transition, &structured.transition, 1e-14);
                close(&model.emission, &structured.emission, 1e-14);
                for len in [1, 2, 17, 257, 1024] {
                    let observations: Vec<u8> = (0..len)
                        .map(|i| {
                            if i % 37 == 0 {
                                1
                            } else if i % 13 == 0 {
                                2
                            } else {
                                0
                            }
                        })
                        .collect();
                    let dense =
                        hmm::forward_backward(&model, &observations, &hmm::pre_backward(&model));
                    let expected =
                        hmm::expectation(&model, &observations, &dense, &hmm::pre_backward(&model));
                    let mut workspace = Workspace::new(n);
                    let prepared = workspace.prepare(&structured);
                    let (actual, counts) =
                        workspace.evaluate_structured(&prepared, &observations, &factors);
                    close(&dense.forward, &actual.forward, 1e-14);
                    close(&dense.backward, &actual.backward, 1e-14);
                    close(&dense.scales, &actual.scales, 1e-14);
                    close(&[dense.log_likelihood], &[actual.log_likelihood], 1e-14);
                    close(&expected.a, &counts.a, 1e-24);
                    close(&expected.e, &counts.e, 1e-24);
                    close(&expected.a0, &counts.a0, 1e-24);
                    let mut counts = expected.clone();
                    counts.normalizer();
                    let mut margins = Margins::new(n);
                    margins.update(&counts);
                    close(
                        &[counts.q(&model)],
                        &[factors.q(&counts, &structured, &margins)],
                        1e-14,
                    );
                    if len == 1 {
                        assert!(counts.a.iter().all(|&x| x == 1e-25));
                    }
                }
            }
        }
    }

    #[test]
    fn cache_boundaries_and_candidate_recovery() {
        let settings = settings(23);
        let a = Sequence {
            name: "a".into(),
            observations: vec![0, 0, 1, 2, 0, 0, 0, 1],
        };
        let b = Sequence {
            name: "b".into(),
            observations: vec![2, 0, 1],
        };
        let sequences = [&a, &b, &a, &a, &b];
        let initial = Model::new(&settings, 20, 10000, &mut LegacyRng::new(42));
        let mut cached = EquivalentBackend::with_simd(&settings, SimdMode::Auto).unwrap();
        let mut plain = EquivalentBackend::with_simd(&settings, SimdMode::Off).unwrap();
        plain.cache_enabled = false;
        let (ca, cl) = cached
            .expectation(&initial, &sequences, 1, &mut NoObserver)
            .unwrap();
        let (pa, pl) = plain
            .expectation(&initial, &sequences, 1, &mut NoObserver)
            .unwrap();
        close(&ca.a, &pa.a, 1e-24);
        close(&ca.e, &pa.e, 1e-24);
        close(&[cl], &[pl], 1e-14);
        assert_eq!(cached.stats().cache_hits, 3);
        let mut dense = DenseBackend::default();
        let (da, dl) = dense
            .expectation(&initial, &sequences, 1, &mut NoObserver)
            .unwrap();
        close(&da.a, &ca.a, 1e-24);
        close(&[dl], &[cl], 1e-14);
        for invalid in [0.0, f64::NAN, f64::INFINITY] {
            let mut model = initial.clone();
            model.params[1] = invalid;
            cached.update_model(&mut model, &settings);
            assert!(!cached.eligible);
            let mut expected = model.clone();
            expected.update(&settings);
            let q = cached.q(&ca, &model);
            let dense_q = ca.q(&expected);
            assert!(q.to_bits() == dense_q.to_bits() || q.is_nan() && dense_q.is_nan());
            model.params.clone_from(&initial.params);
            cached.update_model(&mut model, &settings);
            assert!(cached.eligible);
            cached.materialize_model(&mut model);
            close(&initial.transition, &model.transition, 1e-14);
        }
        assert_eq!(cached.stats().structured_fallbacks, 3);
    }
}

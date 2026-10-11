//! Experimental structured engine with triangle margins and unnormalized Q. Cached counts exist only during one expectation call;
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
use std::{collections::HashMap, io, sync::OnceLock};

pub struct EquivalentBackend {
    workspace: Workspace,
    pub record_pool: Option<std::sync::Arc<crate::record_pool::RecordPool>>,
    frozen: Option<(Model, Vec<Vec<u8>>)>,
    dense_fallback: OnceLock<Counts>,
    settings: Settings,
    factors: StructuredModel,
    margins: Margins,
    eligible: bool,
    #[cfg(debug_assertions)]
    factor_params: Vec<u64>,
    model_workspace: ModelWorkspace,
    pub profile: bool,
    pub cache_enabled: bool,
    counters: BackendStats,
}

struct Cached {
    counts: Counts,
    likelihood: f64,
    backward_check: f64,
    margins: Margins,
}

impl EquivalentBackend {
    pub fn with_simd(settings: &Settings, mode: SimdMode) -> Result<Self, String> {
        let states = settings.pattern.states();
        Ok(Self {
            settings: settings.clone(),
            factors: StructuredModel::new(states),
            margins: Margins::new(states),
            eligible: false,
            #[cfg(debug_assertions)]
            factor_params: Vec::new(),
            workspace: Workspace::with_simd(states, mode)?,
            record_pool: None,
            frozen: None,
            dense_fallback: OnceLock::new(),
            model_workspace: ModelWorkspace::new(states),
            profile: false,
            cache_enabled: true,
            counters: BackendStats::default(),
        })
    }
    // Refreshing factors at E-step entry is not an optimizer model update.
    fn refresh(&mut self, model: &mut Model, settings: &Settings) -> bool {
        self.factors.update(model, settings);
        #[cfg(debug_assertions)]
        {
            self.factor_params.clear();
            self.factor_params
                .extend(model.params.iter().map(|v| v.to_bits()));
        }
        self.eligible = self.factors.eligible(model);
        if !self.eligible {
            self.model_workspace.update(model, settings);
        }
        !self.eligible
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
        let mut current = model.clone();
        self.refresh(&mut current, &self.settings.clone());
        self.materialize_model(&mut current);
        let linear = self.eligible && !observer.needs_sequence_messages();
        self.dense_fallback = OnceLock::new();
        self.frozen = linear.then(|| {
            (
                current.clone(),
                sequences.iter().map(|s| s.observations.clone()).collect(),
            )
        });
        let mut aggregate = Counts::zero(model.n);
        self.margins = Margins::new(model.n);
        let mut likelihood = 0.0;
        let cache_enabled = self.cache_enabled && !observer.needs_sequence_messages();
        let mut occurrences = HashMap::<&[u8], usize>::new();
        if cache_enabled {
            for sequence in sequences {
                *occurrences.entry(&sequence.observations).or_default() += 1;
            }
        }
        let mut parallel = HashMap::<usize, Cached>::new();
        if let Some(pool) = &self.record_pool {
            if pool.has_helpers() && linear && sequences.len() > 1 {
                let mut seen = std::collections::HashSet::<&[u8]>::new();
                let indices: Vec<_> = sequences
                    .iter()
                    .enumerate()
                    .filter_map(|(i, s)| {
                        (!cache_enabled || seen.insert(&s.observations)).then_some(i)
                    })
                    .collect();
                let records = indices
                    .iter()
                    .map(|&i| sequences[i].observations.clone())
                    .collect();
                let frozen = current.clone();
                let settings = self.settings.clone();
                let avx = self.workspace.avx.is_some();
                let results = pool.map(records, move |obs| {
                    let mut m = frozen.clone();
                    let mut factors = StructuredModel::new(m.n);
                    factors.update(&mut m, &settings);
                    factors.materialize(&mut m);
                    let r = crate::linear::evaluate(&m, &obs, &factors, avx, false);
                    Cached {
                        counts: r.counts,
                        margins: r.margins,
                        likelihood: r.likelihood,
                        backward_check: r.backward_check,
                    }
                });
                parallel.extend(indices.into_iter().zip(results));
            }
        }
        let mut cache = HashMap::<&[u8], Cached>::new();
        let prepared = (!linear).then(|| self.workspace.prepare(&current));
        for (index, sequence) in sequences.iter().enumerate() {
            self.counters.sequence_visits += 1;
            if self.cache_enabled && observer.needs_sequence_messages() {
                self.counters.snapshot_cache_bypass += 1;
            }
            let observations = sequence.observations.as_slice();
            if let Some(cached) = cache.get(observations) {
                warn(cached.backward_check);
                likelihood += cached.likelihood;
                aggregate.add(&cached.counts);
                self.margins.add(&cached.margins);
                self.counters.cache_hits += 1;
                continue;
            }
            let result = if let Some(result) = parallel.remove(&index) {
                result
            } else if linear {
                let r = crate::linear::evaluate(
                    &current,
                    observations,
                    &self.factors,
                    self.workspace.avx.is_some(),
                    false,
                );
                Cached {
                    counts: r.counts,
                    margins: r.margins,
                    likelihood: r.likelihood,
                    backward_check: r.backward_check,
                }
            } else {
                let prepared = prepared.as_ref().unwrap();
                let (messages, counts) = if self.eligible {
                    self.workspace
                        .evaluate_structured(prepared, observations, &self.factors)
                } else {
                    self.workspace.evaluate(prepared, observations)
                };
                observer.sequence(iteration, index, sequence, messages, counts)?;
                let mut margins = Margins::new(model.n);
                margins.update(counts);
                Cached {
                    counts: counts.clone(),
                    margins,
                    likelihood: messages.log_likelihood,
                    backward_check: messages.backward_check,
                }
            };
            warn(result.backward_check);
            likelihood += result.likelihood;
            aggregate.add(&result.counts);
            self.margins.add(&result.margins);
            self.counters.sequence_evaluations += 1;
            if occurrences
                .get(observations)
                .is_some_and(|&count| count > 1)
            {
                cache.insert(observations, result);
            }
        }
        Ok((aggregate, likelihood))
    }
    fn normalize_counts(&self, counts: &mut Counts) {
        counts.q0 = 0.0;
    }
    fn update_model(&mut self, model: &mut Model, settings: &Settings) {
        if self.refresh(model, settings) {
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
        #[cfg(debug_assertions)]
        debug_assert!(
            self.factor_params
                .iter()
                .copied()
                .eq(model.params.iter().map(|v| v.to_bits())),
            "Q model parameters do not match the cached factor snapshot"
        );
        if self.eligible {
            self.factors.q(counts, model, &self.margins)
        } else if let Some((frozen, records)) = &self.frozen {
            // Invalid probabilities have the same sentinel/NaN outcome without
            // reconstructing counts. Never clip factors or silently approximate
            // a valid literal transition matrix with margins.
            if model.emission[..2 * model.n]
                .iter()
                .chain(&model.transition)
                .any(|x| x.is_nan() || *x <= 0.0)
            {
                return counts.q(model);
            }
            let dense = self.dense_fallback.get_or_init(|| {
                let mut factors = StructuredModel::new(model.n);
                let mut m = frozen.clone();
                factors.update(&mut m, &self.settings);
                factors.materialize(&mut m);
                let mut sum = Counts::zero(model.n);
                let mut cache = HashMap::<&[u8], Counts>::new();
                for obs in records {
                    let c = cache.entry(obs).or_insert_with(|| {
                        crate::linear::evaluate(
                            &m,
                            obs,
                            &factors,
                            self.workspace.avx.is_some(),
                            true,
                        )
                        .counts
                    });
                    sum.add(c);
                }
                sum
            });
            dense.q(model)
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
        assert_eq!(cached.stats().model_updates, 0);
        assert_eq!(cached.stats().structured_fallbacks, 0);
        let mut dense = DenseBackend::default();
        let (da, dl) = dense
            .expectation(&initial, &sequences, 1, &mut NoObserver)
            .unwrap();
        let mut dm = Margins::new(initial.n);
        dm.update(&da);
        close(&dm.lower_row, &cached.margins.lower_row, 1e-24);
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
    #[test]
    fn linear_aggregation_preserves_duplicates_tails_and_cache_disabled() {
        if !crate::avx_available() {
            return;
        }
        let settings = settings(64);
        let model = Model::new(&settings, 20, 10000, &mut LegacyRng::new(42));
        let sequences: Vec<Sequence> = (0..11)
            .map(|j| Sequence {
                name: j.to_string(),
                observations: (0..if j == 9 { 13 } else { 257 })
                    .map(|i| {
                        if (i + j) % 31 == 0 {
                            1
                        } else if (i + j) % 19 == 0 {
                            2
                        } else {
                            0
                        }
                    })
                    .collect(),
            })
            .collect();
        let refs: Vec<_> = [3, 1, 3, 0, 2, 4, 5, 6, 1, 7, 8, 9, 10, 0]
            .iter()
            .map(|&j| &sequences[j])
            .collect();
        let mut baseline = EquivalentBackend::with_simd(&settings, SimdMode::Auto).unwrap();
        baseline.cache_enabled = false;
        let (want, ll) = baseline
            .expectation(&model, &refs, 1, &mut NoObserver)
            .unwrap();
        for cache in [false, true] {
            let mut candidate = EquivalentBackend::with_simd(&settings, SimdMode::Auto).unwrap();
            candidate.cache_enabled = cache;
            let (got, actual_ll) = candidate
                .expectation(&model, &refs, 1, &mut NoObserver)
                .unwrap();
            assert_eq!(got.a, want.a);
            assert_eq!(got.e, want.e);
            assert_eq!(got.a0, want.a0);
            assert_eq!(actual_ll, ll);
            assert_eq!(candidate.stats().sequence_visits, refs.len() as u64);
            assert_eq!(
                candidate.stats().sequence_evaluations,
                if cache { 11 } else { 14 }
            );
        }
        struct Watching(usize);
        impl Observer for Watching {
            fn sequence(
                &mut self,
                _: usize,
                _: usize,
                _: &Sequence,
                _: &psmc_core::hmm::Messages,
                _: &Counts,
            ) -> io::Result<()> {
                self.0 += 1;
                Ok(())
            }
        }
        let mut observed = EquivalentBackend::with_simd(&settings, SimdMode::Auto).unwrap();
        let mut watcher = Watching(0);
        let (got, actual_ll) = observed
            .expectation(&model, &refs, 1, &mut watcher)
            .unwrap();
        assert_eq!(watcher.0, refs.len());
        close(&got.e, &want.e, 1e-24);
        close(&[actual_ll], &[ll], 1e-14);
        assert_eq!(observed.stats().snapshot_cache_bypass, refs.len() as u64);
    }

    #[test]
    fn valid_literal_fallback_reconstructs_frozen_posterior_once() {
        let settings = settings(23);
        let model = Model::new(&settings, 20, 10000, &mut LegacyRng::new(42));
        let sequence = Sequence {
            name: "fallback".into(),
            observations: (0..513)
                .map(|i| {
                    if i % 29 == 0 {
                        1
                    } else if i % 11 == 0 {
                        2
                    } else {
                        0
                    }
                })
                .collect(),
        };
        let refs = [&sequence, &sequence];
        let mut backend = EquivalentBackend::with_simd(&settings, SimdMode::Auto).unwrap();
        let (counts, _) = backend
            .expectation(&model, &refs, 1, &mut NoObserver)
            .unwrap();
        let mut frozen = model.clone();
        let mut factors = StructuredModel::new(model.n);
        factors.update(&mut frozen, &settings);
        factors.materialize(&mut frozen);
        let record = crate::linear::evaluate(
            &frozen,
            &sequence.observations,
            &factors,
            backend.workspace.avx.is_some(),
            true,
        );
        let mut dense = Counts::zero(model.n);
        dense.add(&record.counts);
        dense.add(&record.counts);
        let mut candidate = model.clone();
        candidate.params[0] *= 1.1;
        backend.update_model(&mut candidate, &settings);
        candidate.update(&settings);
        backend.eligible = false; // exercise a valid literal fallback without changing its objective
        assert!(backend.dense_fallback.get().is_none());
        assert_eq!(backend.q(&counts, &candidate), dense.q(&candidate));
        assert!(backend.dense_fallback.get().is_some());
        assert_eq!(backend.q(&counts, &candidate), dense.q(&candidate));
        backend
            .expectation(&model, &refs, 2, &mut NoObserver)
            .unwrap();
        assert!(backend.dense_fallback.get().is_none());
    }

    #[test]
    #[cfg(debug_assertions)]
    #[should_panic(expected = "Q model parameters do not match")]
    fn q_rejects_stale_parameter_snapshot_in_debug() {
        let settings = settings(4);
        let mut model = Model::new(&settings, 20, 10000, &mut LegacyRng::new(42));
        let mut backend = EquivalentBackend::with_simd(&settings, SimdMode::Auto).unwrap();
        backend.update_model(&mut model, &settings);
        model.params[0] *= 1.1;
        backend.q(&Counts::zero(4), &model);
    }
}

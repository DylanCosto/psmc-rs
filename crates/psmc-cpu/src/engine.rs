//! Per-fit CPU engine. Cached counts exist only during one expectation call;
//! the immutable model and encoded bytes therefore define their entire lifetime.
use crate::{SimdMode, Workspace};
use psmc_core::{
    Sequence, Settings,
    em::{BackendStats, ExpectationBackend, Observer},
    hmm::Counts,
    model::Model,
    model_workspace::ModelWorkspace,
};
use std::{collections::HashMap, io};

pub struct CpuBackend {
    workspace: Workspace,
    mode: SimdMode,
    pub record_pool: Option<std::sync::Arc<crate::record_pool::RecordPool>>,
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

impl CpuBackend {
    pub fn new(states: usize) -> Self {
        Self::with_simd(states, SimdMode::Auto).expect("auto SIMD always has a fallback")
    }
    pub fn with_simd(states: usize, mode: SimdMode) -> Result<Self, String> {
        Ok(Self {
            workspace: Workspace::with_simd(states, mode)?,
            mode,
            record_pool: None,
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

impl ExpectationBackend for CpuBackend {
    fn expectation(
        &mut self,
        model: &Model,
        sequences: &[&Sequence],
        iteration: usize,
        observer: &mut dyn Observer,
    ) -> io::Result<(Counts, f64)> {
        let prepared = self.workspace.prepare(model);
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
        let mut parallel = HashMap::<usize, Cached>::new();
        if let Some(pool) = &self.record_pool {
            if pool.has_helpers() && !observer.needs_sequence_messages() && sequences.len() > 1 {
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
                let frozen = model.clone();

                let mode = self.mode;
                let results = pool.map(records, move |obs| {
                    let (counts, likelihood, backward_check) =
                        crate::record_pool::dense_record(&frozen, mode, &obs);
                    Cached {
                        counts,
                        likelihood,
                        backward_check,
                    }
                });
                parallel.extend(indices.into_iter().zip(results));
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
            if let Some(result) = parallel.remove(&index) {
                warn(result.backward_check);
                likelihood += result.likelihood;
                aggregate.add(&result.counts);
                self.counters.sequence_evaluations += 1;
                if occurrences
                    .get(observations)
                    .is_some_and(|&count| count > 1)
                {
                    cache.insert(observations, result);
                }
                continue;
            }
            let (messages, counts) = self.workspace.evaluate(&prepared, observations);
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
        Ok((aggregate, likelihood))
    }
    fn update_model(&mut self, model: &mut Model, settings: &Settings) {
        self.model_workspace.update(model, settings);
        self.counters.model_updates += 1;
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
        rng::LegacyRng,
    };

    fn exact(a: f64, b: f64) {
        assert!(
            a.to_bits() == b.to_bits() || a.is_nan() && b.is_nan(),
            "{a:?} != {b:?}"
        );
    }
    #[test]
    fn cache_preserves_multiplicity_order_and_parameter_invalidation() {
        let settings = Settings {
            pattern: Pattern {
                text: "2+2".into(),
                groups: vec![0, 0, 1, 1],
                n_free: 2,
            },
            max_t: 15.0,
            alpha: 0.1,
            tr_ratio: 4.0,
            ran_init: 0.0,
            divergence: None,
            initial_params: None,
            explicit_times: None,
        };
        let a = Sequence {
            name: "a".into(),
            observations: vec![0, 1, 2, 0, 0, 1, 0],
        };
        let b = Sequence {
            name: "b".into(),
            observations: vec![0, 1],
        };
        let a_alias = Sequence {
            name: "different-name".into(),
            observations: a.observations.clone(),
        };
        let sequences = [&a, &b, &a_alias, &a, &b, &a];
        let mut rng = LegacyRng::new(42);
        let mut model = Model::new(&settings, 6, 20, &mut rng);
        let mut cpu = CpuBackend::new(4);
        let mut dense = DenseBackend::default();
        for round in 0..3 {
            model.params[0] += 0.01;
            model.update(&settings);
            let (mut expected, expected_lk) = dense
                .expectation(&model, &sequences, round, &mut NoObserver)
                .unwrap();
            let (mut actual, actual_lk) = cpu
                .expectation(&model, &sequences, round, &mut NoObserver)
                .unwrap();
            exact(expected_lk, actual_lk);
            exact(expected.normalizer(), actual.normalizer());
            for (a, b) in expected
                .a0
                .iter()
                .chain(&expected.a)
                .chain(&expected.e)
                .zip(actual.a0.iter().chain(&actual.a).chain(&actual.e))
            {
                exact(*a, *b);
            }
        }
        assert_eq!(cpu.stats().sequence_visits, 18);
        assert_eq!(cpu.stats().sequence_evaluations, 6);
        assert_eq!(cpu.stats().cache_hits, 12);
    }
}

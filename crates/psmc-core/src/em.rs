//! Literal orchestration from original em.c; live last-callback model is retained.
//! Original PSMC copyright Genome Research Ltd/Broad Institute; MIT notice in
//! reference/LICENSE.psmc.txt applies to this translation.
use crate::{
    Sequence, Settings,
    hmm::{self, Counts, Messages},
    model::Model,
    optimizer::hooke_jeeves,
    rng::LegacyRng,
};
use std::{io, time::Instant};

#[derive(Debug)]
pub struct FitState {
    pub model: Model,
    pub post_sigma: Vec<f64>,
    pub lk: f64,
    pub q0: f64,
    pub q1: f64,
    pub last_candidate_q: f64,
    pub expectation_seconds: f64,
    pub mstep_seconds: f64,
}

pub trait Observer {
    /// True guarantees a sequence callback for every occurrence. Returning false
    /// permits count-cache hits to skip callbacks; only use for a no-op observer.
    fn needs_sequence_messages(&self) -> bool {
        true
    }
    fn model(&mut self, _iteration: usize, _settings: &Settings, _model: &Model) -> io::Result<()> {
        Ok(())
    }
    fn sequence(
        &mut self,
        _iteration: usize,
        _index: usize,
        _seq: &Sequence,
        _messages: &Messages,
        _counts: &Counts,
    ) -> io::Result<()> {
        Ok(())
    }
    fn aggregate(
        &mut self,
        _iteration: usize,
        _counts: &Counts,
        _likelihood: f64,
    ) -> io::Result<()> {
        Ok(())
    }
    fn objective(
        &mut self,
        _iteration: usize,
        _evaluation: usize,
        _raw: &[f64],
        _model: &Model,
        _negative_q: f64,
    ) -> io::Result<()> {
        Ok(())
    }
    fn em_end(
        &mut self,
        _iteration: usize,
        _state: &FitState,
        _evaluations: usize,
    ) -> io::Result<()> {
        Ok(())
    }
    fn finish(&mut self) -> io::Result<()> {
        Ok(())
    }
}

pub struct NoObserver;
impl Observer for NoObserver {
    fn needs_sequence_messages(&self) -> bool {
        false
    }
}

#[derive(Clone, Debug, Default)]
pub struct BackendStats {
    pub sequence_visits: u64,
    pub sequence_evaluations: u64,
    pub cache_hits: u64,
    pub snapshot_cache_bypass: u64,
    pub model_updates: u64,
    pub structured_fallbacks: u64,
    pub cuda_launches: u64,
    pub cuda_upload_bytes: u64,
    pub cuda_download_bytes: u64,
    pub cuda_count_seconds: f64,
}

/// Implementations must aggregate complete records in the original order.
/// All counts are specific to the exact live model in this call.
pub trait ExpectationBackend {
    fn expectation(
        &mut self,
        model: &Model,
        sequences: &[&Sequence],
        iteration: usize,
        observer: &mut dyn Observer,
    ) -> io::Result<(Counts, f64)>;
    fn update_model(&mut self, model: &mut Model, settings: &Settings) {
        model.update(settings);
    }
    fn materialize_model(&mut self, _model: &mut Model) {}
    fn normalize_counts(&self, counts: &mut Counts) {
        counts.normalizer();
    }
    fn q(&self, counts: &Counts, model: &Model) -> f64 {
        counts.q(model)
    }
    fn stats(&self) -> BackendStats {
        BackendStats::default()
    }
    fn profiling(&self) -> bool {
        false
    }
}

#[derive(Default)]
pub struct DenseBackend {
    pub profile: bool,
    pub counters: BackendStats,
}
impl ExpectationBackend for DenseBackend {
    fn expectation(
        &mut self,
        model: &Model,
        sequences: &[&Sequence],
        iteration: usize,
        observer: &mut dyn Observer,
    ) -> io::Result<(Counts, f64)> {
        let mut aggregate = Counts::zero(model.n);
        let ae = hmm::pre_backward(model);
        let mut likelihood = 0.0;
        for (index, sequence) in sequences.iter().enumerate() {
            let messages = hmm::forward_backward(model, &sequence.observations, &ae);
            if messages.backward_check > 1.0 + 1e-6 || messages.backward_check < 1.0 - 1e-6 {
                eprintln!(
                    "++ Underflow may have happened ({}).",
                    messages.backward_check
                );
            }
            likelihood += messages.log_likelihood;
            let counts = hmm::expectation(model, &sequence.observations, &messages, &ae);
            observer.sequence(iteration, index, sequence, &messages, &counts)?;
            aggregate.add(&counts);
            self.counters.sequence_visits += 1;
            self.counters.sequence_evaluations += 1;
        }
        Ok((aggregate, likelihood))
    }
    fn update_model(&mut self, model: &mut Model, settings: &Settings) {
        model.update(settings);
        self.counters.model_updates += 1;
    }
    fn stats(&self) -> BackendStats {
        self.counters.clone()
    }
    fn profiling(&self) -> bool {
        self.profile
    }
}

impl FitState {
    pub fn new(settings: &Settings, sequences: &[Sequence], rng: &mut LegacyRng) -> Self {
        Self::new_ordered(settings, &sequences.iter().collect::<Vec<_>>(), rng)
    }

    pub fn new_ordered(settings: &Settings, sequences: &[&Sequence], rng: &mut LegacyRng) -> Self {
        let sum_n = sequences.iter().map(|s| s.heterozygous_count()).sum();
        let sum_l = sequences.iter().map(|s| s.effective_length()).sum();
        let model = Model::new(settings, sum_n, sum_l, rng);
        let n = model.n;
        Self {
            model,
            post_sigma: vec![0.0; n],
            lk: 0.0,
            q0: 0.0,
            q1: 0.0,
            last_candidate_q: f64::NAN,
            expectation_seconds: 0.0,
            mstep_seconds: 0.0,
        }
    }

    pub fn iteration(
        &mut self,
        settings: &Settings,
        sequences: &[Sequence],
        iteration: usize,
        observer: &mut dyn Observer,
    ) -> io::Result<usize> {
        self.iteration_with_backend(
            settings,
            &sequences.iter().collect::<Vec<_>>(),
            iteration,
            observer,
            &mut DenseBackend::default(),
        )
    }

    pub fn iteration_with_backend(
        &mut self,
        settings: &Settings,
        sequences: &[&Sequence],
        iteration: usize,
        observer: &mut dyn Observer,
        backend: &mut dyn ExpectationBackend,
    ) -> io::Result<usize> {
        let n = self.model.n;
        let started = backend.profiling().then(Instant::now);
        let (mut aggregate, likelihood) =
            backend.expectation(&self.model, sequences, iteration, observer)?;
        backend.normalize_counts(&mut aggregate);
        if let Some(started) = started {
            self.expectation_seconds += started.elapsed().as_secs_f64();
        }
        observer.aggregate(iteration, &aggregate, likelihood)?;
        self.lk = likelihood;
        let mut params = self.model.params.clone();
        let started = backend.profiling().then(Instant::now);
        self.q0 = backend.q(&aggregate, &self.model);
        let mut evaluations = 0;
        let mut last_q = f64::NAN;
        let mut observation_error = None;
        let mut objective = |candidate: &[f64]| {
            evaluations += 1;
            for (i, value) in candidate.iter().enumerate() {
                self.model.params[i] = value.abs();
            }
            backend.update_model(&mut self.model, settings);
            if observation_error.is_none() {
                if observer.needs_sequence_messages() {
                    backend.materialize_model(&mut self.model);
                }
                if let Err(error) = observer.model(iteration, settings, &self.model) {
                    observation_error = Some(error);
                }
            }
            let negative_q = -backend.q(&aggregate, &self.model);
            last_q = -negative_q;
            if observation_error.is_none() {
                if let Err(error) =
                    observer.objective(iteration, evaluations, candidate, &self.model, negative_q)
                {
                    observation_error = Some(error);
                }
            }
            negative_q
        };
        self.q1 = -hooke_jeeves(&mut params, &mut objective, 0.5, 1e-7, 50000);
        if let Some(started) = started {
            self.mstep_seconds += started.elapsed().as_secs_f64();
        }
        if let Some(error) = observation_error {
            return Err(error);
        }
        self.last_candidate_q = last_q;
        backend.materialize_model(&mut self.model);
        // Deliberately do not copy optimizer params back or reevaluate. C leaves
        // the live model at the final objective callback, not its accepted x.
        let mut sum = 0.0;
        for k in 0..n {
            sum += aggregate.e[k] + aggregate.e[n + k];
        }
        for k in 0..n {
            self.post_sigma[k] = (aggregate.e[k] + aggregate.e[n + k]) / sum;
        }
        observer.em_end(iteration, self, evaluations)?;
        Ok(evaluations)
    }
}

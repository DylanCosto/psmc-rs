//! Per-fit CPU engine. Cached counts exist only during one expectation call;
//! the immutable model and encoded bytes therefore define their entire lifetime.
use psmc_cpu::{SimdMode, Workspace};
mod driver;
#[cfg(test)]
mod tests;
use psmc_core::{
    Sequence, Settings,
    em::{BackendStats, ExpectationBackend, Observer},
    hmm::Counts,
    model::Model,
    model_workspace::ModelWorkspace,
};
use std::{collections::HashMap, io};

pub struct CudaBackend {
    device: driver::Device,
    tile_sites: usize,
    workspace: Workspace,
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

impl CudaBackend {
    pub fn new(states: usize, mode: SimdMode, tile_sites: usize) -> Result<Self, String> {
        if states == 0 || states > 1024 || tile_sites == 0 || tile_sites > 1_048_576 {
            return Err("CUDA requires 1..1024 states and 1..1048576 tile sites".into());
        }
        Ok(Self {
            device: driver::Device::new()?,
            tile_sites,
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

impl ExpectationBackend for CudaBackend {
    fn expectation(
        &mut self,
        model: &Model,
        sequences: &[&Sequence],
        iteration: usize,
        observer: &mut dyn Observer,
    ) -> io::Result<(Counts, f64)> {
        let prepared = self.workspace.prepare(model);
        let ae = psmc_core::hmm::pre_backward(model);
        self.device.prepare(&ae).map_err(io::Error::other)?;
        self.counters.cuda_upload_bytes += (ae.len() * 8) as u64;
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
            let (messages, cpu_counts) = self
                .workspace
                .evaluate_without_transitions(&prepared, observations);
            let mut counts = cpu_counts.clone();
            let length = observations.len();
            let count_started = self.profile.then(std::time::Instant::now);
            for start in (1..length).step_by(self.tile_sites) {
                let end = start.saturating_add(self.tile_sites).min(length);
                self.device
                    .tile(
                        &messages.forward[start * model.n..end * model.n],
                        &messages.backward[(start + 1) * model.n..(end + 1) * model.n],
                        &observations[start..end],
                        &mut counts.a,
                        model.n,
                        start == 1,
                        end == length,
                    )
                    .map_err(io::Error::other)?;
                self.counters.cuda_launches += 1;
                self.counters.cuda_upload_bytes += ((end - start) * (16 * model.n + 1)) as u64;
                if end == length {
                    self.counters.cuda_download_bytes += (8 * model.n * model.n) as u64;
                }
            }
            if let Some(started) = count_started {
                self.counters.cuda_count_seconds += started.elapsed().as_secs_f64();
            }
            warn(messages.backward_check);
            likelihood += messages.log_likelihood;
            observer.sequence(iteration, index, sequence, messages, &counts)?;
            aggregate.add(&counts);
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

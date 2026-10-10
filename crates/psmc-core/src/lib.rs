//! Literal dense f64 translation of pinned legacy PSMC. No accelerated backend.
pub mod em;
pub mod hmm;
pub mod math;
pub mod model;
pub mod model_workspace;
pub mod optimizer;
pub mod rng;

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

#[derive(Clone, Debug)]
pub struct Sequence {
    pub name: String,
    pub observations: Vec<u8>,
}

impl Sequence {
    pub fn effective_length(&self) -> usize {
        self.observations.iter().filter(|&&x| x < 2).count()
    }
    pub fn heterozygous_count(&self) -> usize {
        self.observations.iter().filter(|&&x| x == 1).count()
    }
}

pub mod structured;

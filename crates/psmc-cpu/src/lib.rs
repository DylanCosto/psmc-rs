//! Reusable, strict CPU HMM workspace. The scalar dense oracle remains in core.
//!
//! This is the same dense arithmetic with row slices and reusable storage, not a
//! structured transition algorithm. See README.md for the operation-order proof.

/*
The MIT License

Copyright (c) 2007-2009 Genome Research Ltd (GRL)
              2009-2015 Broad Institute

Permission is hereby granted, free of charge, to any person obtaining
a copy of this software and associated documentation files (the
"Software"), to deal in the Software without restriction, including
without limitation the rights to use, copy, modify, merge, publish,
distribute, sublicense, and/or sell copies of the Software, and to
permit persons to whom the Software is furnished to do so, subject to
the following conditions:

The above copyright notice and this permission notice shall be
included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS
BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN
ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
*/

use psmc_core::{
    hmm::{Counts, Messages},
    math::ln,
    model::Model,
};

mod linear;
#[cfg(test)]
mod lockstep;
pub mod record_pool;
mod simd;
pub use simd::{SimdMode, avx_available};

const TINY: f64 = 1e-25;

/// Arrays derived once from one immutable parameter snapshot. The borrow prevents
/// updating the model while these products are in use or silently reusing them
/// after a parameter change. No statistical observations are cached here.
pub struct PreparedModel<'a> {
    model: &'a Model,
    transpose: Vec<f64>,
    emission_transition: Vec<f64>,
    emission_transition_transpose: Vec<f64>,
}

impl<'a> PreparedModel<'a> {
    pub fn new(model: &'a Model) -> Self {
        Self::with_avx_layout(model, avx_available() && model.n >= 4)
    }

    fn with_avx_layout(model: &'a Model, avx: bool) -> Self {
        let n = model.n;
        assert!(n > 0, "HMM must have at least one state");
        let square = n.checked_mul(n).expect("HMM state count is too large");
        let emission_len = n.checked_mul(3).expect("HMM state count is too large");
        assert_eq!(model.initial.len(), n);
        assert_eq!(model.transition.len(), square);
        assert_eq!(model.emission.len(), emission_len);
        let mut transpose = vec![0.0; square];
        for (k, row) in transpose.chunks_exact_mut(n).enumerate() {
            for (l, target) in row.iter_mut().enumerate() {
                *target = model.transition[l * n + k];
            }
        }
        let mut emission_transition = vec![0.0; square.checked_mul(3).expect("HMM is too large")];
        for (emission, product) in model
            .emission
            .chunks_exact(n)
            .zip(emission_transition.chunks_exact_mut(square))
        {
            for (transition, target) in model
                .transition
                .chunks_exact(n)
                .zip(product.chunks_exact_mut(n))
            {
                for ((target, &e), &a) in target.iter_mut().zip(emission).zip(transition) {
                    *target = e * a;
                }
            }
        }
        let mut emission_transition_transpose = if avx {
            vec![0.0; emission_transition.len()]
        } else {
            Vec::new()
        };
        if avx {
            for z in 0..3 {
                for k in 0..n {
                    for l in 0..n {
                        emission_transition_transpose[z * square + l * n + k] =
                            emission_transition[z * square + k * n + l];
                    }
                }
            }
        }
        Self {
            model,
            transpose,
            emission_transition,
            emission_transition_transpose,
        }
    }

    pub fn states(&self) -> usize {
        self.model.n
    }
}

/// One independent worker's messages and counts. Capacity is retained across
/// records and iterations; lengths always match the current record so snapshots
/// cannot include stale data. Every used cell is overwritten before reading it.
pub struct Workspace {
    messages: Messages,
    counts: Counts,
    scan: Vec<f64>,
    avx: Option<simd::Avx>,
}

impl Workspace {
    pub fn new(n: usize) -> Self {
        Self::with_simd(n, SimdMode::Auto).expect("auto SIMD always has a fallback")
    }

    pub fn with_simd(n: usize, mode: SimdMode) -> Result<Self, String> {
        assert!(n > 0, "HMM must have at least one state");
        let avx = simd::Avx::select(mode, n)?;
        Ok(Self {
            messages: Messages {
                length: 0,
                n,
                forward: Vec::new(),
                backward: Vec::new(),
                scales: Vec::new(),
                log_likelihood: 0.0,
                backward_check: 0.0,
            },
            counts: Counts::zero(n),
            scan: Vec::new(),
            avx,
        })
    }

    pub fn simd_kernel(&self) -> &'static str {
        if self.avx.is_some() { "avx" } else { "scalar" }
    }

    /// Prepare only the layouts used by this workspace's selected kernel.
    pub fn prepare<'a>(&self, model: &'a Model) -> PreparedModel<'a> {
        PreparedModel::with_avx_layout(model, self.avx.is_some())
    }

    /// Evaluate one existing sequence with exactly the dense oracle's binary64
    /// expression grouping and ascending per-cell accumulation order. The two
    /// borrowed outputs remain valid until the next mutable workspace operation.
    pub fn evaluate(
        &mut self,
        prepared: &PreparedModel<'_>,
        observations: &[u8],
    ) -> (&Messages, &Counts) {
        self.evaluate_impl(prepared, observations, true, None)
    }

    /// Strict CPU messages and initial/emission counts for the optional CUDA
    /// transition-count backend. Transition cells retain their tiny initializer.
    pub fn evaluate_without_transitions(
        &mut self,
        prepared: &PreparedModel<'_>,
        observations: &[u8],
    ) -> (&Messages, &Counts) {
        self.evaluate_impl(prepared, observations, false, None)
    }

    /// Experimental messages using factors from the same parameter snapshot and
    /// state count as `prepared`. The caller must materialize those factors into
    /// the model before preparing it; mixing snapshots is not a supported input.
    /// EquivalentBackend owns both lifetimes and performs that synchronization.
    pub fn evaluate_structured(
        &mut self,
        prepared: &PreparedModel<'_>,
        observations: &[u8],
        factors: &psmc_core::structured::StructuredModel,
    ) -> (&Messages, &Counts) {
        self.evaluate_impl(prepared, observations, true, Some(factors))
    }

    fn evaluate_impl(
        &mut self,
        prepared: &PreparedModel<'_>,
        observations: &[u8],
        transitions: bool,
        factors: Option<&psmc_core::structured::StructuredModel>,
    ) -> (&Messages, &Counts) {
        assert!(!observations.is_empty(), "HMM sequence must be nonempty");
        assert!(
            observations.iter().all(|&symbol| symbol <= 2),
            "HMM observations must be encoded as 0, 1, or 2"
        );
        let model = prepared.model;
        let n = model.n;
        assert_eq!(self.messages.n, n, "workspace state count changed");
        let length = observations.len();
        let rows = length.checked_add(1).expect("HMM sequence is too long");
        let cells = rows.checked_mul(n).expect("HMM messages are too large");
        let square = n * n; // PreparedModel already checked this product.
        if self.avx.is_some() {
            assert_eq!(
                prepared.emission_transition_transpose.len(),
                3 * square,
                "AVX layout required; use workspace.prepare(model)"
            );
        }
        if factors.is_some() {
            self.scan.resize(n, 0.0);
        }
        let scan = &mut self.scan;
        let messages = &mut self.messages;
        messages.length = length;
        // Avoid amortized doubling when a later bootstrap block is slightly larger.
        // reserve_exact changes capacity only; resize and all arithmetic stay ordered.
        reserve_messages(&mut messages.forward, cells);
        reserve_messages(&mut messages.backward, cells);
        reserve_messages(&mut messages.scales, rows);
        messages.forward.resize(cells, 0.0);
        messages.backward.resize(cells, 0.0);
        messages.scales.resize(rows, 0.0);
        messages.forward[..n].fill(0.0);
        messages.backward[..n].fill(0.0);
        messages.scales[0] = 1.0;

        let first_emission = &model.emission[observations[0] as usize * n..][..n];
        let first = &mut messages.forward[n..2 * n];
        let mut sum = 0.0;
        for ((target, &initial), &emission) in
            first.iter_mut().zip(&model.initial).zip(first_emission)
        {
            *target = initial * emission;
            sum += *target;
        }
        for target in first {
            *target /= sum;
        }
        messages.scales[1] = sum;

        for u in 2..=length {
            let (earlier, later) = messages.forward.split_at_mut(u * n);
            let previous = &earlier[(u - 1) * n..];
            let current = &mut later[..n];
            let emission = &model.emission[observations[u - 1] as usize * n..][..n];
            if let Some(factors) = factors {
                factors.forward(current, previous, emission, scan);
                sum = 0.0;
                for &value in current.iter() {
                    sum += value;
                }
            } else if let Some(avx) = self.avx {
                avx.forward(current, previous, &model.transition, emission);
                sum = 0.0;
                for &value in current.iter() {
                    sum += value;
                }
            } else {
                sum = 0.0;
                for ((target, &emission), transition) in current
                    .iter_mut()
                    .zip(emission)
                    .zip(prepared.transpose.chunks_exact(n))
                {
                    let mut tmp = 0.0;
                    for (&forward, &a) in previous.iter().zip(transition) {
                        tmp += forward * a;
                    }
                    *target = emission * tmp;
                    sum += *target;
                }
            }
            if let Some(avx) = self.avx.filter(|_| n == 64) {
                avx.normalize(current, sum);
            } else {
                for target in current {
                    *target /= sum;
                }
            }
            messages.scales[u] = sum;
        }

        for target in &mut messages.backward[length * n..] {
            *target = 1.0 / messages.scales[length];
        }
        for u in (1..length).rev() {
            let (earlier, later) = messages.backward.split_at_mut((u + 1) * n);
            let current = &mut earlier[u * n..];
            let next = &later[..n];
            let product =
                &prepared.emission_transition[observations[u] as usize * square..][..square];
            if let Some(factors) = factors {
                let emission = &model.emission[observations[u] as usize * n..][..n];
                factors.backward(current, next, emission, messages.scales[u], scan);
            } else if let Some(avx) = self.avx {
                let transpose = &prepared.emission_transition_transpose
                    [observations[u] as usize * square..][..square];
                avx.backward(current, next, transpose, messages.scales[u]);
            } else {
                for (target, product_row) in current.iter_mut().zip(product.chunks_exact(n)) {
                    let mut tmp = 0.0;
                    for (&ae, &backward) in product_row.iter().zip(next) {
                        tmp += ae * backward;
                    }
                    *target = tmp / messages.scales[u];
                }
            }
        }
        self.finish_evaluation(prepared, observations, transitions)
    }

    // Also used after deinterleaving independent structured AVX lanes. All count
    // operations and per-sequence likelihood reductions retain their old order.
    fn finish_evaluation(
        &mut self,
        prepared: &PreparedModel<'_>,
        observations: &[u8],
        transitions: bool,
    ) -> (&Messages, &Counts) {
        let model = prepared.model;
        let n = model.n;
        let first_emission = &model.emission[observations[0] as usize * n..][..n];
        let messages = &mut self.messages;
        let mut backward_check = 0.0;
        for ((&initial, &backward), &emission) in model
            .initial
            .iter()
            .zip(&messages.backward[n..2 * n])
            .zip(first_emission)
        {
            backward_check += initial * backward * emission;
        }
        messages.backward_check = backward_check;

        let mut log_likelihood = 0.0;
        let mut product = 1.0;
        for &scale in &messages.scales[1..] {
            product *= scale;
            if product < TINY || product >= 1.0 / TINY {
                log_likelihood += ln(product);
                product = 1.0;
            }
        }
        log_likelihood += ln(product);
        messages.log_likelihood = log_likelihood;

        let counts = &mut self.counts;
        counts.a0.fill(0.0);
        counts.a.fill(TINY);
        counts.e.fill(TINY);
        counts.q0 = 0.0;
        transition_emission_counts(
            self.avx,
            prepared,
            observations,
            messages,
            counts,
            transitions,
        );
        for (((count, &initial), &emission), &backward) in counts
            .a0
            .iter_mut()
            .zip(&model.initial)
            .zip(first_emission)
            .zip(&messages.backward[n..2 * n])
        {
            *count += initial * emission * backward;
        }
        (messages, counts)
    }
}

fn transition_emission_counts(
    avx: Option<simd::Avx>,
    prepared: &PreparedModel<'_>,
    observations: &[u8],
    messages: &Messages,
    counts: &mut Counts,
    transitions: bool,
) {
    let n = prepared.model.n;
    let square = n * n;
    let length = observations.len();
    let sequence_counts = avx.filter(|_| transitions && n == 64);
    if let Some(avx) = sequence_counts {
        avx.counts_emissions64(
            &mut counts.a,
            observations,
            &messages.forward,
            &messages.backward,
            &prepared.emission_transition,
            &mut counts.e,
            &messages.scales,
        );
    }
    if sequence_counts.is_none() {
        for u in 1..length {
            let forward = &messages.forward[u * n..][..n];
            let backward = &messages.backward[u * n..][..n];
            let next_backward = &messages.backward[(u + 1) * n..][..n];
            let scale = messages.scales[u];
            let emission_counts = &mut counts.e[observations[u - 1] as usize * n..][..n];
            let product =
                &prepared.emission_transition[observations[u] as usize * square..][..square];
            if let Some(avx) = avx {
                if transitions {
                    avx.counts(&mut counts.a, forward, product, next_backward);
                }
                for ((count, &f), &b) in emission_counts.iter_mut().zip(forward).zip(backward) {
                    *count += f * b * scale;
                }
            } else {
                for ((((&fuk, &buk), emission_count), transition_counts), product_row) in forward
                    .iter()
                    .zip(backward)
                    .zip(emission_counts)
                    .zip(counts.a.chunks_exact_mut(n))
                    .zip(product.chunks_exact(n))
                {
                    if transitions {
                        for ((count, &ae), &next) in transition_counts
                            .iter_mut()
                            .zip(product_row)
                            .zip(next_backward)
                        {
                            *count += fuk * ae * next;
                        }
                    }
                    *emission_count += fuk * buk * scale;
                }
            }
        }
    }
}

#[cfg(test)]
mod tests;

pub mod engine;
pub use engine::CpuBackend;

fn reserve_messages(buffer: &mut Vec<f64>, needed: usize) {
    if needed > buffer.capacity() {
        buffer.reserve_exact(needed - buffer.len());
    }
}

pub mod equivalent;
pub use equivalent::EquivalentBackend;

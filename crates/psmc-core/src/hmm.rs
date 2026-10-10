//! Dense scalar translation of the pinned `khmm.c` forward/backward and EM counts.
//!
//! Positions are one-based, including the unused zero row from C. In particular,
//! backward messages divide by the *current* scale; the final observation has no
//! emission-count contribution; and every sequence receives its own tiny counts.
//! These are deliberate legacy semantics, not a conventional Baum–Welch rewrite.

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

use crate::math::ln;
use crate::model::Model;

const TINY: f64 = 1e-25;
const INF: f64 = 1e300;

#[derive(Clone, Debug)]
pub struct Messages {
    pub length: usize,
    pub n: usize,
    pub forward: Vec<f64>,
    pub backward: Vec<f64>,
    pub scales: Vec<f64>,
    pub log_likelihood: f64,
    /// The legacy underflow diagnostic; ordinarily within `1 +/- 1e-6`.
    pub backward_check: f64,
}

#[derive(Clone, Debug)]
pub struct Counts {
    pub n: usize,
    pub a0: Vec<f64>,
    /// Transition counts, source-major.
    pub a: Vec<f64>,
    /// Emission counts, symbol-major, including the missing-observation row.
    pub e: Vec<f64>,
    pub q0: f64,
}

fn square(n: usize) -> usize {
    n.checked_mul(n).expect("HMM state count is too large")
}

fn emission_length(n: usize) -> usize {
    n.checked_mul(3).expect("HMM state count is too large")
}

fn check_model(model: &Model) {
    assert!(model.n > 0, "HMM must have at least one state");
    assert_eq!(model.initial.len(), model.n);
    assert_eq!(model.transition.len(), square(model.n));
    assert_eq!(model.emission.len(), emission_length(model.n));
}

fn check_observations(observations: &[u8]) {
    assert!(!observations.is_empty(), "HMM sequence must be nonempty");
    assert!(
        observations.iter().all(|&symbol| symbol <= 2),
        "HMM observations must be encoded as 0, 1, or 2"
    );
}

impl Counts {
    /// Zero aggregate storage, as in `hmm_new_exp`; sequence tiny counts are added
    /// by `expectation`, not by this constructor.
    pub fn zero(n: usize) -> Self {
        assert!(n > 0, "HMM must have at least one state");
        Self {
            n,
            a0: vec![0.0; n],
            a: vec![0.0; square(n)],
            e: vec![0.0; emission_length(n)],
            q0: 0.0,
        }
    }

    fn check_shape(&self) {
        assert!(self.n > 0, "HMM must have at least one state");
        assert_eq!(self.a0.len(), self.n);
        assert_eq!(self.a.len(), square(self.n));
        assert_eq!(self.e.len(), emission_length(self.n));
    }

    /// Add one sequence in input order. Missing emission counts are deliberately
    /// omitted, and the normalizer is not updated until `normalizer` is called.
    pub fn add(&mut self, other: &Counts) {
        self.check_shape();
        other.check_shape();
        assert_eq!(self.n, other.n);
        let n = self.n;
        for k in 0..n {
            self.a0[k] += other.a0[k];
            for l in 0..n {
                self.a[k * n + l] += other.a[k * n + l];
            }
        }
        for b in 0..2 {
            for l in 0..n {
                self.e[b * n + l] += other.e[b * n + l];
            }
        }
    }

    /// Compute and retain the full-count entropy term from `hmm_Q0`.
    pub fn normalizer(&mut self) -> f64 {
        self.check_shape();
        let n = self.n;
        let mut sum = 0.0;
        for k in 0..n {
            let mut tmp = 0.0;
            for b in 0..2 {
                tmp += self.e[b * n + k];
            }
            for b in 0..2 {
                sum += self.e[b * n + k] * ln(self.e[b * n + k] / tmp);
            }
        }
        for k in 0..n {
            let mut tmp = 0.0;
            for l in 0..n {
                tmp += self.a[k * n + l];
            }
            for l in 0..n {
                sum += self.a[k * n + l] * ln(self.a[k * n + l] / tmp);
            }
        }
        self.q0 = sum;
        sum
    }

    /// Evaluate the legacy normalized Q. Initial and missing-observation counts
    /// are excluded. A nonpositive probability returns `-1e300`; a NaN is not
    /// caught by that comparison and propagates as in the C implementation.
    pub fn q(&self, model: &Model) -> f64 {
        self.check_shape();
        check_model(model);
        assert_eq!(self.n, model.n);
        let n = self.n;
        let mut sum = 0.0;
        for bb in 0..2 {
            for k in 0..n {
                let probability = model.emission[bb * n + k];
                if probability <= 0.0 {
                    return -INF;
                }
                sum += self.e[bb * n + k] * ln(probability);
            }
        }
        for k in 0..n {
            for l in 0..n {
                let probability = model.transition[k * n + l];
                if probability <= 0.0 {
                    return -INF;
                }
                sum += self.a[k * n + l] * ln(probability);
            }
        }
        sum - self.q0
    }
}

/// The C auxiliary array has `(symbol * n + source) * n + destination` layout.
pub fn pre_backward(model: &Model) -> Vec<f64> {
    check_model(model);
    let n = model.n;
    let mut ae = vec![0.0; square(n).checked_mul(3).expect("HMM is too large")];
    for b in 0..3 {
        for k in 0..n {
            for l in 0..n {
                ae[(b * n + k) * n + l] = model.emission[b * n + l] * model.transition[k * n + l];
            }
        }
    }
    ae
}

pub fn forward_backward(model: &Model, observations: &[u8], ae: &[f64]) -> Messages {
    check_model(model);
    check_observations(observations);
    let n = model.n;
    let length = observations.len();
    assert_eq!(
        ae.len(),
        square(n).checked_mul(3).expect("HMM is too large")
    );
    let rows = length.checked_add(1).expect("HMM sequence is too long");
    let cells = rows.checked_mul(n).expect("HMM messages are too large");
    let mut forward = vec![0.0; cells];
    let mut backward = vec![0.0; cells];
    let mut scales = vec![0.0; rows];
    let mut at = vec![0.0; square(n)];
    for k in 0..n {
        for l in 0..n {
            at[k * n + l] = model.transition[l * n + k];
        }
    }

    scales[0] = 1.0;
    let mut sum = 0.0;
    for k in 0..n {
        forward[n + k] = model.initial[k] * model.emission[observations[0] as usize * n + k];
        sum += forward[n + k];
    }
    for k in 0..n {
        forward[n + k] /= sum;
    }
    scales[1] = sum;

    for u in 2..=length {
        sum = 0.0;
        for k in 0..n {
            let mut tmp = 0.0;
            for l in 0..n {
                tmp += forward[(u - 1) * n + l] * at[k * n + l];
            }
            forward[u * n + k] = model.emission[observations[u - 1] as usize * n + k] * tmp;
            sum += forward[u * n + k];
        }
        for k in 0..n {
            forward[u * n + k] /= sum;
        }
        scales[u] = sum;
    }

    for k in 0..n {
        backward[length * n + k] = 1.0 / scales[length];
    }
    for u in (1..length).rev() {
        let ae_base = observations[u] as usize * n * n;
        for k in 0..n {
            let mut tmp = 0.0;
            for l in 0..n {
                tmp += ae[ae_base + k * n + l] * backward[(u + 1) * n + l];
            }
            backward[u * n + k] = tmp / scales[u];
        }
    }
    let mut backward_check = 0.0;
    for l in 0..n {
        backward_check +=
            model.initial[l] * backward[n + l] * model.emission[observations[0] as usize * n + l];
    }

    // Match `hmm_lk`'s product grouping; summing log(scale) per position changes
    // the floating-point answer even though the real-arithmetic formula agrees.
    let mut log_likelihood = 0.0;
    let mut prod = 1.0;
    for &scale in scales.iter().skip(1) {
        prod *= scale;
        if prod < TINY || prod >= 1.0 / TINY {
            log_likelihood += ln(prod);
            prod = 1.0;
        }
    }
    log_likelihood += ln(prod);

    Messages {
        length,
        n,
        forward,
        backward,
        scales,
        log_likelihood,
        backward_check,
    }
}

pub fn expectation(model: &Model, observations: &[u8], messages: &Messages, ae: &[f64]) -> Counts {
    check_model(model);
    check_observations(observations);
    let n = model.n;
    let length = observations.len();
    assert_eq!(messages.n, n);
    assert_eq!(messages.length, length);
    let rows = length.checked_add(1).expect("HMM sequence is too long");
    let cells = rows.checked_mul(n).expect("HMM messages are too large");
    assert_eq!(messages.forward.len(), cells);
    assert_eq!(messages.backward.len(), cells);
    assert_eq!(messages.scales.len(), rows);
    assert_eq!(
        ae.len(),
        square(n).checked_mul(3).expect("HMM is too large")
    );
    let mut counts = Counts::zero(n);
    counts.a.fill(TINY);
    counts.e.fill(TINY);

    for u in 1..length {
        let ss = messages.scales[u];
        let emission_base = observations[u - 1] as usize * n;
        let ae_base = observations[u] as usize * n * n;
        for k in 0..n {
            let fuk = messages.forward[u * n + k];
            for l in 0..n {
                counts.a[k * n + l] +=
                    fuk * ae[ae_base + k * n + l] * messages.backward[(u + 1) * n + l];
            }
            counts.e[emission_base + k] += fuk * messages.backward[u * n + k] * ss;
        }
    }
    for l in 0..n {
        counts.a0[l] += model.initial[l]
            * model.emission[observations[0] as usize * n + l]
            * messages.backward[n + l];
    }
    counts
}

#[cfg(test)]
mod tests {
    use super::*;

    fn toy_model() -> Model {
        Model {
            n: 2,
            params: vec![],
            t: vec![],
            sigma: vec![0.6, 0.4],
            c_pi: 0.0,
            c_sigma: 0.0,
            initial: vec![0.6, 0.4],
            transition: vec![0.7, 0.3, 0.2, 0.8],
            emission: vec![0.9, 0.25, 0.1, 0.75, 1.0, 1.0],
        }
    }

    fn close(actual: f64, expected: f64) {
        assert!(
            (actual - expected).abs() <= 1e-12 + 1e-10 * expected.abs(),
            "{actual:?} != {expected:?}"
        );
    }

    #[test]
    fn messages_and_legacy_counts_agree_with_enumerated_paths() {
        let model = toy_model();
        // Missing bins retain transitions; the final heterozygote is omitted
        // from E but still informs the posterior at every earlier position.
        let observations = [0, 2, 1, 0, 1];
        let length = observations.len();
        let ae = pre_backward(&model);
        let messages = forward_backward(&model, &observations, &ae);
        let counts = expectation(&model, &observations, &messages, &ae);
        let mut total = 0.0;
        let mut posterior = vec![0.0; length * 2];
        let mut transitions = [0.0; 4];
        let mut emissions = [0.0; 6];
        for path_id in 0..(1 << length) {
            let path: Vec<usize> = (0..length).map(|u| (path_id >> u) & 1).collect();
            let mut probability = model.initial[path[0]];
            for u in 0..length {
                probability *= model.emission[observations[u] as usize * 2 + path[u]];
                if u > 0 {
                    probability *= model.transition[path[u - 1] * 2 + path[u]];
                }
            }
            total += probability;
            for u in 0..length {
                posterior[u * 2 + path[u]] += probability;
                if u + 1 < length {
                    transitions[path[u] * 2 + path[u + 1]] += probability;
                    emissions[observations[u] as usize * 2 + path[u]] += probability;
                }
            }
        }
        close(messages.log_likelihood, ln(total));
        close(messages.backward_check, 1.0);
        assert_eq!(&messages.forward[..2], &[0.0, 0.0]);
        assert_eq!(&messages.backward[..2], &[0.0, 0.0]);
        assert_eq!(messages.scales[0], 1.0);
        for u in 0..length {
            for k in 0..2 {
                close(
                    messages.forward[(u + 1) * 2 + k]
                        * messages.backward[(u + 1) * 2 + k]
                        * messages.scales[u + 1],
                    posterior[u * 2 + k] / total,
                );
            }
        }
        for k in 0..2 {
            close(counts.a0[k], posterior[k] / total);
        }
        for (actual, expected) in counts.a.iter().zip(transitions) {
            close(*actual, expected / total + TINY);
        }
        for (actual, expected) in counts.e.iter().zip(emissions) {
            close(*actual, expected / total + TINY);
        }
    }

    #[test]
    fn one_position_and_repeated_records_preserve_tiny_counts() {
        let model = toy_model();
        let ae = pre_backward(&model);
        let observations = [2];
        let messages = forward_backward(&model, &observations, &ae);
        let counts = expectation(&model, &observations, &messages, &ae);
        assert_eq!(counts.a0, model.initial);
        assert!(counts.a.iter().all(|&x| x == TINY));
        assert!(counts.e.iter().all(|&x| x == TINY));
        let mut aggregate = Counts::zero(2);
        aggregate.add(&counts);
        aggregate.add(&counts);
        assert_eq!(aggregate.a0, vec![1.2, 0.8]);
        assert!(aggregate.a.iter().all(|&x| x == TINY + TINY));
        assert!(aggregate.e[..4].iter().all(|&x| x == TINY + TINY));
        assert_eq!(&aggregate.e[4..], &[0.0, 0.0]);
    }

    #[test]
    fn q_preserves_sentinel_nan_and_ignored_count_semantics() {
        let mut model = toy_model();
        let ae = pre_backward(&model);
        let observations = [0, 1, 0];
        let messages = forward_backward(&model, &observations, &ae);
        let sequence_counts = expectation(&model, &observations, &messages, &ae);
        let mut counts = Counts::zero(2);
        counts.add(&sequence_counts);
        counts.normalizer();
        let q = counts.q(&model);
        assert!(q.is_finite());
        counts.a0.fill(f64::NAN);
        counts.e[4..].fill(f64::NAN);
        assert_eq!(counts.q(&model), q);
        model.emission[0] = 0.0;
        assert_eq!(counts.q(&model), -INF);
        model.emission[0] = f64::NAN;
        assert!(counts.q(&model).is_nan());
        model.emission[0] = 0.9;
        model.transition[0] = -0.0;
        assert_eq!(counts.q(&model), -INF);
    }

    #[test]
    fn impossible_observations_propagate_nonfinite_reference_behavior() {
        let mut model = toy_model();
        model.emission[0..2].fill(0.0);
        let ae = pre_backward(&model);
        let messages = forward_backward(&model, &[0], &ae);
        assert_eq!(messages.log_likelihood, f64::NEG_INFINITY);
        assert!(messages.forward[2..].iter().all(|x| x.is_nan()));
        assert!(messages.backward[2..].iter().all(|&x| x == f64::INFINITY));
    }

    #[test]
    #[should_panic(expected = "HMM sequence must be nonempty")]
    fn rejects_empty_sequence() {
        let model = toy_model();
        let ae = pre_backward(&model);
        forward_backward(&model, &[], &ae);
    }

    #[test]
    #[should_panic(expected = "HMM observations must be encoded as 0, 1, or 2")]
    fn rejects_invalid_observation_encoding() {
        let model = toy_model();
        let ae = pre_backward(&model);
        forward_backward(&model, &[3], &ae);
    }
}

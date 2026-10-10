//! Structured real-arithmetic PSMC factors; only used by opt-in equivalent mode.
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

use crate::{
    Settings,
    math::{exp, ln},
    model::Model,
};

/// Factors and scratch storage owned by one fitting worker.
#[derive(Debug)]
pub struct StructuredModel {
    n: usize,
    lambda: Vec<f64>,
    alpha: Vec<f64>,
    beta: Vec<f64>,
    q_aux: Vec<f64>,
    lower: Vec<f64>,
    upper: Vec<f64>,
    diagonal: Vec<f64>,
    delta: Vec<f64>,
    tau: Vec<f64>,
}

impl StructuredModel {
    pub fn new(n: usize) -> Self {
        assert!(n > 0);
        Self {
            n,
            lambda: vec![0.0; n],
            alpha: vec![0.0; n + 1],
            beta: vec![0.0; n],
            q_aux: vec![0.0; n - 1],
            lower: vec![0.0; n],
            upper: vec![0.0; n],
            diagonal: vec![0.0; n],
            delta: vec![0.0; n],
            tau: vec![0.0; n],
        }
    }

    /// Update factors and scalar fields; transition is materialized separately.
    ///
    /// The workspace must have the model's state count. Model/settings validity
    /// and the unchanged missing-symbol emission row have the oracle's contract.
    pub fn update(&mut self, model: &mut Model, settings: &Settings) {
        let n = model.n;
        assert_eq!(settings.pattern.states(), n);
        assert_eq!(self.n, n, "workspace/model state count differs");
        // Bind exact-size slices once. This preserves safe bounds checks while
        // making loop bounds visible to the optimizer, as in fresh Vec storage.
        let lambda = &mut self.lambda[..n];
        let alpha = &mut self.alpha[..n + 1];
        let beta = &mut self.beta[..n];
        let q_aux = &mut self.q_aux[..n - 1];
        let tau = &mut self.tau[..n];

        let theta = model.params[0];
        let rho = model.params[1];
        let max_t = model.params[2];
        for k in 0..n {
            lambda[k] = model.params[settings.pattern.groups[k] + 3];
        }
        if let Some(input) = &settings.explicit_times {
            assert_eq!(input.len(), n);
            model.t[..n].copy_from_slice(input);
        } else {
            let grid_beta = ln(1.0 + max_t / settings.alpha) / (n - 1) as f64;
            for k in 0..n - 1 {
                model.t[k] = settings.alpha * (exp(grid_beta * k as f64) - 1.0);
            }
            model.t[n - 1] = max_t;
        }
        model.t[n] = 1000.0;

        let mut dt = 0.0;
        if settings.divergence.is_some() {
            dt = model.params[model.params.len() - 1];
            if dt < 0.0 {
                dt = 0.0;
            }
        }
        for k in 0..n {
            tau[k] = model.t[k + 1] - model.t[k];
        }
        alpha[0] = 1.0;
        for k in 1..n {
            alpha[k] = alpha[k - 1] * exp(-tau[k - 1] / lambda[k - 1]);
        }
        alpha[n] = 0.0;
        beta[0] = 0.0;
        for k in 1..n {
            beta[k] = beta[k - 1] + lambda[k - 1] * (1.0 / alpha[k] - 1.0 / alpha[k - 1]);
        }
        for l in 0..n - 1 {
            q_aux[l] = (alpha[l] - alpha[l + 1]) * (beta[l] - lambda[l] / alpha[l]) + tau[l];
        }
        model.c_pi = 0.0;
        for l in 0..n {
            model.c_pi += lambda[l] * (alpha[l] - alpha[l + 1]);
        }
        model.c_sigma = 1.0 / (model.c_pi * rho) + 0.5;

        let mut sum_t = 0.0;
        for k in 0..n {
            let ak1 = alpha[k] - alpha[k + 1];
            let lak = lambda[k];
            let cpik = ak1 * (sum_t + lak) - alpha[k + 1] * tau[k];
            let pik = cpik / model.c_pi;
            model.sigma[k] = (ak1 / (model.c_pi * rho) + pik / 2.0) / model.c_sigma;
            let mut avg_t = -ln(1.0 - pik / (model.c_sigma * model.sigma[k])) / rho;
            if avg_t.is_nan() || avg_t < sum_t || avg_t > sum_t + tau[k] {
                avg_t = sum_t + (lak - tau[k] * alpha[k + 1] / (alpha[k] - alpha[k + 1]));
            }
            let diagonal_q = (ak1 * ak1 * (beta[k] - lak / alpha[k]) + 2.0 * lak * ak1
                - 2.0 * alpha[k + 1] * tau[k])
                / cpik;
            let rate = pik / (model.c_sigma * model.sigma[k]);
            self.lower[k] = rate * (ak1 / cpik);
            self.upper[k] = if k + 1 < n {
                rate * (q_aux[k] / cpik)
            } else {
                0.0
            };
            self.diagonal[k] = rate * diagonal_q + (1.0 - rate);
            self.delta[k] = ak1;
            model.initial[k] = model.sigma[k];
            model.emission[k] = exp(-theta * (avg_t + dt));
            model.emission[n + k] = 1.0 - model.emission[k];
            sum_t += tau[k];
        }
    }
}

impl StructuredModel {
    /// A linear check covers every used triangular product, including underflow.
    /// Invalid factors are never clipped. The caller must use the literal path.
    pub fn eligible(&self, model: &Model) -> bool {
        let n = self.n;
        let positive = |x: f64| x.is_finite() && x > 0.0;
        if !model.emission[..2 * n].iter().copied().all(positive)
            || !model.initial.iter().copied().all(positive)
            || !self.diagonal.iter().copied().all(positive)
        {
            return false;
        }
        let mut minimum = f64::INFINITY;
        let mut maximum: f64 = 0.0;
        for k in 1..n {
            let q = self.q_aux[k - 1];
            if !positive(q) || !positive(self.lower[k]) {
                return false;
            }
            minimum = minimum.min(q);
            maximum = maximum.max(q);
            if !positive(self.lower[k] * minimum) || !positive(self.lower[k] * maximum) {
                return false;
            }
        }
        minimum = f64::INFINITY;
        maximum = 0.0;
        for k in (0..n - 1).rev() {
            let d = self.delta[k + 1];
            if !positive(d) || !positive(self.upper[k]) {
                return false;
            }
            minimum = minimum.min(d);
            maximum = maximum.max(d);
            if !positive(self.upper[k] * minimum) || !positive(self.upper[k] * maximum) {
                return false;
            }
        }
        true
    }

    pub fn materialize(&self, model: &mut Model) {
        let n = self.n;
        for k in 0..n {
            for l in 0..n {
                model.transition[k * n + l] = if l < k {
                    self.lower[k] * self.q_aux[l]
                } else if l > k {
                    self.upper[k] * self.delta[l]
                } else {
                    self.diagonal[k]
                };
            }
        }
    }

    pub fn forward(
        &self,
        output: &mut [f64],
        previous: &[f64],
        emission: &[f64],
        scratch: &mut [f64],
    ) {
        let n = self.n;
        let mut suffix = 0.0;
        for k in (0..n).rev() {
            scratch[k] = suffix;
            suffix += previous[k] * self.lower[k];
        }
        let mut prefix = 0.0;
        for k in 0..n {
            let lower = if k + 1 < n {
                self.q_aux[k] * scratch[k]
            } else {
                0.0
            };
            output[k] =
                emission[k] * (self.delta[k] * prefix + previous[k] * self.diagonal[k] + lower);
            prefix += previous[k] * self.upper[k];
        }
    }

    pub fn backward(
        &self,
        output: &mut [f64],
        next: &[f64],
        emission: &[f64],
        scale: f64,
        scratch: &mut [f64],
    ) {
        let n = self.n;
        let mut suffix = 0.0;
        for k in (0..n).rev() {
            scratch[k] = suffix;
            suffix += self.delta[k] * (emission[k] * next[k]);
        }
        let mut prefix = 0.0;
        for k in 0..n {
            let x = emission[k] * next[k];
            output[k] =
                (self.lower[k] * prefix + self.diagonal[k] * x + self.upper[k] * scratch[k])
                    / scale;
            if k + 1 < n {
                prefix += self.q_aux[k] * x;
            }
        }
    }

    pub fn q(&self, counts: &crate::hmm::Counts, model: &Model, margins: &Margins) -> f64 {
        let n = self.n;
        let mut sum = 0.0;
        for b in 0..2 {
            for k in 0..n {
                sum += counts.e[b * n + k] * ln(model.emission[b * n + k]);
            }
        }
        for k in 0..n {
            sum += counts.a[k * n + k] * ln(self.diagonal[k]);
            if k > 0 {
                sum += margins.lower_row[k] * ln(self.lower[k]);
                sum += margins.upper_col[k] * ln(self.delta[k]);
            }
            if k + 1 < n {
                sum += margins.lower_col[k] * ln(self.q_aux[k]);
                sum += margins.upper_row[k] * ln(self.upper[k]);
            }
        }
        sum - counts.q0
    }
}

pub struct Margins {
    lower_row: Vec<f64>,
    lower_col: Vec<f64>,
    upper_row: Vec<f64>,
    upper_col: Vec<f64>,
}
impl Margins {
    pub fn new(n: usize) -> Self {
        Self {
            lower_row: vec![0.0; n],
            lower_col: vec![0.0; n],
            upper_row: vec![0.0; n],
            upper_col: vec![0.0; n],
        }
    }
    pub fn update(&mut self, counts: &crate::hmm::Counts) {
        self.lower_row.fill(0.0);
        self.lower_col.fill(0.0);
        self.upper_row.fill(0.0);
        self.upper_col.fill(0.0);
        for k in 0..counts.n {
            for l in 0..counts.n {
                let c = counts.a[k * counts.n + l];
                if l < k {
                    self.lower_row[k] += c;
                    self.lower_col[l] += c;
                } else if l > k {
                    self.upper_row[k] += c;
                    self.upper_col[l] += c;
                }
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{Pattern, rng::LegacyRng};
    #[test]
    fn eligibility_rejects_negative_zero_and_underflow_products() {
        let settings = Settings {
            pattern: Pattern {
                text: "3".into(),
                groups: vec![0; 3],
                n_free: 1,
            },
            max_t: 15.0,
            alpha: 0.1,
            tr_ratio: 5.0,
            ran_init: 0.0,
            divergence: None,
            initial_params: None,
            explicit_times: None,
        };
        let mut model = Model::new(&settings, 2, 1000, &mut LegacyRng::new(42));
        let mut factors = StructuredModel::new(3);
        factors.update(&mut model, &settings);
        assert!(factors.eligible(&model));
        for bad in [0.0, -0.0, -1.0, f64::NAN, f64::INFINITY] {
            factors.update(&mut model, &settings);
            factors.lower[1] = bad;
            assert!(!factors.eligible(&model));
        }
        factors.update(&mut model, &settings);
        factors.lower[1] = f64::MIN_POSITIVE;
        factors.q_aux[0] = f64::MIN_POSITIVE;
        assert!(!factors.eligible(&model));
    }
}

#[cfg(test)]
mod sweep_tests {
    use super::*;
    use crate::{Pattern, hmm::Counts, rng::LegacyRng};
    #[test]
    fn candidate_sweep_preserves_model_and_normalized_q_within_declared_tolerance() {
        let mut rng = LegacyRng::new(20261010);
        let mut eligible = 0;
        for n in [2usize, 23, 64] {
            let settings = Settings {
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
            };
            let mut model = Model::new(&settings, 2, 1000, &mut rng);
            let mut factors = StructuredModel::new(n);
            let mut counts = Counts::zero(n);
            for c in counts.a.iter_mut().chain(&mut counts.e) {
                *c = 1e-25 + 100.0 * rng.next_f64();
            }
            counts.normalizer();
            let mut margins = Margins::new(n);
            margins.update(&counts);
            for _ in 0..100 {
                model.params[0] = 10.0_f64.powf(-4.0 + 3.0 * rng.next_f64());
                model.params[1] = 10.0_f64.powf(-5.0 + 3.0 * rng.next_f64());
                model.params[2] = 0.5 + 30.0 * rng.next_f64();
                for p in &mut model.params[3..] {
                    *p = 10.0_f64.powf(-1.0 + 2.0 * rng.next_f64());
                }
                model.update(&settings);
                let mut alternate = model.clone();
                factors.update(&mut alternate, &settings);
                if !factors.eligible(&alternate) {
                    continue;
                }
                eligible += 1;
                factors.materialize(&mut alternate);
                for (&a, &b) in model.transition.iter().zip(&alternate.transition) {
                    assert!((a - b).abs() <= 1e-14 + 1e-12 * a.abs().max(b.abs()));
                }
                let a = counts.q(&model);
                let b = factors.q(&counts, &alternate, &margins);
                assert!(a.is_finite() && b.is_finite());
                assert!(
                    (a - b).abs() <= 1e-14 + 1e-12 * a.abs().max(b.abs()),
                    "{a} {b}"
                );
            }
        }
        assert!(
            eligible > 100,
            "insufficient eligible sweep coverage: {eligible}"
        );
    }
}

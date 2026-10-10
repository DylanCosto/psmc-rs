//! Reusable scratch storage for the literal dense PSMC model calculation.
//!
//! The calculation below deliberately duplicates `Model::update`: that routine
//! remains the independent dense Rust oracle. Arithmetic, branch and loop order
//! follow `core.c::psmc_update_hmm` at source commit
//! 82fa2ada83ee463fe1251b562ae3d60e82d7ad6a. Only the lifetime of six scratch
//! allocations changes. This is not the later factored model/objective method.
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

/// Fixed-shape scratch storage owned by one fitting worker.
///
/// All scratch entries that the algorithm reads are written during each update:
/// lambda/tau/q cover 0..n, alpha covers 0..=n, beta covers 0..n and q_aux covers
/// 0..n-1. Thus buffers do not need zeroing between candidates, including after
/// invalid candidates. Nothing is cached across parameter vectors.
#[derive(Debug)]
pub struct ModelWorkspace {
    n: usize,
    lambda: Vec<f64>,
    alpha: Vec<f64>,
    beta: Vec<f64>,
    q_aux: Vec<f64>,
    q: Vec<f64>,
    tau: Vec<f64>,
}

impl ModelWorkspace {
    pub fn new(n: usize) -> Self {
        assert!(n > 0);
        Self {
            n,
            lambda: vec![0.0; n],
            alpha: vec![0.0; n + 1],
            beta: vec![0.0; n],
            q_aux: vec![0.0; n - 1],
            q: vec![0.0; n],
            tau: vec![0.0; n],
        }
    }

    /// Recompute every model field written by `Model::update` without allocating.
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
        let q = &mut self.q[..n];
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
            let mut tmp = ak1 / cpik;
            for l in 0..k {
                q[l] = tmp * q_aux[l];
            }
            q[k] = (ak1 * ak1 * (beta[k] - lak / alpha[k]) + 2.0 * lak * ak1
                - 2.0 * alpha[k + 1] * tau[k])
                / cpik;
            if k < n - 1 {
                tmp = q_aux[k] / cpik;
                for l in k + 1..n {
                    q[l] = (alpha[l] - alpha[l + 1]) * tmp;
                }
            }
            tmp = pik / (model.c_sigma * model.sigma[k]);
            for l in 0..n {
                model.transition[k * n + l] = tmp * q[l];
            }
            model.transition[k * n + k] = tmp * q[k] + (1.0 - tmp);
            model.initial[k] = model.sigma[k];
            model.emission[k] = exp(-theta * (avg_t + dt));
            model.emission[n + k] = 1.0 - model.emission[k];
            sum_t += tau[k];
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{Pattern, rng::LegacyRng};

    fn assert_values(label: &str, expected: &[f64], actual: &[f64]) {
        assert_eq!(expected.len(), actual.len(), "{label} shape");
        for (i, (&a, &b)) in expected.iter().zip(actual).enumerate() {
            if a.is_nan() {
                assert!(b.is_nan(), "{label}[{i}]: expected NaN, got {b:?}");
            } else {
                // Covers signed zero and infinity signs as well as finite bits.
                assert_eq!(a.to_bits(), b.to_bits(), "{label}[{i}]: {a:?} != {b:?}");
            }
        }
    }

    fn assert_model(expected: &Model, actual: &Model) {
        assert_eq!(expected.n, actual.n);
        for (label, a, b) in [
            ("params", &expected.params, &actual.params),
            ("t", &expected.t, &actual.t),
            ("sigma", &expected.sigma, &actual.sigma),
            ("initial", &expected.initial, &actual.initial),
            ("transition", &expected.transition, &actual.transition),
            ("emission", &expected.emission, &actual.emission),
        ] {
            assert_values(label, a, b);
        }
        assert_values(
            "normalizers",
            &[expected.c_pi, expected.c_sigma],
            &[actual.c_pi, actual.c_sigma],
        );
    }

    #[test]
    fn repeated_candidates_reuse_buffers_and_overwrite_poison() {
        let mut rng = LegacyRng::new(42);
        for n in [1, 2, 4, 23, 64] {
            for mode in 0..6 {
                let settings = Settings {
                    pattern: Pattern {
                        text: String::new(),
                        groups: (0..n).map(|k| k / 3).collect(),
                        n_free: (n + 2) / 3,
                    },
                    max_t: 15.0,
                    alpha: 0.1,
                    tr_ratio: 4.0,
                    ran_init: if mode >= 4 { 0.1 } else { 0.0 },
                    divergence: if mode % 2 == 1 { Some(0.7) } else { None },
                    initial_params: None,
                    explicit_times: if mode == 2 || mode == 3 {
                        Some((0..n).map(|i| i as f64 * 0.3).collect())
                    } else {
                        None
                    },
                };
                let initial = Model::new(&settings, 23, 177, &mut rng);
                let mut expected = initial.clone();
                let mut actual = initial.clone();
                let mut workspace = ModelWorkspace::new(n);
                let pointers = [
                    workspace.lambda.as_ptr(),
                    workspace.alpha.as_ptr(),
                    workspace.beta.as_ptr(),
                    workspace.q_aux.as_ptr(),
                    workspace.q.as_ptr(),
                    workspace.tau.as_ptr(),
                ];
                for trial in 0..12 {
                    expected.params.clone_from(&initial.params);
                    for (i, p) in expected.params.iter_mut().enumerate() {
                        *p *= 1.0 + i as f64 * 0.01 * trial as f64;
                    }
                    // Invalid optimizer trials must not poison later valid ones.
                    match trial {
                        2 => expected.params[0] = -0.0,
                        3 => expected.params[1] = 0.0,
                        5 => expected.params[3] = 0.0,
                        7 => expected.params[0] = f64::NAN,
                        9 => expected.params[1] = f64::INFINITY,
                        _ => {}
                    }
                    actual.params.clone_from(&expected.params);
                    // Deliberate stale scratch values detect any read-before-write.
                    for scratch in [
                        &mut workspace.lambda,
                        &mut workspace.alpha,
                        &mut workspace.beta,
                        &mut workspace.q_aux,
                        &mut workspace.q,
                        &mut workspace.tau,
                    ] {
                        scratch.fill(f64::NAN);
                    }
                    expected.update(&settings);
                    workspace.update(&mut actual, &settings);
                    assert_model(&expected, &actual);
                    assert_eq!(
                        pointers,
                        [
                            workspace.lambda.as_ptr(),
                            workspace.alpha.as_ptr(),
                            workspace.beta.as_ptr(),
                            workspace.q_aux.as_ptr(),
                            workspace.q.as_ptr(),
                            workspace.tau.as_ptr(),
                        ],
                        "scratch storage moved at n={n}, mode={mode}, trial={trial}"
                    );
                }
            }
        }
    }

    #[test]
    #[should_panic(expected = "workspace/model state count differs")]
    fn rejects_different_model_shape() {
        let settings = Settings {
            pattern: Pattern {
                text: "2".into(),
                groups: vec![0, 0],
                n_free: 1,
            },
            max_t: 15.0,
            alpha: 0.1,
            tr_ratio: 4.0,
            ran_init: 0.0,
            divergence: None,
            initial_params: None,
            explicit_times: None,
        };
        let mut model = Model::new(&settings, 1, 10, &mut LegacyRng::new(42));
        ModelWorkspace::new(4).update(&mut model, &settings);
    }
}

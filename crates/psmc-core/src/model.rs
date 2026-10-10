//! Literal translation of `core.c` and `psmc_cap_matrix` from lh3/psmc
//! commit 82fa2ada83ee463fe1251b562ae3d60e82d7ad6a.
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
    rng::LegacyRng,
};

#[derive(Clone, Debug)]
pub struct Model {
    /// Number of HMM states (upstream `hp->n`, or `pp->n + 1`).
    pub n: usize,
    pub params: Vec<f64>,
    /// All boundaries, including the finite terminal boundary 1000.
    pub t: Vec<f64>,
    pub sigma: Vec<f64>,
    pub c_pi: f64,
    pub c_sigma: f64,
    pub initial: Vec<f64>,
    /// Row-major source-state/destination-state matrix.
    pub transition: Vec<f64>,
    /// Symbol-major matrix: homozygous, heterozygous, missing.
    pub emission: Vec<f64>,
}

impl Model {
    pub fn new(settings: &Settings, sum_n: usize, sum_l: usize, rng: &mut LegacyRng) -> Self {
        let n = settings.pattern.states();
        assert!(n > 0);
        let n_params = settings.pattern.n_free + 3 + usize::from(settings.divergence.is_some());
        let mut params = vec![0.0; n_params];
        if let Some(input) = &settings.initial_params {
            assert_eq!(input.len(), n_params);
            params.copy_from_slice(input);
        } else {
            let theta = -ln(1.0 - sum_n as f64 / sum_l as f64);
            params[0] = theta;
            params[1] = theta / settings.tr_ratio;
            params[2] = settings.max_t;
            for k in 3..settings.pattern.n_free + 3 {
                // Draw even at zero amplitude: bootstrap/random initialization share RNG state.
                params[k] = 1.0 + (rng.next_f64() * 2.0 - 1.0) * settings.ran_init;
                if params[k] < 0.1 {
                    params[k] = 0.1;
                }
            }
            if let Some(dt) = settings.divergence {
                params[n_params - 1] = dt;
            }
        }
        let mut model = Self {
            n,
            params,
            t: vec![0.0; n + 1],
            sigma: vec![0.0; n],
            c_pi: 0.0,
            c_sigma: 0.0,
            initial: vec![0.0; n],
            transition: vec![0.0; n * n],
            emission: vec![0.0; 3 * n],
        };
        model.emission[2 * n..].fill(1.0);
        model.update(settings);
        model
    }

    pub fn update(&mut self, settings: &Settings) {
        let n = self.n;
        assert_eq!(settings.pattern.states(), n);
        let mut lambda = vec![0.0; n];
        let mut alpha = vec![0.0; n + 1];
        let mut beta = vec![0.0; n];
        let mut q_aux = vec![0.0; n - 1];
        let mut q = vec![0.0; n];
        let mut tau = vec![0.0; n];

        let theta = self.params[0];
        let rho = self.params[1];
        let max_t = self.params[2];
        for k in 0..n {
            lambda[k] = self.params[settings.pattern.groups[k] + 3];
        }
        if let Some(input) = &settings.explicit_times {
            assert_eq!(input.len(), n);
            self.t[..n].copy_from_slice(input);
        } else {
            let grid_beta = ln(1.0 + max_t / settings.alpha) / (n - 1) as f64;
            for k in 0..n - 1 {
                self.t[k] = settings.alpha * (exp(grid_beta * k as f64) - 1.0);
            }
            self.t[n - 1] = max_t;
        }
        self.t[n] = 1000.0;

        let mut dt = 0.0;
        if settings.divergence.is_some() {
            dt = self.params[self.params.len() - 1];
            if dt < 0.0 {
                dt = 0.0;
            }
        }
        for k in 0..n {
            tau[k] = self.t[k + 1] - self.t[k];
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
        self.c_pi = 0.0;
        for l in 0..n {
            self.c_pi += lambda[l] * (alpha[l] - alpha[l + 1]);
        }
        self.c_sigma = 1.0 / (self.c_pi * rho) + 0.5;

        let mut sum_t = 0.0;
        for k in 0..n {
            let ak1 = alpha[k] - alpha[k + 1];
            let lak = lambda[k];
            let cpik = ak1 * (sum_t + lak) - alpha[k + 1] * tau[k];
            let pik = cpik / self.c_pi;
            self.sigma[k] = (ak1 / (self.c_pi * rho) + pik / 2.0) / self.c_sigma;
            let mut avg_t = -ln(1.0 - pik / (self.c_sigma * self.sigma[k])) / rho;
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
            tmp = pik / (self.c_sigma * self.sigma[k]);
            for l in 0..n {
                self.transition[k * n + l] = tmp * q[l];
            }
            self.transition[k * n + k] = tmp * q[k] + (1.0 - tmp);
            self.initial[k] = self.sigma[k];
            self.emission[k] = exp(-theta * (avg_t + dt));
            self.emission[n + k] = 1.0 - self.emission[k];
            sum_t += tau[k];
        }
    }

    /// The separate legacy reporting/decoding formula, using the current model's grid.
    pub fn avg_times(&self, settings: &Settings) -> Vec<f64> {
        let n = self.n;
        let rho = self.params[1];
        let mut lambda = vec![0.0; n];
        let mut alpha = vec![0.0; n + 1];
        let mut tau = vec![0.0; n];
        let mut avg_t = vec![0.0; n];
        for k in 0..n {
            lambda[k] = self.params[settings.pattern.groups[k] + 3];
        }
        let mut dt = 0.0;
        if settings.divergence.is_some() {
            dt = self.params[self.params.len() - 1];
            if dt < 0.0 {
                dt = 0.0;
            }
        }
        for k in 0..n {
            tau[k] = self.t[k + 1] - self.t[k];
        }
        alpha[0] = 1.0;
        for k in 1..n {
            alpha[k] = alpha[k - 1] * exp(-tau[k - 1] / lambda[k - 1]);
        }
        alpha[n] = 0.0;
        let mut sum_t = 0.0;
        for k in 0..n {
            let ak1 = alpha[k] - alpha[k + 1];
            let lak = lambda[k];
            let pik = (ak1 * (sum_t + lak) - alpha[k + 1] * tau[k]) / self.c_pi;
            avg_t[k] = -ln(1.0 - pik / (self.c_sigma * self.sigma[k])) / rho;
            if avg_t[k].is_nan() || avg_t[k] < sum_t || avg_t[k] > sum_t + tau[k] {
                avg_t[k] = sum_t + (lak - tau[k] * alpha[k + 1] / (alpha[k] - alpha[k + 1]));
            }
            avg_t[k] += dt;
            sum_t += tau[k];
        }
        avg_t
    }

    /// Apply the legacy post-fit destination cap; initial/emission distributions stay intact.
    pub fn cap_transition(&mut self, cap: usize) {
        assert!(cap > 0 && cap < self.n - 1);
        for k in 0..self.n {
            let mut sum = 0.0;
            for l in cap..self.n {
                sum += self.transition[k * self.n + l];
                self.transition[k * self.n + l] = 0.0;
            }
            self.transition[k * self.n + cap] = sum;
        }
    }
}

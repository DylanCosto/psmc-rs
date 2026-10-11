//! Diagnostic-only algebra from docs/stable-model-protocol.md. Not linked into CLI.
use psmc_core::{Settings, model::Model};
fn small_functions(x: f64) -> (f64, f64, f64) {
    let r = (-x).exp();
    let d = -(-x).exp_m1();
    let (h, g) = if x < 0.5 {
        let mut h = x * x / 2.0;
        let mut g = h;
        let mut ht = h;
        let mut gt = g;
        for m in 2..32 {
            let m = m as f64;
            ht *= -x / (m + 1.0);
            gt *= -x * m / ((m + 1.0) * (m - 1.0));
            let hn = h + ht;
            let gn = g + gt;
            if hn == h && gn == g {
                break;
            }
            h = hn;
            g = gn;
        }
        (h, g)
    } else {
        (x - d, d - x * r)
    };
    let j = if x < 1.0 {
        let mut term = x * x * x / 6.0;
        let mut sum = term;
        for k in 1..32 {
            let m = (2 * k + 1) as f64;
            term *= x * x / ((m + 1.0) * (m + 2.0));
            let next = sum + term;
            if next == sum {
                break;
            }
            sum = next;
        }
        2.0 * r * sum
    } else {
        -(-2.0 * x).exp_m1() - 2.0 * x * r
    };
    (h, g, j)
}

pub fn update(m: &mut Model, s: &Settings) -> bool {
    let n = m.n;
    if n < 2 || m.params.iter().any(|p| !p.is_finite() || *p <= 0.0) {
        return false;
    }
    let theta = m.params[0];
    let rho = m.params[1];
    let mt = m.params[2];
    if let Some(t) = &s.explicit_times {
        m.t[..n].copy_from_slice(t);
    } else {
        let beta = (mt / s.alpha).ln_1p() / (n - 1) as f64;
        for k in 0..n - 1 {
            m.t[k] = s.alpha * (beta * k as f64).exp_m1();
        }
        m.t[n - 1] = mt;
    }
    m.t[n] = 1000.0;
    if m.t
        .windows(2)
        .any(|w| !w[0].is_finite() || w[0] < 0.0 || w[1] <= w[0])
    {
        return false;
    }
    let lam: Vec<_> = s.pattern.groups.iter().map(|&g| m.params[g + 3]).collect();
    let mut a = vec![0.0; n];
    let mut d = vec![0.0; n];
    let mut cp = vec![0.0; n];
    let mut v = vec![0.0; n];
    let mut q = vec![0.0; n];
    let mut mean = vec![0.0; n];
    let mut survival = 1.0;
    let mut b = 0.0;
    m.c_pi = 0.0;
    for k in 0..n {
        a[k] = survival;
        if k + 1 == n {
            d[k] = 1.0;
            cp[k] = m.t[k] + lam[k];
            v[k] = b + lam[k];
            mean[k] = lam[k];
        } else {
            let x = (m.t[k + 1] - m.t[k]) / lam[k];
            let r = (-x).exp();
            d[k] = -(-x).exp_m1();
            let (h, g, j) = small_functions(x);
            q[k] = d[k] * b + lam[k] * h;
            cp[k] = d[k] * m.t[k] + lam[k] * g;
            v[k] = d[k] * d[k] * b + lam[k] * j;
            mean[k] = lam[k] * g / d[k];
            b = r * b + lam[k] * d[k];
            survival *= r;
        }
        m.c_pi += lam[k] * a[k] * d[k];
    }
    m.c_sigma = 1.0 / (m.c_pi * rho) + 0.5;
    let dt = if s.divergence.is_some() {
        m.params[m.params.len() - 1].max(0.0)
    } else {
        0.0
    };
    for k in 0..n {
        let denominator = d[k] / rho + cp[k] / 2.0;
        let rate = cp[k] / denominator;
        let sigma = a[k] * (d[k] + rho * cp[k] / 2.0) / (1.0 + rho * m.c_pi / 2.0);
        m.sigma[k] = sigma;
        m.initial[k] = sigma;
        let mut avg = -(-rate).ln_1p() / rho;
        if !avg.is_finite() || avg < m.t[k] || avg > m.t[k + 1] {
            avg = m.t[k] + mean[k];
        }
        let exponent = -theta * (avg + dt);
        m.emission[k] = exponent.exp();
        m.emission[n + k] = -exponent.exp_m1();
        for l in 0..n {
            m.transition[k * n + l] = if l < k {
                d[k] / denominator * q[l]
            } else if l > k {
                q[k] / denominator * (a[l] / a[k]) * d[l]
            } else {
                (1.0 - rate) + v[k] / denominator
            };
        }
    }
    let valid = |v: &f64| v.is_finite() && *v >= 0.0 && *v <= 1.0;
    m.initial
        .iter()
        .chain(&m.transition)
        .chain(&m.emission)
        .all(valid)
        && (m.initial.iter().sum::<f64>() - 1.0).abs() <= 1e-12
        && m.transition
            .chunks(n)
            .all(|row| (row.iter().sum::<f64>() - 1.0).abs() <= 1e-12)
}

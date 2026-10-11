//! Equivalent-only segmented scans and checkpointed triangle-margin E-step.
//! Four lanes are contiguous state segments, never independent sequence pieces.
use psmc_core::{
    hmm::Counts,
    math::ln,
    model::Model,
    structured::{Margins, StructuredModel},
};
const BLOCK: usize = 256;

pub(crate) struct Result {
    pub counts: Counts,
    pub margins: Margins,
    pub likelihood: f64,
    pub backward_check: f64,
}

/// Exclusive prefix of a and exclusive suffix of b in state order. In memory,
/// lane j contains states j*segment .. (j+1)*segment. Padded states are zero.
fn scan(a: &[f64], b: &[f64], p: &mut [f64], s: &mut [f64], avx: bool) {
    #[cfg(target_arch = "x86_64")]
    if avx {
        // SAFETY: caller selected AVX using runtime detection; equal padded
        // buffers have lengths divisible by four. Loads/stores are unaligned.
        unsafe { scan_avx(a, b, p, s) };
        return;
    }
    let _ = avx;
    let segment = a.len() / 4;
    let mut pre = 0.0;
    let mut suf = 0.0;
    for k in 0..a.len() {
        let i = (k % segment) * 4 + k / segment;
        p[i] = pre;
        pre += a[i];
        let k = a.len() - 1 - k;
        let i = (k % segment) * 4 + k / segment;
        s[i] = suf;
        suf += b[i];
    }
}
#[cfg(target_arch = "x86_64")]
#[target_feature(enable = "avx")]
unsafe fn scan_avx(a: &[f64], b: &[f64], p: &mut [f64], s: &mut [f64]) {
    use std::arch::x86_64::*;
    unsafe {
        let mut pre = _mm256_setzero_pd();
        let mut suf = _mm256_setzero_pd();
        for i in (0..a.len()).step_by(4) {
            _mm256_storeu_pd(p.as_mut_ptr().add(i), pre);
            pre = _mm256_add_pd(pre, _mm256_loadu_pd(a.as_ptr().add(i)));
            let j = a.len() - 4 - i;
            _mm256_storeu_pd(s.as_mut_ptr().add(j), suf);
            suf = _mm256_add_pd(suf, _mm256_loadu_pd(b.as_ptr().add(j)));
        }
        let mut pt = [0.; 4];
        let mut st = [0.; 4];
        _mm256_storeu_pd(pt.as_mut_ptr(), pre);
        _mm256_storeu_pd(st.as_mut_ptr(), suf);
        let po = [0., pt[0], pt[0] + pt[1], (pt[0] + pt[1]) + pt[2]];
        let so = [(st[3] + st[2]) + st[1], st[3] + st[2], st[3], 0.];
        let pv = _mm256_loadu_pd(po.as_ptr());
        let sv = _mm256_loadu_pd(so.as_ptr());
        for i in (0..a.len()).step_by(4) {
            _mm256_storeu_pd(
                p.as_mut_ptr().add(i),
                _mm256_add_pd(pv, _mm256_loadu_pd(p.as_ptr().add(i))),
            );
            _mm256_storeu_pd(
                s.as_mut_ptr().add(i),
                _mm256_add_pd(sv, _mm256_loadu_pd(s.as_ptr().add(i))),
            );
        }
    }
}

struct Steps {
    n: usize,
    size: usize,
    segment: usize,
    avx: bool,
    l: Vec<f64>,
    u: Vec<f64>,
    d: Vec<f64>,
    q: Vec<f64>,
    diag: Vec<f64>,
    emission: Vec<f64>,
    initial: Vec<f64>,
    a: Vec<f64>,
    b: Vec<f64>,
    p: Vec<f64>,
    s: Vec<f64>,
    x: Vec<f64>,
    accumulated: Vec<f64>,
}
impl Steps {
    fn new(model: &Model, factors: &StructuredModel, avx: bool) -> Self {
        let n = model.n;
        let segment = n.div_ceil(4);
        let size = 4 * segment;
        let pack = |src: &[f64]| {
            let mut v = vec![0.; size];
            for (k, &x) in src.iter().enumerate() {
                v[(k % segment) * 4 + k / segment] = x;
            }
            v
        };
        let f = factors.message_factors();
        let mut emission = Vec::new();
        for row in model.emission.chunks_exact(n) {
            emission.extend(pack(row));
        }
        let mut accumulated = vec![1e-25; 8 * size];
        for k in 0..size {
            let i = (k % segment) * 4 + k / segment;
            accumulated[size + i] = k as f64 * 1e-25;
            accumulated[2 * size + i] = n.saturating_sub(k + 1) as f64 * 1e-25;
            accumulated[3 * size + i] = n.saturating_sub(k + 1) as f64 * 1e-25;
            accumulated[4 * size + i] = k as f64 * 1e-25;
        }
        Self {
            accumulated,
            n,
            size,
            segment,
            avx,
            l: pack(f.lower),
            u: pack(f.upper),
            d: pack(f.delta),
            q: pack(f.q_aux),
            diag: pack(f.diagonal),
            initial: pack(&model.initial),
            emission,
            a: vec![0.; size],
            b: vec![0.; size],
            p: vec![0.; size],
            s: vec![0.; size],
            x: vec![0.; size],
        }
    }
    fn index(&self, k: usize) -> usize {
        (k % self.segment) * 4 + k / self.segment
    }
    fn forward(&mut self, previous: &[f64], out: &mut [f64], symbol: u8, first: bool) -> f64 {
        #[cfg(target_arch = "x86_64")]
        if self.avx {
            // SAFETY: runtime AVX selection; all private buffers are padded to
            // size, emission has three rows, callers supply one padded row.
            return unsafe { self.forward_avx(previous, out, symbol, first) };
        }
        if first {
            for i in 0..self.size {
                out[i] = self.initial[i] * self.emission[symbol as usize * self.size + i];
            }
        } else {
            for i in 0..self.size {
                self.a[i] = previous[i] * self.u[i];
                self.b[i] = previous[i] * self.l[i];
            }
            scan(&self.a, &self.b, &mut self.p, &mut self.s, self.avx);
            for i in 0..self.size {
                out[i] = self.emission[symbol as usize * self.size + i]
                    * (self.d[i] * self.p[i] + previous[i] * self.diag[i] + self.q[i] * self.s[i]);
            }
        }
        let mut sum = 0.;
        for k in 0..self.n {
            sum += out[self.index(k)];
        }
        let inverse = 1. / sum;
        for x in out {
            *x *= inverse;
        }
        sum
    }
    fn backward_counts(
        &mut self,
        f: &[f64],
        next: &[f64],
        out: &mut [f64],
        symbol: u8,
        current: u8,
        scale: f64,
        cp: &[f64],
        cs: &[f64],
        result: &mut Result,
        dense: bool,
        model: &Model,
    ) {
        let mut vectorized = false;
        #[cfg(target_arch = "x86_64")]
        if self.avx {
            // SAFETY: same padded layout/runtime invariant as forward_avx.
            unsafe { self.backward_avx(f, next, out, symbol, current, scale, cp, cs) };
            vectorized = true;
        }
        if !vectorized {
            for i in 0..self.size {
                self.x[i] = self.emission[symbol as usize * self.size + i] * next[i];
                self.a[i] = self.q[i] * self.x[i];
                self.b[i] = self.d[i] * self.x[i];
            }
            scan(&self.a, &self.b, &mut self.p, &mut self.s, false);
            let inverse = 1. / scale;
            for i in 0..self.size {
                out[i] = (self.l[i] * self.p[i] + self.diag[i] * self.x[i] + self.u[i] * self.s[i])
                    * inverse;
                self.accumulated[i] += f[i] * self.diag[i] * self.x[i];
                self.accumulated[self.size + i] += f[i] * self.l[i] * self.p[i];
                self.accumulated[2 * self.size + i] += f[i] * self.u[i] * self.s[i];
                self.accumulated[3 * self.size + i] += self.x[i] * self.q[i] * cs[i];
                self.accumulated[4 * self.size + i] += self.x[i] * self.d[i] * cp[i];
                self.accumulated[(5 + current as usize) * self.size + i] += f[i] * out[i] * scale;
            }
        }
        if dense {
            for k in 0..self.n {
                let i = self.index(k);
                for j in 0..self.n {
                    if j != k {
                        result.counts.a[k * self.n + j] +=
                            f[i] * model.transition[k * self.n + j] * self.x[self.index(j)];
                    }
                }
            }
        }
    }
}

/// Only scales, forward checkpoints and one reconstructed block are retained.
/// Backward traversal consumes each transition exactly once in reverse site order.
/// Dense=true is a lazy Q fallback, using this same posterior and reduction order.
pub(crate) fn evaluate(
    model: &Model,
    observations: &[u8],
    factors: &StructuredModel,
    avx: bool,
    dense: bool,
) -> Result {
    assert!(!observations.is_empty() && observations.iter().all(|&x| x <= 2));
    let n = model.n;
    let len = observations.len();
    let blocks = len.div_ceil(BLOCK);
    let mut step = Steps::new(model, factors, avx);
    let size = step.size;
    let mut scales = vec![0.; len + 1];
    let mut checkpoints = vec![0.; blocks * size];
    let mut previous = vec![0.; size];
    let mut cur = vec![0.; size];
    for u in 1..=len {
        if (u - 1) % BLOCK == 0 {
            let b = (u - 1) / BLOCK;
            checkpoints[b * size..(b + 1) * size].copy_from_slice(&previous);
        }
        scales[u] = step.forward(&previous, &mut cur, observations[u - 1], u == 1);
        std::mem::swap(&mut previous, &mut cur);
    }
    let mut result = Result {
        counts: Counts::zero(n),
        margins: Margins::new(n),
        likelihood: 0.,
        backward_check: 0.,
    };
    result.counts.e.fill(1e-25);
    if dense {
        result.counts.a.fill(1e-25);
    } else {
        for k in 0..n {
            result.counts.a[k * n + k] = 1e-25;
        }
    }
    result.margins.tiny();
    let mut prod = 1.;
    for &scale in &scales[1..] {
        prod *= scale;
        if prod < 1e-25 || prod >= 1e25 {
            result.likelihood += ln(prod);
            prod = 1.;
        }
    }
    result.likelihood += ln(prod);
    let mut next = vec![1. / scales[len]; size];
    let mut backward = vec![0.; size];
    let mut forward = vec![0.; (BLOCK + 2) * size];
    let mut prefix = vec![0.; (BLOCK + 1) * size];
    let mut suffix = prefix.clone();
    for block in (0..blocks).rev() {
        let start = block * BLOCK + 1;
        let end = (start + BLOCK - 1).min(len);
        forward[..size].copy_from_slice(&checkpoints[block * size..(block + 1) * size]);
        for u in start..=(end + 1).min(len) {
            let offset = (u - start + 1) * size;
            let (left, right) = forward.split_at_mut(offset);
            step.forward(
                &left[offset - size..offset],
                &mut right[..size],
                observations[u - 1],
                u == 1,
            );
            if u > start {
                let j = (u - start - 1) * size;
                prefix[j..j + size].copy_from_slice(&step.p);
                suffix[j..j + size].copy_from_slice(&step.s);
            }
        }
        for u in (start..=end.min(len - 1)).rev() {
            let j = (u - start) * size;
            step.backward_counts(
                &forward[j + size..j + 2 * size],
                &next,
                &mut backward,
                observations[u],
                observations[u - 1],
                scales[u],
                &prefix[j..j + size],
                &suffix[j..j + size],
                &mut result,
                dense,
                model,
            );
            std::mem::swap(&mut next, &mut backward);
        }
    }
    for k in 0..n {
        let i = step.index(k);
        result.counts.a[k * n + k] = step.accumulated[i];
        result.margins.lower_row[k] = step.accumulated[size + i];
        result.margins.upper_row[k] = step.accumulated[2 * size + i];
        result.margins.lower_col[k] = step.accumulated[3 * size + i];
        result.margins.upper_col[k] = step.accumulated[4 * size + i];
        for symbol in 0..3 {
            result.counts.e[symbol * n + k] = step.accumulated[(5 + symbol) * size + i];
        }
        result.counts.a0[k] =
            step.initial[i] * step.emission[observations[0] as usize * size + i] * next[i];
        result.backward_check += result.counts.a0[k];
    }
    result
}

#[cfg(test)]
mod tests {
    use super::*;
    use psmc_core::{Pattern, Settings, hmm, rng::LegacyRng};
    fn close(a: &[f64], b: &[f64], abs: f64) {
        assert_eq!(a.len(), b.len());
        for (i, (&a, &b)) in a.iter().zip(b).enumerate() {
            assert!(
                a.is_finite()
                    && b.is_finite()
                    && (a - b).abs() <= abs + 1e-12 * a.abs().max(b.abs()),
                "{i}: {a} != {b}"
            );
        }
    }
    #[test]
    fn segmented_messages_margins_and_checkpoint_counts_match_dense() {
        for n in [2, 3, 4, 5, 7, 23, 64, 65] {
            for variant in 0..3 {
                let settings = Settings {
                    pattern: Pattern {
                        text: n.to_string(),
                        groups: vec![0; n],
                        n_free: 1,
                    },
                    max_t: 15.,
                    alpha: 0.1,
                    tr_ratio: 5.,
                    ran_init: 0.,
                    divergence: (variant == 1).then_some(0.3),
                    initial_params: None,
                    explicit_times: (variant == 2)
                        .then(|| (0..n).map(|i| 15. * i as f64 / (n - 1) as f64).collect()),
                };
                let dense_model = Model::new(&settings, 20, 10000, &mut LegacyRng::new(42));
                let mut model = dense_model.clone();
                let mut factors = StructuredModel::new(n);
                factors.update(&mut model, &settings);
                assert!(factors.eligible(&model));
                factors.materialize(&mut model);
                for len in [1, 2, 17, 255, 256, 257, 258, 511, 512, 513, 1024] {
                    let obs: Vec<_> = (0..len)
                        .map(|i| {
                            if i % 31 == 0 {
                                1
                            } else if i % 13 == 0 {
                                2
                            } else {
                                0
                            }
                        })
                        .collect();
                    let ae = hmm::pre_backward(&dense_model);
                    let msg = hmm::forward_backward(&dense_model, &obs, &ae);
                    let counts = hmm::expectation(&dense_model, &obs, &msg, &ae);
                    let mut margins = Margins::new(n);
                    margins.update(&counts);
                    for avx in [false, true] {
                        if avx && !crate::avx_available() {
                            continue;
                        }
                        let actual = evaluate(&model, &obs, &factors, avx, true);
                        close(&counts.a, &actual.counts.a, 1e-24);
                        close(&counts.e, &actual.counts.e, 1e-24);
                        close(&counts.a0, &actual.counts.a0, 1e-24);
                        close(&margins.lower_row, &actual.margins.lower_row, 1e-24);
                        close(&margins.upper_row, &actual.margins.upper_row, 1e-24);
                        close(&margins.lower_col, &actual.margins.lower_col, 1e-24);
                        close(&margins.upper_col, &actual.margins.upper_col, 1e-24);
                        close(
                            &[msg.log_likelihood, 1., counts.q(&dense_model)],
                            &[
                                actual.likelihood,
                                actual.backward_check,
                                factors.q(&actual.counts, &model, &actual.margins),
                            ],
                            1e-14,
                        );
                        let mut steps = Steps::new(&model, &factors, avx);
                        let size = steps.size;
                        let mut previous = vec![0.; size];
                        let mut output = previous.clone();
                        for u in 1..=len {
                            let scale = steps.forward(&previous, &mut output, obs[u - 1], u == 1);
                            close(&[scale], &[msg.scales[u]], 1e-14);
                            let unpack: Vec<_> = (0..n).map(|k| output[steps.index(k)]).collect();
                            close(&unpack, &msg.forward[u * n..(u + 1) * n], 1e-14);
                            std::mem::swap(&mut previous, &mut output);
                        }
                    }
                }
            }
        }
    }
}

#[cfg(target_arch = "x86_64")]
impl Steps {
    #[target_feature(enable = "avx")]
    unsafe fn forward_avx(
        &mut self,
        previous: &[f64],
        out: &mut [f64],
        symbol: u8,
        first: bool,
    ) -> f64 {
        use std::arch::x86_64::*;
        assert_eq!(previous.len(), self.size);
        assert_eq!(out.len(), self.size);
        assert!(symbol <= 2);
        unsafe {
            macro_rules! load {
                ($v:expr,$i:expr) => {
                    _mm256_loadu_pd($v.as_ptr().add($i))
                };
            }
            macro_rules! store {
                ($v:expr,$i:expr,$x:expr) => {
                    _mm256_storeu_pd($v.as_mut_ptr().add($i), $x)
                };
            }
            if !first {
                for i in (0..self.size).step_by(4) {
                    let f = load!(previous, i);
                    store!(self.a, i, _mm256_mul_pd(f, load!(self.u, i)));
                    store!(self.b, i, _mm256_mul_pd(f, load!(self.l, i)));
                }
                scan_avx(&self.a, &self.b, &mut self.p, &mut self.s);
            }
            let mut total = _mm256_setzero_pd();
            for i in (0..self.size).step_by(4) {
                let e = load!(self.emission, symbol as usize * self.size + i);
                let x = if first {
                    _mm256_mul_pd(load!(self.initial, i), e)
                } else {
                    let x = _mm256_add_pd(
                        _mm256_add_pd(
                            _mm256_mul_pd(load!(self.d, i), load!(self.p, i)),
                            _mm256_mul_pd(load!(previous, i), load!(self.diag, i)),
                        ),
                        _mm256_mul_pd(load!(self.q, i), load!(self.s, i)),
                    );
                    _mm256_mul_pd(e, x)
                };
                store!(out, i, x);
                total = _mm256_add_pd(total, x);
            }
            let mut totals = [0.; 4];
            store!(totals, 0, total);
            let sum = ((totals[0] + totals[1]) + totals[2]) + totals[3];
            let inverse = _mm256_set1_pd(1. / sum);
            for i in (0..self.size).step_by(4) {
                store!(out, i, _mm256_mul_pd(load!(out, i), inverse));
            }
            sum
        }
    }
    #[target_feature(enable = "avx")]
    unsafe fn backward_avx(
        &mut self,
        f: &[f64],
        next: &[f64],
        out: &mut [f64],
        symbol: u8,
        current: u8,
        scale: f64,
        cp: &[f64],
        cs: &[f64],
    ) {
        use std::arch::x86_64::*;
        assert!(
            [f.len(), next.len(), out.len(), cp.len(), cs.len()]
                .iter()
                .all(|&n| n == self.size)
        );
        assert!(symbol <= 2 && current <= 2);
        unsafe {
            macro_rules! load {
                ($v:expr,$i:expr) => {
                    _mm256_loadu_pd($v.as_ptr().add($i))
                };
            }
            macro_rules! store {
                ($v:expr,$i:expr,$x:expr) => {
                    _mm256_storeu_pd($v.as_mut_ptr().add($i), $x)
                };
            }
            macro_rules! accumulate {
                ($row:expr,$i:expr,$x:expr) => {{
                    let j = $row * self.size + $i;
                    store!(
                        self.accumulated,
                        j,
                        _mm256_add_pd(load!(self.accumulated, j), $x)
                    );
                }};
            }
            for i in (0..self.size).step_by(4) {
                let x = _mm256_mul_pd(
                    load!(self.emission, symbol as usize * self.size + i),
                    load!(next, i),
                );
                store!(self.x, i, x);
                store!(self.a, i, _mm256_mul_pd(load!(self.q, i), x));
                store!(self.b, i, _mm256_mul_pd(load!(self.d, i), x));
            }
            scan_avx(&self.a, &self.b, &mut self.p, &mut self.s);
            let inverse = _mm256_set1_pd(1. / scale);
            let scale = _mm256_set1_pd(scale);
            for i in (0..self.size).step_by(4) {
                let x = load!(self.x, i);
                let fv = load!(f, i);
                let diag = load!(self.diag, i);
                let l = load!(self.l, i);
                let u = load!(self.u, i);
                let p = load!(self.p, i);
                let s = load!(self.s, i);
                let bv = _mm256_mul_pd(
                    _mm256_add_pd(
                        _mm256_add_pd(_mm256_mul_pd(l, p), _mm256_mul_pd(diag, x)),
                        _mm256_mul_pd(u, s),
                    ),
                    inverse,
                );
                store!(out, i, bv);
                accumulate!(0, i, _mm256_mul_pd(_mm256_mul_pd(fv, diag), x));
                accumulate!(1, i, _mm256_mul_pd(_mm256_mul_pd(fv, l), p));
                accumulate!(2, i, _mm256_mul_pd(_mm256_mul_pd(fv, u), s));
                accumulate!(
                    3,
                    i,
                    _mm256_mul_pd(_mm256_mul_pd(x, load!(self.q, i)), load!(cs, i))
                );
                accumulate!(
                    4,
                    i,
                    _mm256_mul_pd(_mm256_mul_pd(x, load!(self.d, i)), load!(cp, i))
                );
                accumulate!(
                    5 + current as usize,
                    i,
                    _mm256_mul_pd(_mm256_mul_pd(fv, bv), scale)
                );
            }
        }
    }
}

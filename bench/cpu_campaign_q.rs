//! Isolated Q candidate; the dense Counts::q remains the numerical oracle.
use psmc_core::{hmm::Counts, math::ln, model::Model};

// Replaced in the disposable candidate tree: 0=flat, 1=last per position,
// 2=bounded direct map. No transcendental approximation or sum regrouping.
const MODE: usize = 0;
const SLOTS: usize = 8192;
#[derive(Clone, Copy, Default)]
struct Entry { bits: u64, logarithm: f64 }
pub struct QCache { entries: Vec<Entry>, n: usize }
impl QCache {
    pub fn new(n: usize) -> Self {
        let length = match MODE { 1 => n * n + 2 * n, 2 => SLOTS, _ => 0 };
        Self { entries: vec![Entry::default(); length], n }
    }
    #[inline]
    fn log(&mut self, probability: f64, position: usize) -> f64 {
        // Probability <=0 is checked by the caller at the original point.
        // Zero bits initialize empty slots and can never match a positive input.
        // Nonfinite calls always execute the original libm operation.
        if MODE == 0 || !probability.is_finite() { return ln(probability); }
        let bits = probability.to_bits();
        let index = if MODE == 1 { position } else {
            (bits.wrapping_mul(0x9e3779b97f4a7c15) >> (64 - 13)) as usize
        };
        let entry = &mut self.entries[index];
        if entry.bits != bits {
            *entry = Entry { bits, logarithm: ln(probability) };
        }
        entry.logarithm
    }
    pub fn q(&mut self, counts: &Counts, model: &Model) -> f64 {
        let n = self.n;
        assert!(n > 0);
        assert_eq!(counts.n, n);
        assert_eq!(model.n, n);
        assert_eq!(counts.a0.len(), n);
        assert_eq!(counts.a.len(), n * n);
        assert_eq!(counts.e.len(), 3 * n);
        assert_eq!(model.initial.len(), n);
        assert_eq!(model.transition.len(), n * n);
        assert_eq!(model.emission.len(), 3 * n);
        let mut sum = 0.0;
        for (position, (&count, &probability)) in counts.e[..2*n].iter().zip(&model.emission[..2*n]).enumerate() {
            if probability <= 0.0 { return -1e300; }
            sum += count * self.log(probability, position);
        }
        for (position, (&count, &probability)) in counts.a.iter().zip(&model.transition).enumerate() {
            if probability <= 0.0 { return -1e300; }
            sum += count * self.log(probability, 2*n + position);
        }
        sum - counts.q0
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn equal(a: f64, b: f64) {
        assert!(a.to_bits() == b.to_bits() || a.is_nan() && b.is_nan(), "{a:?} != {b:?}");
    }
    #[test]
    fn exact_probability_reuse_preserves_q_and_invalid_order() {
        for n in [1, 2, 3, 4, 7, 23, 64, 65] {
            let mut cache = QCache::new(n);
            let mut counts = Counts::zero(n);
            let mut model = Model { n, params: vec![], t: vec![], sigma: vec![], c_pi: 0.0, c_sigma: 0.0,
                initial: vec![1.0 / n as f64; n], transition: vec![0.5; n*n], emission: vec![0.25; 3*n] };
            let values = [0.5, 0.25, f64::MIN_POSITIVE, f64::from_bits(1), 1.0, 0.9999999999999999,
                          f64::INFINITY, f64::NAN, 0.0, -0.0, -0.1];
            for round in 0..200 {
                for (i, v) in model.transition.iter_mut().enumerate() { *v = values[(i + round/3) % values.len()]; }
                for (i, v) in model.emission[..2*n].iter_mut().enumerate() { *v = values[(i*3 + round/5) % values.len()]; }
                for (i,v) in counts.a.iter_mut().enumerate() { *v = (i+round+1) as f64 * 1e-25; }
                counts.e.fill((round+1) as f64 * 0.0001);
                counts.q0 = -(round as f64);
                equal(counts.q(&model), cache.q(&counts, &model));
                // Cache reuse must remain valid when counts change: only logs are cached.
                counts.a.fill(1.75);
                equal(counts.q(&model), cache.q(&counts, &model));
                model.transition.fill(0.5);
                model.emission.fill(0.25);
                equal(counts.q(&model), cache.q(&counts, &model));
            }
        }
    }
    #[test]
    fn replacement_collision_never_returns_a_different_probability_log() {
        let mut cache = QCache::new(4);
        for pass in 0..3 {
            for i in 1..25_000 {
                let value = if i % 2 == 0 { (i+pass) as f64 / 30_000.0 } else { 0.5 };
                equal(ln(value), cache.log(value, i % 24));
            }
        }
    }
}

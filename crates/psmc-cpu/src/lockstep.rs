//! Four independent records per AVX vector, with bounded message reconstruction.
//! Counts are accumulated in ascending site order using the existing CPU kernel.
use crate::{PreparedModel, Workspace};
use psmc_core::{hmm::Counts, structured::StructuredModel};
const BLOCK: usize = 256;
#[derive(Clone)]
pub(crate) struct LaneResult {
    pub counts: Counts,
    pub likelihood: f64,
    pub backward_check: f64,
}
#[derive(Default)]
pub(crate) struct Lockstep {
    scales: Vec<[f64; 4]>,
    forward_checkpoints: Vec<[f64; 4]>,
    backward_checkpoints: Vec<[f64; 4]>,
    forward: Vec<[f64; 4]>,
    backward: Vec<[f64; 4]>,
}
fn resize(v: &mut Vec<[f64; 4]>, len: usize) {
    if len > v.capacity() {
        v.reserve_exact(len - v.len());
    }
    v.resize(len, [0.; 4]);
}
impl Lockstep {
    pub(crate) fn evaluate(
        &mut self,
        workspace: &mut Workspace,
        prepared: &PreparedModel<'_>,
        records: [&[u8]; 4],
        factors: &StructuredModel,
    ) -> [LaneResult; 4] {
        assert!(workspace.avx.is_some(), "lockstep needs detected AVX");
        let n = prepared.model.n;
        let len = records[0].len();
        assert!(len > 0);
        assert!(
            records
                .iter()
                .all(|r| r.len() == len && r.iter().all(|&v| v <= 2))
        );
        let blocks = (len - 1).div_ceil(BLOCK).max(1);
        resize(
            &mut self.scales,
            len.checked_add(1).expect("record too long"),
        );
        let checkpoint_cells = blocks.checked_mul(n).expect("checkpoints too large");
        resize(&mut self.forward_checkpoints, checkpoint_cells);
        resize(&mut self.backward_checkpoints, checkpoint_cells);
        let cells = (BLOCK + 2).checked_mul(n).expect("message block too large");
        resize(&mut self.forward, cells);
        resize(&mut self.backward, cells);
        #[cfg(target_arch = "x86_64")]
        // SAFETY: actual CPU/OS AVX capability checked above; nonempty records,
        // equal lengths and valid symbols checked. PreparedModel checks model
        // dimensions. Vector storage is exactly [f64;4], accessed unaligned.
        unsafe {
            self.run(workspace, prepared, records, factors, blocks)
        }
        #[cfg(not(target_arch = "x86_64"))]
        unreachable!("AVX capability is never present on this architecture")
    }
    #[cfg(target_arch = "x86_64")]
    #[target_feature(enable = "avx")]
    unsafe fn run(
        &mut self,
        workspace: &mut Workspace,
        prepared: &PreparedModel<'_>,
        records: [&[u8]; 4],
        factors: &StructuredModel,
        blocks: usize,
    ) -> [LaneResult; 4] {
        use std::arch::x86_64::*;
        let m = prepared.model;
        let n = m.n;
        let len = records[0].len();
        let f = factors.message_factors();
        assert_eq!(f.lower.len(), n);
        assert_eq!(f.upper.len(), n);
        assert_eq!(f.diagonal.len(), n);
        assert_eq!(f.delta.len(), n);
        assert_eq!(f.q_aux.len(), n - 1);
        let mut emissions = vec![[0.; 4]; 81 * n];
        for code in 0..81 {
            let mut z = code;
            let mut symbols = [0; 4];
            for s in &mut symbols {
                *s = z % 3;
                z /= 3;
            }
            for k in 0..n {
                emissions[code * n + k] = std::array::from_fn(|l| m.emission[symbols[l] * n + k]);
            }
        }
        let code = |u: usize| {
            records[0][u] as usize
                + 3 * records[1][u] as usize
                + 9 * records[2][u] as usize
                + 27 * records[3][u] as usize
        };
        let mut prev = vec![[0.; 4]; n];
        let mut cur = prev.clone();
        let mut scratch = prev.clone();
        self.scales[0] = [1.; 4];
        self.forward_checkpoints[..n].fill([0.; 4]);
        // SAFETY: all vector loads/stores below address one complete [f64;4].
        // Site/state/checkpoint indices are bounded by the checked dimensions.
        unsafe {
            for u in 1..=len {
                self.scales[u] = if u == 1 {
                    initial(&mut cur, &emissions[code(0) * n..][..n], &m.initial)
                } else {
                    forward(
                        &prev,
                        &mut cur,
                        &emissions[code(u - 1) * n..][..n],
                        &f,
                        &mut scratch,
                    )
                };
                if u % BLOCK == 0 && u / BLOCK < blocks {
                    let b = u / BLOCK;
                    self.forward_checkpoints[b * n..(b + 1) * n].copy_from_slice(&cur);
                }
                std::mem::swap(&mut prev, &mut cur);
            }
            let end = _mm256_div_pd(
                _mm256_set1_pd(1.),
                _mm256_loadu_pd(self.scales[len].as_ptr()),
            );
            for k in 0..n {
                _mm256_storeu_pd(prev[k].as_mut_ptr(), end);
            }
            self.backward_checkpoints[(blocks - 1) * n..blocks * n].copy_from_slice(&prev);
            for u in (1..len).rev() {
                backward(
                    &prev,
                    &mut cur,
                    &emissions[code(u) * n..][..n],
                    &f,
                    self.scales[u],
                    &mut scratch,
                );
                if u > 1 && (u - 1) % BLOCK == 0 {
                    let b = (u - 1) / BLOCK - 1;
                    self.backward_checkpoints[b * n..(b + 1) * n].copy_from_slice(&cur);
                }
                std::mem::swap(&mut prev, &mut cur);
            }
            // prev now holds backward probabilities for the first site.
            let mut result = std::array::from_fn(|lane| {
                let mut counts = Counts::zero(n);
                counts.a.fill(crate::TINY);
                counts.e.fill(crate::TINY);
                let mut check = 0.;
                for k in 0..n {
                    let e = m.emission[records[lane][0] as usize * n + k];
                    check += m.initial[k] * prev[k][lane] * e;
                    counts.a0[k] = m.initial[k] * e * prev[k][lane];
                }
                let mut ll = 0.;
                let mut product = 1.;
                for row in &self.scales[1..] {
                    product *= row[lane];
                    if product < crate::TINY || product >= 1. / crate::TINY {
                        ll += psmc_core::math::ln(product);
                        product = 1.;
                    }
                }
                ll += psmc_core::math::ln(product);
                LaneResult {
                    counts,
                    likelihood: ll,
                    backward_check: check,
                }
            });
            // Reconstruct bounded blocks in ASCENDING order, with one overlap
            // site to supply each final transition. Exact checkpoints reproduce
            // the same messages; no partial-count sums or extra TINY additions.
            for b in 0..blocks {
                let start = b * BLOCK + 1;
                let end = (start + BLOCK).min(len);
                let length = end - start + 1;
                self.forward[..n].copy_from_slice(&self.forward_checkpoints[b * n..(b + 1) * n]);
                for u in start..=end {
                    let local = u - start + 1;
                    let (left, right) = self.forward.split_at_mut(local * n);
                    let out = &mut right[..n];
                    let scale = if u == 1 {
                        initial(out, &emissions[code(0) * n..][..n], &m.initial)
                    } else {
                        forward(
                            &left[(local - 1) * n..local * n],
                            out,
                            &emissions[code(u - 1) * n..][..n],
                            &f,
                            &mut scratch,
                        )
                    };
                    debug_assert_eq!(scale, self.scales[u]);
                }
                self.backward[length * n..(length + 1) * n]
                    .copy_from_slice(&self.backward_checkpoints[b * n..(b + 1) * n]);
                for u in (start..end).rev() {
                    let local = u - start + 1;
                    let (left, right) = self.backward.split_at_mut((local + 1) * n);
                    backward(
                        &right[..n],
                        &mut left[local * n..(local + 1) * n],
                        &emissions[code(u) * n..][..n],
                        &f,
                        self.scales[u],
                        &mut scratch,
                    );
                }
                let cells = (length + 1) * n;
                for lane in 0..4 {
                    let msg = &mut workspace.messages;
                    msg.length = length;
                    for (out, input) in [
                        (&mut msg.forward, &self.forward),
                        (&mut msg.backward, &self.backward),
                    ] {
                        crate::reserve_messages(out, cells);
                        out.resize(cells, 0.);
                        for (o, v) in out.iter_mut().zip(input) {
                            *o = v[lane];
                        }
                    }
                    crate::reserve_messages(&mut msg.scales, length + 1);
                    msg.scales.resize(length + 1, 0.);
                    msg.scales[0] = 1.;
                    for u in 1..=length {
                        msg.scales[u] = self.scales[start + u - 1][lane];
                    }
                    crate::transition_emission_counts(
                        workspace.avx,
                        prepared,
                        &records[lane][start - 1..end],
                        msg,
                        &mut result[lane].counts,
                        true,
                    );
                }
            }
            result
        }
    }
}

#[cfg(target_arch = "x86_64")]
mod steps {
    use psmc_core::structured::MessageFactors;
    use std::arch::x86_64::*;
    #[target_feature(enable = "avx")]
    pub(super) unsafe fn initial(
        out: &mut [[f64; 4]],
        emission: &[[f64; 4]],
        initial: &[f64],
    ) -> [f64; 4] {
        unsafe {
            let mut sum = _mm256_setzero_pd();
            for k in 0..out.len() {
                let v = _mm256_mul_pd(
                    _mm256_set1_pd(initial[k]),
                    _mm256_loadu_pd(emission[k].as_ptr()),
                );
                _mm256_storeu_pd(out[k].as_mut_ptr(), v);
                sum = _mm256_add_pd(sum, v);
            }
            for row in out {
                let v = _mm256_div_pd(_mm256_loadu_pd(row.as_ptr()), sum);
                _mm256_storeu_pd(row.as_mut_ptr(), v);
            }
            let mut s = [0.; 4];
            _mm256_storeu_pd(s.as_mut_ptr(), sum);
            s
        }
    }
    #[target_feature(enable = "avx")]
    pub(super) unsafe fn forward(
        prev: &[[f64; 4]],
        out: &mut [[f64; 4]],
        e: &[[f64; 4]],
        f: &MessageFactors<'_>,
        scratch: &mut [[f64; 4]],
    ) -> [f64; 4] {
        unsafe {
            let n = out.len();
            let zero = _mm256_setzero_pd();
            let mut suffix = zero;
            for k in (0..n).rev() {
                _mm256_storeu_pd(scratch[k].as_mut_ptr(), suffix);
                suffix = _mm256_add_pd(
                    suffix,
                    _mm256_mul_pd(
                        _mm256_loadu_pd(prev[k].as_ptr()),
                        _mm256_set1_pd(f.lower[k]),
                    ),
                );
            }
            let mut prefix = zero;
            let mut sum = zero;
            for k in 0..n {
                let previous = _mm256_loadu_pd(prev[k].as_ptr());
                let lower = if k + 1 < n {
                    _mm256_mul_pd(
                        _mm256_set1_pd(f.q_aux[k]),
                        _mm256_loadu_pd(scratch[k].as_ptr()),
                    )
                } else {
                    zero
                };
                let v = _mm256_mul_pd(
                    _mm256_loadu_pd(e[k].as_ptr()),
                    _mm256_add_pd(
                        _mm256_add_pd(
                            _mm256_mul_pd(_mm256_set1_pd(f.delta[k]), prefix),
                            _mm256_mul_pd(previous, _mm256_set1_pd(f.diagonal[k])),
                        ),
                        lower,
                    ),
                );
                _mm256_storeu_pd(out[k].as_mut_ptr(), v);
                sum = _mm256_add_pd(sum, v);
                prefix = _mm256_add_pd(prefix, _mm256_mul_pd(previous, _mm256_set1_pd(f.upper[k])));
            }
            for row in out {
                let v = _mm256_div_pd(_mm256_loadu_pd(row.as_ptr()), sum);
                _mm256_storeu_pd(row.as_mut_ptr(), v);
            }
            let mut s = [0.; 4];
            _mm256_storeu_pd(s.as_mut_ptr(), sum);
            s
        }
    }
    #[target_feature(enable = "avx")]
    pub(super) unsafe fn backward(
        next: &[[f64; 4]],
        out: &mut [[f64; 4]],
        e: &[[f64; 4]],
        f: &MessageFactors<'_>,
        scale: [f64; 4],
        scratch: &mut [[f64; 4]],
    ) {
        unsafe {
            let n = out.len();
            let zero = _mm256_setzero_pd();
            let mut suffix = zero;
            for k in (0..n).rev() {
                _mm256_storeu_pd(scratch[k].as_mut_ptr(), suffix);
                let x = _mm256_mul_pd(
                    _mm256_loadu_pd(e[k].as_ptr()),
                    _mm256_loadu_pd(next[k].as_ptr()),
                );
                suffix = _mm256_add_pd(suffix, _mm256_mul_pd(_mm256_set1_pd(f.delta[k]), x));
            }
            let mut prefix = zero;
            let scale = _mm256_loadu_pd(scale.as_ptr());
            for k in 0..n {
                let x = _mm256_mul_pd(
                    _mm256_loadu_pd(e[k].as_ptr()),
                    _mm256_loadu_pd(next[k].as_ptr()),
                );
                let v = _mm256_div_pd(
                    _mm256_add_pd(
                        _mm256_add_pd(
                            _mm256_mul_pd(_mm256_set1_pd(f.lower[k]), prefix),
                            _mm256_mul_pd(_mm256_set1_pd(f.diagonal[k]), x),
                        ),
                        _mm256_mul_pd(
                            _mm256_set1_pd(f.upper[k]),
                            _mm256_loadu_pd(scratch[k].as_ptr()),
                        ),
                    ),
                    scale,
                );
                _mm256_storeu_pd(out[k].as_mut_ptr(), v);
                if k + 1 < n {
                    prefix = _mm256_add_pd(prefix, _mm256_mul_pd(_mm256_set1_pd(f.q_aux[k]), x));
                }
            }
        }
    }
}
#[cfg(target_arch = "x86_64")]
use steps::{backward, forward, initial};

#[cfg(test)]
mod tests {
    use super::*;
    use psmc_core::{Pattern, Settings, model::Model, rng::LegacyRng};
    #[test]
    fn four_independent_lanes_equal_scalar_structured_messages_and_counts() {
        if !crate::avx_available() {
            return;
        }
        for n in [4, 5, 23, 64] {
            let settings = Settings {
                pattern: Pattern {
                    text: n.to_string(),
                    groups: (0..n).collect(),
                    n_free: n,
                },
                max_t: 15.,
                alpha: 0.1,
                tr_ratio: 5.,
                ran_init: 0.,
                divergence: Some(0.3),
                initial_params: None,
                explicit_times: None,
            };
            let mut model = Model::new(&settings, 20, 10000, &mut LegacyRng::new(42));
            let mut factors = StructuredModel::new(n);
            factors.update(&mut model, &settings);
            assert!(factors.eligible(&model));
            factors.materialize(&mut model);
            let mut expected = Workspace::new(n);
            let mut actual = Workspace::new(n);
            let prepared = actual.prepare(&model);
            let mut batch = Lockstep::default();
            for length in [1, 2, 17, 255, 256, 257, 258, 511, 512, 513, 514, 2048, 3] {
                let sequences: [Vec<u8>; 4] = std::array::from_fn(|lane| {
                    (0..length)
                        .map(|i| {
                            if (i + lane) % 19 == 0 {
                                2
                            } else if (i * (lane + 1) + lane) % 31 == 0 {
                                1
                            } else {
                                0
                            }
                        })
                        .collect()
                });
                let obs = std::array::from_fn(|lane| sequences[lane].as_slice());
                let results = batch.evaluate(&mut actual, &prepared, obs, &factors);
                #[cfg(target_arch = "x86_64")]
                {
                    let reference: [psmc_core::hmm::Messages; 4] = std::array::from_fn(|lane| {
                        expected
                            .evaluate_structured(&prepared, obs[lane], &factors)
                            .0
                            .clone()
                    });
                    let mut previous = vec![[0.0; 4]; n];
                    let mut current = previous.clone();
                    let mut scratch = previous.clone();
                    let emissions = |site: usize| {
                        (0..n)
                            .map(|k| {
                                std::array::from_fn(|lane| {
                                    model.emission[obs[lane][site] as usize * n + k]
                                })
                            })
                            .collect::<Vec<[f64; 4]>>()
                    };
                    // SAFETY: this test returned early without detected AVX;
                    // every vector input has the same verified state dimension.
                    unsafe {
                        for u in 1..=length {
                            let e = emissions(u - 1);
                            let scale = if u == 1 {
                                initial(&mut current, &e, &model.initial)
                            } else {
                                forward(
                                    &previous,
                                    &mut current,
                                    &e,
                                    &factors.message_factors(),
                                    &mut scratch,
                                )
                            };
                            for lane in 0..4 {
                                assert_eq!(scale[lane], reference[lane].scales[u]);
                                for k in 0..n {
                                    assert_eq!(
                                        current[k][lane],
                                        reference[lane].forward[u * n + k]
                                    );
                                }
                            }
                            std::mem::swap(&mut previous, &mut current);
                        }
                        for k in 0..n {
                            previous[k] =
                                std::array::from_fn(|lane| 1.0 / reference[lane].scales[length]);
                        }
                        for u in (1..length).rev() {
                            backward(
                                &previous,
                                &mut current,
                                &emissions(u),
                                &factors.message_factors(),
                                std::array::from_fn(|lane| reference[lane].scales[u]),
                                &mut scratch,
                            );
                            for lane in 0..4 {
                                for k in 0..n {
                                    assert_eq!(
                                        current[k][lane],
                                        reference[lane].backward[u * n + k]
                                    );
                                }
                            }
                            std::mem::swap(&mut previous, &mut current);
                        }
                    }
                }
                for lane in 0..4 {
                    let result = &results[lane];
                    let ac = &result.counts;
                    let (em, ec) = expected.evaluate_structured(&prepared, obs[lane], &factors);
                    assert_eq!(result.likelihood, em.log_likelihood);
                    assert_eq!(result.backward_check, em.backward_check);
                    assert_eq!(ac.a, ec.a);
                    assert_eq!(ac.e, ec.e);
                    assert_eq!(ac.a0, ec.a0);
                }
            }
        }
    }
}

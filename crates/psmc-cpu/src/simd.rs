//! Strict AVX lanes: independent destinations, no horizontal sums or FMA.
//! Safe entry points own a runtime-detected capability and validate dimensions.

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum SimdMode {
    Auto,
    Off,
    Avx,
}
impl SimdMode {
    pub fn parse(value: &str) -> Result<Self, String> {
        match value {
            "auto" => Ok(Self::Auto),
            "off" => Ok(Self::Off),
            "avx" => Ok(Self::Avx),
            _ => Err("--simd must be auto, off or avx".into()),
        }
    }
    pub fn name(self) -> &'static str {
        match self {
            Self::Auto => "auto",
            Self::Off => "off",
            Self::Avx => "avx",
        }
    }
    pub fn validate(self) -> Result<(), String> {
        selection(self, avx_available()).map(|_| ())
    }
}

pub fn avx_available() -> bool {
    #[cfg(target_arch = "x86_64")]
    {
        std::is_x86_feature_detected!("avx")
    }
    #[cfg(not(target_arch = "x86_64"))]
    {
        false
    }
}

fn selection(mode: SimdMode, available: bool) -> Result<bool, String> {
    match (mode, available) {
        (SimdMode::Off, _) | (SimdMode::Auto, false) => Ok(false),
        (SimdMode::Auto | SimdMode::Avx, true) => Ok(true),
        (SimdMode::Avx, false) => {
            Err("AVX is unavailable on this CPU/OS; use --simd auto or off".into())
        }
    }
}

/// This private field can only be constructed after actual CPU/OS detection.
#[derive(Clone, Copy)]
pub(crate) struct Avx(());
impl Avx {
    pub(crate) fn select(mode: SimdMode, states: usize) -> Result<Option<Self>, String> {
        Ok((selection(mode, avx_available())? && states >= 4).then_some(Self(())))
    }

    pub(crate) fn forward(
        self,
        out: &mut [f64],
        previous: &[f64],
        matrix: &[f64],
        emission: &[f64],
    ) {
        let n = out.len();
        assert_eq!(previous.len(), n);
        assert_eq!(emission.len(), n);
        assert_eq!(
            matrix.len(),
            n.checked_mul(n).expect("matrix size overflow")
        );
        #[cfg(target_arch = "x86_64")]
        // SAFETY: this capability requires detected AVX. Complete groups end at
        // n/4*4; every matrix row has n cells and every input/output has n cells.
        // Mutable out cannot alias the borrowed inputs. Unaligned accesses are used.
        unsafe {
            if n == 64 {
                x86::forward64(out, previous, matrix, emission)
            } else {
                x86::forward(out, previous, matrix, emission)
            }
        }
        #[cfg(not(target_arch = "x86_64"))]
        unreachable!("AVX capability is never constructed on this architecture");
    }

    pub(crate) fn backward(self, out: &mut [f64], next: &[f64], transpose: &[f64], scale: f64) {
        let n = out.len();
        assert_eq!(next.len(), n);
        assert_eq!(
            transpose.len(),
            n.checked_mul(n).expect("matrix size overflow")
        );
        #[cfg(target_arch = "x86_64")]
        // SAFETY: same detected capability and in-bounds row/lane proof as forward.
        unsafe {
            if n == 64 {
                x86::backward64(out, next, transpose, scale)
            } else {
                x86::backward(out, next, transpose, scale)
            }
        }
        #[cfg(not(target_arch = "x86_64"))]
        unreachable!("AVX capability is never constructed on this architecture");
    }

    pub(crate) fn counts_sequence64(
        self,
        counts: &mut [f64],
        observations: &[u8],
        forward: &[f64],
        backward: &[f64],
        products: &[f64],
    ) {
        assert!(!observations.is_empty());
        assert!(observations.iter().all(|&z| z <= 2));
        let cells = observations
            .len()
            .checked_add(1)
            .and_then(|r| r.checked_mul(64))
            .expect("message size overflow");
        assert_eq!(counts.len(), 4096);
        assert_eq!(products.len(), 3 * 4096);
        assert_eq!(forward.len(), cells);
        assert_eq!(backward.len(), cells);
        #[cfg(target_arch = "x86_64")]
        // SAFETY: capability checks AVX; validated exact dimensions and symbols
        // bound every complete 4-lane load/store. Tiles never add HMM boundaries.
        unsafe {
            x86::counts_sequence64(counts, observations, forward, backward, products)
        }
        #[cfg(not(target_arch = "x86_64"))]
        unreachable!("AVX capability is never constructed on this architecture");
    }

    pub(crate) fn counts(self, counts: &mut [f64], forward: &[f64], product: &[f64], next: &[f64]) {
        let n = forward.len();
        assert_eq!(next.len(), n);
        let square = n.checked_mul(n).expect("matrix size overflow");
        assert_eq!(counts.len(), square);
        assert_eq!(product.len(), square);
        #[cfg(target_arch = "x86_64")]
        // SAFETY: capability checks AVX. n rows of n cells; complete lane groups
        // remain in their row, and scalar tails handle all remaining cells.
        unsafe {
            x86::counts(counts, forward, product, next)
        }
        #[cfg(not(target_arch = "x86_64"))]
        unreachable!("AVX capability is never constructed on this architecture");
    }
}

#[cfg(target_arch = "x86_64")]
mod x86 {
    use std::arch::x86_64::*;

    #[target_feature(enable = "avx")]
    pub(super) unsafe fn forward(
        out: &mut [f64],
        previous: &[f64],
        matrix: &[f64],
        emission: &[f64],
    ) {
        let n = out.len();
        let end = n / 4 * 4;
        // SAFETY: callers validate all lengths and the AVX capability. Index
        // l*n+k+3 < n*n for k < end and l < n; vector out/emission stay within n.
        unsafe {
            for k in (0..end).step_by(4) {
                let mut sum = _mm256_setzero_pd();
                for (l, &f) in previous.iter().enumerate() {
                    let a = _mm256_loadu_pd(matrix.as_ptr().add(l * n + k));
                    sum = _mm256_add_pd(sum, _mm256_mul_pd(_mm256_set1_pd(f), a));
                }
                let e = _mm256_loadu_pd(emission.as_ptr().add(k));
                _mm256_storeu_pd(out.as_mut_ptr().add(k), _mm256_mul_pd(e, sum));
            }
        }
        for k in end..n {
            let mut sum = 0.0;
            for (l, &f) in previous.iter().enumerate() {
                sum += f * matrix[l * n + k];
            }
            out[k] = emission[k] * sum;
        }
    }

    #[target_feature(enable = "avx")]
    pub(super) unsafe fn backward(out: &mut [f64], next: &[f64], transpose: &[f64], scale: f64) {
        let n = out.len();
        let end = n / 4 * 4;
        // SAFETY: validated n*n layout and n-element out/next; four lanes always
        // stay within one row. No aliased mutable pointers or aligned-load promise.
        unsafe {
            for k in (0..end).step_by(4) {
                let mut sum = _mm256_setzero_pd();
                for (l, &b) in next.iter().enumerate() {
                    let ae = _mm256_loadu_pd(transpose.as_ptr().add(l * n + k));
                    sum = _mm256_add_pd(sum, _mm256_mul_pd(ae, _mm256_set1_pd(b)));
                }
                _mm256_storeu_pd(
                    out.as_mut_ptr().add(k),
                    _mm256_div_pd(sum, _mm256_set1_pd(scale)),
                );
            }
        }
        for k in end..n {
            let mut sum = 0.0;
            for (l, &b) in next.iter().enumerate() {
                sum += transpose[l * n + k] * b;
            }
            out[k] = sum / scale;
        }
    }

    #[target_feature(enable = "avx")]
    pub(super) unsafe fn forward64(
        out: &mut [f64],
        previous: &[f64],
        matrix: &[f64],
        emission: &[f64],
    ) {
        // SAFETY: wrapper checks exact 64-state dimensions; k+31<=63.
        // Eight independent ordered chains; each lane adds l=0..64 unchanged.
        unsafe {
            for k in (0..64).step_by(32) {
                let mut sum0 = _mm256_setzero_pd();
                let mut sum1 = _mm256_setzero_pd();
                let mut sum2 = _mm256_setzero_pd();
                let mut sum3 = _mm256_setzero_pd();
                let mut sum4 = _mm256_setzero_pd();
                let mut sum5 = _mm256_setzero_pd();
                let mut sum6 = _mm256_setzero_pd();
                let mut sum7 = _mm256_setzero_pd();
                for (l, &f) in previous.iter().enumerate() {
                    let v = _mm256_set1_pd(f);
                    let a0 = _mm256_loadu_pd(matrix.as_ptr().add(l * 64 + k + 0));
                    sum0 = _mm256_add_pd(sum0, _mm256_mul_pd(v, a0));
                    let a1 = _mm256_loadu_pd(matrix.as_ptr().add(l * 64 + k + 4));
                    sum1 = _mm256_add_pd(sum1, _mm256_mul_pd(v, a1));
                    let a2 = _mm256_loadu_pd(matrix.as_ptr().add(l * 64 + k + 8));
                    sum2 = _mm256_add_pd(sum2, _mm256_mul_pd(v, a2));
                    let a3 = _mm256_loadu_pd(matrix.as_ptr().add(l * 64 + k + 12));
                    sum3 = _mm256_add_pd(sum3, _mm256_mul_pd(v, a3));
                    let a4 = _mm256_loadu_pd(matrix.as_ptr().add(l * 64 + k + 16));
                    sum4 = _mm256_add_pd(sum4, _mm256_mul_pd(v, a4));
                    let a5 = _mm256_loadu_pd(matrix.as_ptr().add(l * 64 + k + 20));
                    sum5 = _mm256_add_pd(sum5, _mm256_mul_pd(v, a5));
                    let a6 = _mm256_loadu_pd(matrix.as_ptr().add(l * 64 + k + 24));
                    sum6 = _mm256_add_pd(sum6, _mm256_mul_pd(v, a6));
                    let a7 = _mm256_loadu_pd(matrix.as_ptr().add(l * 64 + k + 28));
                    sum7 = _mm256_add_pd(sum7, _mm256_mul_pd(v, a7));
                }
                _mm256_storeu_pd(
                    out.as_mut_ptr().add(k + 0),
                    _mm256_mul_pd(_mm256_loadu_pd(emission.as_ptr().add(k + 0)), sum0),
                );
                _mm256_storeu_pd(
                    out.as_mut_ptr().add(k + 4),
                    _mm256_mul_pd(_mm256_loadu_pd(emission.as_ptr().add(k + 4)), sum1),
                );
                _mm256_storeu_pd(
                    out.as_mut_ptr().add(k + 8),
                    _mm256_mul_pd(_mm256_loadu_pd(emission.as_ptr().add(k + 8)), sum2),
                );
                _mm256_storeu_pd(
                    out.as_mut_ptr().add(k + 12),
                    _mm256_mul_pd(_mm256_loadu_pd(emission.as_ptr().add(k + 12)), sum3),
                );
                _mm256_storeu_pd(
                    out.as_mut_ptr().add(k + 16),
                    _mm256_mul_pd(_mm256_loadu_pd(emission.as_ptr().add(k + 16)), sum4),
                );
                _mm256_storeu_pd(
                    out.as_mut_ptr().add(k + 20),
                    _mm256_mul_pd(_mm256_loadu_pd(emission.as_ptr().add(k + 20)), sum5),
                );
                _mm256_storeu_pd(
                    out.as_mut_ptr().add(k + 24),
                    _mm256_mul_pd(_mm256_loadu_pd(emission.as_ptr().add(k + 24)), sum6),
                );
                _mm256_storeu_pd(
                    out.as_mut_ptr().add(k + 28),
                    _mm256_mul_pd(_mm256_loadu_pd(emission.as_ptr().add(k + 28)), sum7),
                );
            }
        }
    }
    #[target_feature(enable = "avx")]
    pub(super) unsafe fn backward64(out: &mut [f64], next: &[f64], transpose: &[f64], scale: f64) {
        // SAFETY: wrapper checks exact 64-state dimensions; k+31<=63.
        // Eight independent ordered chains; each lane adds l=0..64 unchanged.
        unsafe {
            for k in (0..64).step_by(32) {
                let mut sum0 = _mm256_setzero_pd();
                let mut sum1 = _mm256_setzero_pd();
                let mut sum2 = _mm256_setzero_pd();
                let mut sum3 = _mm256_setzero_pd();
                let mut sum4 = _mm256_setzero_pd();
                let mut sum5 = _mm256_setzero_pd();
                let mut sum6 = _mm256_setzero_pd();
                let mut sum7 = _mm256_setzero_pd();
                for (l, &b) in next.iter().enumerate() {
                    let v = _mm256_set1_pd(b);
                    let a0 = _mm256_loadu_pd(transpose.as_ptr().add(l * 64 + k + 0));
                    sum0 = _mm256_add_pd(sum0, _mm256_mul_pd(a0, v));
                    let a1 = _mm256_loadu_pd(transpose.as_ptr().add(l * 64 + k + 4));
                    sum1 = _mm256_add_pd(sum1, _mm256_mul_pd(a1, v));
                    let a2 = _mm256_loadu_pd(transpose.as_ptr().add(l * 64 + k + 8));
                    sum2 = _mm256_add_pd(sum2, _mm256_mul_pd(a2, v));
                    let a3 = _mm256_loadu_pd(transpose.as_ptr().add(l * 64 + k + 12));
                    sum3 = _mm256_add_pd(sum3, _mm256_mul_pd(a3, v));
                    let a4 = _mm256_loadu_pd(transpose.as_ptr().add(l * 64 + k + 16));
                    sum4 = _mm256_add_pd(sum4, _mm256_mul_pd(a4, v));
                    let a5 = _mm256_loadu_pd(transpose.as_ptr().add(l * 64 + k + 20));
                    sum5 = _mm256_add_pd(sum5, _mm256_mul_pd(a5, v));
                    let a6 = _mm256_loadu_pd(transpose.as_ptr().add(l * 64 + k + 24));
                    sum6 = _mm256_add_pd(sum6, _mm256_mul_pd(a6, v));
                    let a7 = _mm256_loadu_pd(transpose.as_ptr().add(l * 64 + k + 28));
                    sum7 = _mm256_add_pd(sum7, _mm256_mul_pd(a7, v));
                }
                _mm256_storeu_pd(
                    out.as_mut_ptr().add(k + 0),
                    _mm256_div_pd(sum0, _mm256_set1_pd(scale)),
                );
                _mm256_storeu_pd(
                    out.as_mut_ptr().add(k + 4),
                    _mm256_div_pd(sum1, _mm256_set1_pd(scale)),
                );
                _mm256_storeu_pd(
                    out.as_mut_ptr().add(k + 8),
                    _mm256_div_pd(sum2, _mm256_set1_pd(scale)),
                );
                _mm256_storeu_pd(
                    out.as_mut_ptr().add(k + 12),
                    _mm256_div_pd(sum3, _mm256_set1_pd(scale)),
                );
                _mm256_storeu_pd(
                    out.as_mut_ptr().add(k + 16),
                    _mm256_div_pd(sum4, _mm256_set1_pd(scale)),
                );
                _mm256_storeu_pd(
                    out.as_mut_ptr().add(k + 20),
                    _mm256_div_pd(sum5, _mm256_set1_pd(scale)),
                );
                _mm256_storeu_pd(
                    out.as_mut_ptr().add(k + 24),
                    _mm256_div_pd(sum6, _mm256_set1_pd(scale)),
                );
                _mm256_storeu_pd(
                    out.as_mut_ptr().add(k + 28),
                    _mm256_div_pd(sum7, _mm256_set1_pd(scale)),
                );
            }
        }
    }
    #[target_feature(enable = "avx")]
    pub(super) unsafe fn counts_sequence64(
        counts: &mut [f64],
        observations: &[u8],
        forward: &[f64],
        backward: &[f64],
        products: &[f64],
    ) {
        // SAFETY: wrapper checks 64-state shapes and symbols; l+31<=63.
        // Every cell adds sites in original order, with two unfused multiplies.
        unsafe {
            for begin in (1..observations.len()).step_by(8) {
                let end = (begin + 8).min(observations.len());
                for k in 0..64 {
                    for l in (0..64).step_by(32) {
                        let mut sum0 = _mm256_loadu_pd(counts.as_ptr().add(k * 64 + l + 0));
                        let mut sum1 = _mm256_loadu_pd(counts.as_ptr().add(k * 64 + l + 4));
                        let mut sum2 = _mm256_loadu_pd(counts.as_ptr().add(k * 64 + l + 8));
                        let mut sum3 = _mm256_loadu_pd(counts.as_ptr().add(k * 64 + l + 12));
                        let mut sum4 = _mm256_loadu_pd(counts.as_ptr().add(k * 64 + l + 16));
                        let mut sum5 = _mm256_loadu_pd(counts.as_ptr().add(k * 64 + l + 20));
                        let mut sum6 = _mm256_loadu_pd(counts.as_ptr().add(k * 64 + l + 24));
                        let mut sum7 = _mm256_loadu_pd(counts.as_ptr().add(k * 64 + l + 28));
                        for u in begin..end {
                            let f = _mm256_set1_pd(*forward.get_unchecked(u * 64 + k));
                            let row = *observations.get_unchecked(u) as usize * 4096 + k * 64 + l;
                            let next = (u + 1) * 64 + l;
                            let first0 =
                                _mm256_mul_pd(f, _mm256_loadu_pd(products.as_ptr().add(row + 0)));
                            let term0 = _mm256_mul_pd(
                                first0,
                                _mm256_loadu_pd(backward.as_ptr().add(next + 0)),
                            );
                            sum0 = _mm256_add_pd(sum0, term0);
                            let first1 =
                                _mm256_mul_pd(f, _mm256_loadu_pd(products.as_ptr().add(row + 4)));
                            let term1 = _mm256_mul_pd(
                                first1,
                                _mm256_loadu_pd(backward.as_ptr().add(next + 4)),
                            );
                            sum1 = _mm256_add_pd(sum1, term1);
                            let first2 =
                                _mm256_mul_pd(f, _mm256_loadu_pd(products.as_ptr().add(row + 8)));
                            let term2 = _mm256_mul_pd(
                                first2,
                                _mm256_loadu_pd(backward.as_ptr().add(next + 8)),
                            );
                            sum2 = _mm256_add_pd(sum2, term2);
                            let first3 =
                                _mm256_mul_pd(f, _mm256_loadu_pd(products.as_ptr().add(row + 12)));
                            let term3 = _mm256_mul_pd(
                                first3,
                                _mm256_loadu_pd(backward.as_ptr().add(next + 12)),
                            );
                            sum3 = _mm256_add_pd(sum3, term3);
                            let first4 =
                                _mm256_mul_pd(f, _mm256_loadu_pd(products.as_ptr().add(row + 16)));
                            let term4 = _mm256_mul_pd(
                                first4,
                                _mm256_loadu_pd(backward.as_ptr().add(next + 16)),
                            );
                            sum4 = _mm256_add_pd(sum4, term4);
                            let first5 =
                                _mm256_mul_pd(f, _mm256_loadu_pd(products.as_ptr().add(row + 20)));
                            let term5 = _mm256_mul_pd(
                                first5,
                                _mm256_loadu_pd(backward.as_ptr().add(next + 20)),
                            );
                            sum5 = _mm256_add_pd(sum5, term5);
                            let first6 =
                                _mm256_mul_pd(f, _mm256_loadu_pd(products.as_ptr().add(row + 24)));
                            let term6 = _mm256_mul_pd(
                                first6,
                                _mm256_loadu_pd(backward.as_ptr().add(next + 24)),
                            );
                            sum6 = _mm256_add_pd(sum6, term6);
                            let first7 =
                                _mm256_mul_pd(f, _mm256_loadu_pd(products.as_ptr().add(row + 28)));
                            let term7 = _mm256_mul_pd(
                                first7,
                                _mm256_loadu_pd(backward.as_ptr().add(next + 28)),
                            );
                            sum7 = _mm256_add_pd(sum7, term7);
                        }
                        _mm256_storeu_pd(counts.as_mut_ptr().add(k * 64 + l + 0), sum0);
                        _mm256_storeu_pd(counts.as_mut_ptr().add(k * 64 + l + 4), sum1);
                        _mm256_storeu_pd(counts.as_mut_ptr().add(k * 64 + l + 8), sum2);
                        _mm256_storeu_pd(counts.as_mut_ptr().add(k * 64 + l + 12), sum3);
                        _mm256_storeu_pd(counts.as_mut_ptr().add(k * 64 + l + 16), sum4);
                        _mm256_storeu_pd(counts.as_mut_ptr().add(k * 64 + l + 20), sum5);
                        _mm256_storeu_pd(counts.as_mut_ptr().add(k * 64 + l + 24), sum6);
                        _mm256_storeu_pd(counts.as_mut_ptr().add(k * 64 + l + 28), sum7);
                    }
                }
            }
        }
    }
    #[target_feature(enable = "avx")]
    pub(super) unsafe fn counts(
        counts: &mut [f64],
        forward: &[f64],
        product: &[f64],
        next: &[f64],
    ) {
        let n = forward.len();
        let end = n / 4 * 4;
        for (k, &f) in forward.iter().enumerate() {
            let row = &mut counts[k * n..][..n];
            let ae = &product[k * n..][..n];
            // SAFETY: all slices have n cells. l+3 < n in vector loop; the
            // enclosing row slice bounds the destination independently of k.
            unsafe {
                let fv = _mm256_set1_pd(f);
                for l in (0..end).step_by(4) {
                    let first = _mm256_mul_pd(fv, _mm256_loadu_pd(ae.as_ptr().add(l)));
                    let contribution = _mm256_mul_pd(first, _mm256_loadu_pd(next.as_ptr().add(l)));
                    let old = _mm256_loadu_pd(row.as_ptr().add(l));
                    _mm256_storeu_pd(row.as_mut_ptr().add(l), _mm256_add_pd(old, contribution));
                }
            }
            for l in end..n {
                row[l] += f * ae[l] * next[l];
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn dispatch_and_small_shapes_are_explicit() {
        assert!(!selection(SimdMode::Auto, false).unwrap());
        assert!(!selection(SimdMode::Off, true).unwrap());
        assert!(selection(SimdMode::Avx, false).is_err());
        assert!(selection(SimdMode::Avx, true).unwrap());
        assert!(Avx::select(SimdMode::Auto, 3).unwrap().is_none());
        assert!(SimdMode::parse("neon").is_err());
        assert!(SimdMode::parse("invalid").is_err());
    }
}

#[cfg(test)]
mod lane_tests {
    use super::*;
    fn exact(a: &[f64], b: &[f64]) {
        assert_eq!(a.len(), b.len());
        for (&a, &b) in a.iter().zip(b) {
            assert!(
                a.to_bits() == b.to_bits() || a.is_nan() && b.is_nan(),
                "{a:?} != {b:?}"
            );
        }
    }
    #[test]
    fn lanes_preserve_extremes_subnormals_and_unaligned_tails() {
        let Some(avx) = Avx::select(SimdMode::Auto, 4).unwrap() else {
            return;
        };
        let values = [
            0.0,
            -0.0,
            f64::from_bits(1),
            -f64::from_bits(1),
            1e-300,
            1e300,
            0.1,
            -1.0,
            f64::INFINITY,
            f64::NEG_INFINITY,
            f64::NAN,
        ];
        for n in (1..=33).chain([63, 64, 65]) {
            for offset in 0..values.len() {
                let f: Vec<_> = (0..n)
                    .map(|i| values[(i + offset) % values.len()])
                    .collect();
                let b: Vec<_> = (0..n)
                    .map(|i| values[(i * 3 + offset + 1) % values.len()])
                    .collect();
                let matrix_storage: Vec<_> = (0..n * n + 1)
                    .map(|i| values[(i * 7 + offset) % values.len()])
                    .collect();
                let matrix = &matrix_storage[1..]; // deliberate nonzero alignment offset
                let mut expected = vec![0.0; n];
                let mut actual_storage = vec![123.0; n + 2];
                let out = &mut actual_storage[1..n + 1];
                for k in 0..n {
                    let mut v = 0.0;
                    for l in 0..n {
                        v += f[l] * matrix[l * n + k];
                    }
                    expected[k] = b[k] * v;
                }
                avx.forward(out, &f, matrix, &b);
                exact(out, &expected);
                for k in 0..n {
                    let mut v = 0.0;
                    for l in 0..n {
                        v += matrix[l * n + k] * b[l];
                    }
                    expected[k] = v / values[offset];
                }
                avx.backward(out, &b, matrix, values[offset]);
                exact(out, &expected);
                assert_eq!(actual_storage[0], 123.0);
                assert_eq!(actual_storage[n + 1], 123.0);
                let mut counts: Vec<_> = (0..n * n)
                    .map(|i| values[(i + offset + 2) % values.len()])
                    .collect();
                let mut reference = counts.clone();
                for k in 0..n {
                    for l in 0..n {
                        reference[k * n + l] += f[k] * matrix[k * n + l] * b[l];
                    }
                }
                avx.counts(&mut counts, &f, matrix, &b);
                exact(&counts, &reference);
            }
        }
    }
    #[test]
    fn safe_wrappers_reject_bad_shapes_before_vector_access() {
        let Some(avx) = Avx::select(SimdMode::Auto, 4).unwrap() else {
            return;
        };
        assert!(
            std::panic::catch_unwind(|| avx.forward(
                &mut [0.0; 4],
                &[1.0; 4],
                &[1.0; 15],
                &[1.0; 4]
            ))
            .is_err()
        );
        assert!(
            std::panic::catch_unwind(|| avx.backward(&mut [0.0; 4], &[1.0; 3], &[1.0; 16], 1.0))
                .is_err()
        );
        assert!(
            std::panic::catch_unwind(|| avx.forward(
                &mut [0.0; 64],
                &[1.0; 63],
                &[1.0; 4096],
                &[1.0; 64]
            ))
            .is_err()
        );
        assert!(
            std::panic::catch_unwind(|| avx.forward(
                &mut [0.0; 64],
                &[1.0; 64],
                &[1.0; 4095],
                &[1.0; 64]
            ))
            .is_err()
        );
        assert!(
            std::panic::catch_unwind(|| avx.forward(
                &mut [0.0; 64],
                &[1.0; 64],
                &[1.0; 4096],
                &[1.0; 63]
            ))
            .is_err()
        );
        assert!(
            std::panic::catch_unwind(|| avx.backward(
                &mut [0.0; 64],
                &[1.0; 63],
                &[1.0; 4096],
                1.0
            ))
            .is_err()
        );
        assert!(
            std::panic::catch_unwind(|| avx.backward(
                &mut [0.0; 64],
                &[1.0; 64],
                &[1.0; 4095],
                1.0
            ))
            .is_err()
        );
        assert!(
            std::panic::catch_unwind(|| avx.counts(
                &mut [0.0; 15],
                &[1.0; 4],
                &[1.0; 16],
                &[1.0; 4]
            ))
            .is_err()
        );
    }
}

#[cfg(test)]
mod sequence_tests {
    use super::*;
    #[test]
    fn ordered_counts64_match_scalar_at_tile_boundaries_and_extremes() {
        let Some(avx) = Avx::select(SimdMode::Auto, 64).unwrap() else {
            return;
        };
        let values = [
            0.0,
            -0.0,
            f64::from_bits(1),
            -f64::from_bits(1),
            1e-300,
            1e300,
            0.1,
            -1.0,
            f64::INFINITY,
            f64::NEG_INFINITY,
            f64::NAN,
        ];
        for length in [1, 2, 7, 8, 9, 15, 16, 17, 31, 32, 33, 63, 64, 65, 129] {
            for extreme in [false, true] {
                let cells = (length + 1) * 64;
                let make = |count: usize, salt: usize| -> Vec<f64> {
                    (0..count)
                        .map(|i| {
                            if extreme {
                                values[(i * 7 + salt) % values.len()]
                            } else {
                                ((i * 17 + salt) % 103) as f64 / 107.0
                            }
                        })
                        .collect()
                };
                // Offset all arrays to exercise unaligned vector loads/stores.
                let f = make(cells + 1, 1);
                let b = make(cells + 1, 3);
                let products = make(3 * 4096 + 1, 7);
                let obs: Vec<u8> = (0..length).map(|u| (u % 3) as u8).collect();
                let mut expected = vec![1e-25; 4096];
                for u in 1..length {
                    for k in 0..64 {
                        for l in 0..64 {
                            expected[k * 64 + l] += (f[1 + u * 64 + k]
                                * products[1 + obs[u] as usize * 4096 + k * 64 + l])
                                * b[1 + (u + 1) * 64 + l];
                        }
                    }
                }
                let mut actual = vec![1e-25; 4097];
                avx.counts_sequence64(&mut actual[1..], &obs, &f[1..], &b[1..], &products[1..]);
                for (a, e) in actual[1..].iter().zip(expected) {
                    if e.is_nan() {
                        assert!(a.is_nan());
                    } else {
                        assert_eq!(a.to_bits(), e.to_bits());
                    }
                }
            }
        }
    }
    #[test]
    fn sequence_shape_and_symbol_errors_are_rejected() {
        let Some(avx) = Avx::select(SimdMode::Auto, 64).unwrap() else {
            return;
        };
        for (obs, cells, products, counts) in [
            (vec![], 64, 12288, 4096),
            (vec![3], 128, 12288, 4096),
            (vec![0], 127, 12288, 4096),
            (vec![0], 128, 12287, 4096),
            (vec![0], 128, 12288, 4095),
        ] {
            assert!(
                std::panic::catch_unwind(|| avx.counts_sequence64(
                    &mut vec![0.0; counts],
                    &obs,
                    &vec![0.0; cells],
                    &vec![0.0; cells],
                    &vec![0.0; products]
                ))
                .is_err()
            );
        }
    }
}

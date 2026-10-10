"""Choose generic/wide execution once per sequence, not once per HMM position."""
from cpu_campaign_kernel_variants import replace
from cpu_campaign_split64 import prepare as split64


def prepare(scratch):
    split64(scratch)
    path=scratch/'crates/psmc-cpu/src/simd.rs'
    replace(path,'            if n == 64 { x86::forward64(out, previous, matrix, emission) } else { x86::forward(out, previous, matrix, emission) }',
        '            x86::forward(out, previous, matrix, emission)')
    replace(path,'            if n == 64 { x86::backward64(out, next, transpose, scale) } else { x86::backward(out, next, transpose, scale) }',
        '            x86::backward(out, next, transpose, scale)')
    methods='''    pub(crate) fn forward64(self, out: &mut [f64], previous: &[f64], matrix: &[f64], emission: &[f64]) {
        assert_eq!(out.len(),64);
        assert_eq!(previous.len(),64);
        assert_eq!(matrix.len(),4096);
        assert_eq!(emission.len(),64);
        #[cfg(target_arch="x86_64")]
        // SAFETY: this token proves AVX and the fixed-size bounds are checked above.
        unsafe { x86::forward64(out,previous,matrix,emission); }
        #[cfg(not(target_arch="x86_64"))]
        unreachable!("AVX capability cannot be constructed");
    }
    pub(crate) fn backward64(self, out: &mut [f64], next: &[f64], transpose: &[f64], scale: f64) {
        assert_eq!(out.len(),64);
        assert_eq!(next.len(),64);
        assert_eq!(transpose.len(),4096);
        #[cfg(target_arch="x86_64")]
        // SAFETY: runtime capability and fixed 64/4096 shapes checked above.
        unsafe { x86::backward64(out,next,transpose,scale); }
        #[cfg(not(target_arch="x86_64"))]
        unreachable!("AVX capability cannot be constructed");
    }

'''
    replace(path,'    pub(crate) fn counts(self,',methods+'    pub(crate) fn counts(self,')
    replace(path,'                avx.forward(out, &f, matrix, &b);\n                exact(out, &expected);',
        '                avx.forward(out, &f, matrix, &b);\n                exact(out, &expected);\n                if n==64 { avx.forward64(out,&f,matrix,&b); exact(out,&expected); }')
    replace(path,'                avx.backward(out, &b, matrix, values[offset]);\n                exact(out, &expected);',
        '                avx.backward(out, &b, matrix, values[offset]);\n                exact(out, &expected);\n                if n==64 { avx.backward64(out,&b,matrix,values[offset]); exact(out,&expected); }')
    with path.open('a') as stream:
        stream.write('''
#[cfg(test)]
mod fixed_shape_tests {
    use super::*;
    #[test]
    fn wide_wrappers_reject_shapes_before_access() {
        let Some(avx)=Avx::select(SimdMode::Auto,64).unwrap() else {return;};
        assert!(std::panic::catch_unwind(||avx.forward64(&mut [0.0;63],&[1.0;64],&[1.0;4096],&[1.0;64])).is_err());
        assert!(std::panic::catch_unwind(||avx.forward64(&mut [0.0;64],&[1.0;63],&[1.0;4096],&[1.0;64])).is_err());
        assert!(std::panic::catch_unwind(||avx.forward64(&mut [0.0;64],&[1.0;64],&[1.0;4095],&[1.0;64])).is_err());
        assert!(std::panic::catch_unwind(||avx.forward64(&mut [0.0;64],&[1.0;64],&[1.0;4096],&[1.0;63])).is_err());
        assert!(std::panic::catch_unwind(||avx.backward64(&mut [0.0;63],&[1.0;64],&[1.0;4096],1.0)).is_err());
        assert!(std::panic::catch_unwind(||avx.backward64(&mut [0.0;64],&[1.0;63],&[1.0;4096],1.0)).is_err());
        assert!(std::panic::catch_unwind(||avx.backward64(&mut [0.0;64],&[1.0;64],&[1.0;4095],1.0)).is_err());
    }
}
''')
    cpu=scratch/'crates/psmc-cpu/src/lib.rs'
    old='''    pub fn evaluate(
        &mut self,
        prepared: &PreparedModel<'_>,
        observations: &[u8],
    ) -> (&Messages, &Counts) {'''
    wrapper='''    pub fn evaluate(
        &mut self,
        prepared: &PreparedModel<'_>,
        observations: &[u8],
    ) -> (&Messages, &Counts) {
        if self.messages.n == 64 && self.avx.is_some() {
            self.evaluate_impl::<true>(prepared, observations)
        } else {
            self.evaluate_impl::<false>(prepared, observations)
        }
    }

    // The const parameter removes per-position specialization branches. Keep
    // separate instantiations so generic kernels retain their own register layout.
    #[inline(never)]
    fn evaluate_impl<const WIDE64: bool>(
        &mut self,
        prepared: &PreparedModel<'_>,
        observations: &[u8],
    ) -> (&Messages, &Counts) {'''
    replace(cpu,old,wrapper)
    replace(cpu,'                avx.forward(current, previous, &model.transition, emission);',
        '                if WIDE64 { avx.forward64(current, previous, &model.transition, emission); } else { avx.forward(current, previous, &model.transition, emission); }')
    replace(cpu,'                avx.backward(current, next, transpose, messages.scales[u]);',
        '                if WIDE64 { avx.backward64(current, next, transpose, messages.scales[u]); } else { avx.backward(current, next, transpose, messages.scales[u]); }')

"""Generate isolated strict kernel candidates from the Phase 3a source."""
from pathlib import Path


def replace(path, old, new):
    source = path.read_text()
    assert source.count(old) == 1, (str(path), old[:80], source.count(old))
    path.write_text(source.replace(old, new))


def unroll(scratch, width):
    assert width in (8, 16)
    path = scratch / 'crates/psmc-cpu/src/simd.rs'
    for direction in ['forward', 'backward']:
        if direction == 'forward':
            old = '''            for k in (0..end).step_by(4) {
                let mut sum = _mm256_setzero_pd();
                for (l, &f) in previous.iter().enumerate() {'''
            iterator, value, matrix = 'previous', 'f', 'matrix'
        else:
            old = '''            for k in (0..end).step_by(4) {
                let mut sum = _mm256_setzero_pd();
                for (l, &b) in next.iter().enumerate() {'''
            iterator, value, matrix = 'next', 'b', 'transpose'
        lines = [f'            // Independent destinations: each lane still adds l=0..n in order.',
                 f'            // k+{width-1}<n and l*n+k+{width-1}<n*n by wide/end bounds.',
                 f'            let wide = n / {width} * {width};',
                 f'            for k in (0..wide).step_by({width}) {{']
        for j in range(width//4): lines.append(f'                let mut sum{j} = _mm256_setzero_pd();')
        lines += [f'                for (l, &{value}) in {iterator}.iter().enumerate() {{',
                  f'                    let v = _mm256_set1_pd({value});']
        for j in range(width//4):
            lines.append(f'                    let a{j} = _mm256_loadu_pd({matrix}.as_ptr().add(l*n+k+{j*4}));')
            product = f'_mm256_mul_pd(v, a{j})' if direction == 'forward' else f'_mm256_mul_pd(a{j}, v)'
            lines.append(f'                    sum{j} = _mm256_add_pd(sum{j}, {product});')
        lines.append('                }')
        for j in range(width//4):
            result = f'_mm256_mul_pd(_mm256_loadu_pd(emission.as_ptr().add(k+{j*4})), sum{j})' if direction == 'forward' else f'_mm256_div_pd(sum{j}, _mm256_set1_pd(scale))'
            lines.append(f'                _mm256_storeu_pd(out.as_mut_ptr().add(k+{j*4}), {result});')
        lines.append('            }')
        replace(path, old, '\n'.join(lines)+'\n'+old.replace('(0..end)', '(wide..end)'))
    replace(path, 'for n in 1..=13 {', 'for n in (1..=33).chain([63,64,65]) {')


def tile(scratch, size):
    assert size in (64, 256)
    path = scratch / 'crates/psmc-cpu/src/simd.rs'
    wrapper = '''    pub(crate) fn counts_sequence(self, counts: &mut [f64], n: usize, observations: &[u8],
        forward: &[f64], backward: &[f64], products: &[f64]) {
        assert!(n > 0 && !observations.is_empty());
        assert!(observations.iter().all(|&v| v <= 2));
        let square = n.checked_mul(n).expect("square overflow");
        let cells = observations.len().checked_add(1).and_then(|x| x.checked_mul(n)).expect("cells overflow");
        assert_eq!(counts.len(), square);
        assert_eq!(forward.len(), cells);
        assert_eq!(backward.len(), cells);
        assert_eq!(products.len(), square.checked_mul(3).expect("products overflow"));
        #[cfg(target_arch = "x86_64")]
        // SAFETY: capability detects AVX; all site/row/column dimensions checked above.
        unsafe { x86::counts_sequence(counts,n,observations,forward,backward,products); }
        #[cfg(not(target_arch = "x86_64"))]
        unreachable!("AVX capability cannot be constructed");
    }

'''
    replace(path, '    pub(crate) fn counts(self,', wrapper+'    pub(crate) fn counts(self,')
    kernel = '''    #[target_feature(enable = "avx")]
    pub(super) unsafe fn counts_sequence(counts: &mut [f64], n: usize, observations: &[u8],
        forward: &[f64], backward: &[f64], products: &[f64]) {
        let length = observations.len();
        let end = n/4*4;
        let square = n*n;
        for begin in (1..length).step_by(TILE_SIZE) {
            let stop = (length-begin).min(TILE_SIZE)+begin;
            for k in 0..n {
                // SAFETY: complete groups stay within k's n-cell row. u<length,
                // so (u+1)*n+l+3 is within the checked backward buffer. Symbols<=2.
                unsafe {
                    for l in (0..end).step_by(4) {
                        let target = counts.as_mut_ptr().add(k*n+l);
                        let mut sum = _mm256_loadu_pd(target);
                        for u in begin..stop {
                            let f = _mm256_set1_pd(forward[u*n+k]);
                            let ae = _mm256_loadu_pd(products.as_ptr().add(observations[u] as usize*square+k*n+l));
                            let b = _mm256_loadu_pd(backward.as_ptr().add((u+1)*n+l));
                            sum = _mm256_add_pd(sum, _mm256_mul_pd(_mm256_mul_pd(f,ae),b));
                        }
                        _mm256_storeu_pd(target,sum);
                    }
                }
                for l in end..n {
                    let mut sum = counts[k*n+l];
                    for u in begin..stop {
                        sum += forward[u*n+k]*products[observations[u] as usize*square+k*n+l]*backward[(u+1)*n+l];
                    }
                    counts[k*n+l] = sum;
                }
            }
        }
    }

'''.replace('TILE_SIZE',str(size))
    replace(path, '    #[target_feature(enable = "avx")]\n    pub(super) unsafe fn counts(', kernel+'    #[target_feature(enable = "avx")]\n    pub(super) unsafe fn counts(')
    cpu = scratch/'crates/psmc-cpu/src/lib.rs'
    replace(cpu, '        counts.q0 = 0.0;', '''        counts.q0 = 0.0;
        if let Some(avx) = self.avx {
            avx.counts_sequence(&mut counts.a,n,observations,&messages.forward,&messages.backward,&prepared.emission_transition);
        }''')
    replace(cpu, '                avx.counts(&mut counts.a, forward, product, next_backward);', '                let _ = avx; // complete transition counts already computed in ascending tiles')
    with path.open('a') as file:
        file.write('''
#[cfg(test)]
mod tile_tests {
    use super::*;
    #[test]
    fn tile_boundaries_and_nonfinite_values_preserve_every_cell() {
        let Some(avx) = Avx::select(SimdMode::Auto,4).unwrap() else { return; };
        let v = [0.0,-0.0,f64::from_bits(1),1e-300,1e300,0.1,-1.0,f64::INFINITY,f64::NEG_INFINITY,f64::NAN];
        for n in [1,4,7,16,23,32,64,65] {
            for length in [1,2,3,63,64,65,127,128,129,255,256,257] {
                let observations: Vec<_>=(0..length).map(|i|(i%3) as u8).collect();
                let f: Vec<_>=(0..(length+1)*n).map(|i|v[(i*7+2)%v.len()]).collect();
                let b: Vec<_>=(0..(length+1)*n).map(|i|v[(i*3+1)%v.len()]).collect();
                let ae: Vec<_>=(0..3*n*n).map(|i|v[(i*13+5)%v.len()]).collect();
                let mut actual=vec![1e-25;n*n]; let mut expected=actual.clone();
                for u in 1..length {
                    for k in 0..n { for l in 0..n {
                        expected[k*n+l] += f[u*n+k]*ae[observations[u] as usize*n*n+k*n+l]*b[(u+1)*n+l];
                    }}
                }
                avx.counts_sequence(&mut actual,n,&observations,&f,&b,&ae);
                for (&a,&b) in actual.iter().zip(&expected) { assert!(a.to_bits()==b.to_bits() || a.is_nan() && b.is_nan()); }
            }
        }
    }
}
''')


def prepare(scratch, label):
    if label.startswith('unroll'):
        unroll(scratch,int(label.removeprefix('unroll')))
    elif label.startswith('tile'):
        tile(scratch,int(label.removeprefix('tile')))
    else:
        raise ValueError(label)

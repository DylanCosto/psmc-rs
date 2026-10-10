"""Keep original AVX functions intact; dispatch K64 to separate wide kernels."""
from cpu_campaign_kernel_variants import replace


def prepare(scratch):
    path=scratch/'crates/psmc-cpu/src/simd.rs'
    replace(path,'            x86::forward(out, previous, matrix, emission)',
        '            if n == 64 { x86::forward64(out, previous, matrix, emission) } else { x86::forward(out, previous, matrix, emission) }')
    replace(path,'            x86::backward(out, next, transpose, scale)',
        '            if n == 64 { x86::backward64(out, next, transpose, scale) } else { x86::backward(out, next, transpose, scale) }')
    functions=[]
    for direction in ['forward','backward']:
        signature='out: &mut [f64], previous: &[f64], matrix: &[f64], emission: &[f64]' if direction=='forward' else 'out: &mut [f64], next: &[f64], transpose: &[f64], scale: f64'
        iterator,matrix,value=('previous','matrix','f') if direction=='forward' else ('next','transpose','b')
        lines=['    #[target_feature(enable = "avx")]',f'    pub(super) unsafe fn {direction}64({signature}) {{',
            '        // SAFETY: called only after the safe wrapper checks n==64 and all',
            '        // shapes. k+15<=63, l<64; all row and vector addresses are in bounds.',
            '        // Four independent ordered chains; no FMA or horizontal reduction.',
            '        unsafe {','            for k in (0..64).step_by(16) {']
        for j in range(4): lines.append(f'                let mut sum{j} = _mm256_setzero_pd();')
        lines += [f'                for (l, &{value}) in {iterator}.iter().enumerate() {{',f'                    let v = _mm256_set1_pd({value});']
        for j in range(4):
            lines.append(f'                    let a{j} = _mm256_loadu_pd({matrix}.as_ptr().add(l*64+k+{j*4}));')
            product=f'_mm256_mul_pd(v, a{j})' if direction=='forward' else f'_mm256_mul_pd(a{j}, v)'
            lines.append(f'                    sum{j} = _mm256_add_pd(sum{j}, {product});')
        lines.append('                }')
        for j in range(4):
            result=f'_mm256_mul_pd(_mm256_loadu_pd(emission.as_ptr().add(k+{j*4})), sum{j})' if direction=='forward' else f'_mm256_div_pd(sum{j}, _mm256_set1_pd(scale))'
            lines.append(f'                _mm256_storeu_pd(out.as_mut_ptr().add(k+{j*4}), {result});')
        lines+=['            }','        }','    }','']
        functions.append('\n'.join(lines))
    needle='    #[target_feature(enable = "avx")]\n    pub(super) unsafe fn counts('
    replace(path,needle,'\n'.join(functions)+'\n'+needle)
    replace(path,'for n in 1..=13 {','for n in (1..=33).chain([63,64,65]) {')

"""Fixed source-loop unroll: each accumulator still visits all sources in order."""
import sys
from pathlib import Path
import exhaust_cpu as e
from exhaust_more import normalize
from cpu_next_candidates import function_replace
original=e.generate
def generate(path,kb,width,sites):
    original(path,2,16,16)
    normalize(path.parents[3], k64=True)
    path.write_text(path.read_text()+Path('bench/exhaust_normalize_tests.rs').read_text())
    if kb==1:return
    for direction in ['forward','backward']:
        forward=direction=='forward'
        vector,matrix=('previous','matrix') if forward else ('next','transpose')
        signature='out: &mut [f64], previous: &[f64], matrix: &[f64], emission: &[f64]' if forward else 'out: &mut [f64], next: &[f64], transpose: &[f64], scale: f64'
        lines=['    #[target_feature(enable = "avx")]',f'    pub(super) unsafe fn {direction}64({signature}) {{','        // SAFETY: validated K64 shapes; source unroll preserves every addend order.','        unsafe {','            for k in (0..64).step_by(32) {']
        for j in range(8):lines.append(f'                let mut sum{j} = _mm256_setzero_pd();')
        lines+=['                for l in (0..64).step_by(4) {']
        for offset in range(4):
            lines.append(f'                    let v = _mm256_set1_pd(*{vector}.get_unchecked(l+{offset}));')
            for j in range(8):
                lines.append(f'                    let a = _mm256_loadu_pd({matrix}.as_ptr().add((l+{offset})*64+k+{4*j}));')
                prod='_mm256_mul_pd(v,a)' if forward else '_mm256_mul_pd(a,v)'
                lines.append(f'                    sum{j} = _mm256_add_pd(sum{j},{prod});')
        lines+=['                }']
        for j in range(8):
            result=f'_mm256_mul_pd(_mm256_loadu_pd(emission.as_ptr().add(k+{4*j})),sum{j})' if forward else f'_mm256_div_pd(sum{j},_mm256_set1_pd(scale))'
            lines.append(f'                _mm256_storeu_pd(out.as_mut_ptr().add(k+{4*j}),{result});')
        lines+=['            }','        }','    }'];function_replace(path,direction+'64','\n'.join(lines))
e.generate=generate
e.RAW=Path('work/exhaust/unroll');e.REPORT='bench/exhaust-unroll.json'
e.CONFIGS={'combined':(1,16,16),'source4':(2,16,16)}
if __name__=='__main__':getattr(e,sys.argv[1])()

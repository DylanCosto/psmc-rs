"""Keep emission counting beside transition tiles to reuse hot message rows."""
import sys
from pathlib import Path
import exhaust_cpu as e
from exhaust_more import normalize
original=e.generate
def generate(path,kb,width,sites):
    original(path,2,16,16)
    normalize(path.parents[3], k64=True)
    path.write_text(path.read_text()+Path('bench/exhaust_normalize_tests.rs').read_text())
    if kb==1:return
    s=path.read_text()
    start=s.index('    pub(crate) fn counts_sequence64(');end=s.index('    pub(crate) fn counts(self',start)
    wrapper=s[start:end].replace('counts_sequence64','counts_emissions64').replace('        products: &[f64],','        products: &[f64],\n        emissions: &mut [f64],\n        scales: &[f64],')
    wrapper=wrapper.replace('        assert_eq!(counts.len(), 4096);','        assert_eq!(counts.len(), 4096);\n        assert_eq!(emissions.len(), 192);\n        assert_eq!(scales.len(), observations.len()+1);')
    wrapper=wrapper.replace('forward, backward, products)','forward, backward, products, emissions, scales)')
    s=s[:end]+wrapper+s[end:]
    start=s.index('    #[target_feature(enable = "avx")]\n    pub(super) unsafe fn counts_sequence64(');end=s.index('    #[target_feature(enable = "avx")]',start+10)
    function=s[start:end].replace('counts_sequence64','counts_emissions64').replace('products: &[f64])','products: &[f64], emissions: &mut [f64], scales: &[f64])')
    needle='            }\n        }\n    }'
    assert function.count(needle)==1
    function=function.replace(needle,'''                for u in begin..end {
                    let z = *observations.get_unchecked(u-1) as usize;
                    let scale = _mm256_set1_pd(*scales.get_unchecked(u));
                    for k in (0..64).step_by(4) {
                        let f = _mm256_loadu_pd(forward.as_ptr().add(u*64+k));
                        let b = _mm256_loadu_pd(backward.as_ptr().add(u*64+k));
                        let p = emissions.as_mut_ptr().add(z*64+k);
                        let contribution = _mm256_mul_pd(_mm256_mul_pd(f,b),scale);
                        _mm256_storeu_pd(p,_mm256_add_pd(_mm256_loadu_pd(p),contribution));
                    }
                }
            }
        }
    }''')
    s=s[:end]+function+'\n'+s[end:];path.write_text(s)
    lib=path.parent/'lib.rs';s=lib.read_text().replace('avx.counts_sequence64(','avx.counts_emissions64(')
    token='                &prepared.emission_transition,\n            );'
    assert s.count(token)==1
    s=s.replace(token,'                &prepared.emission_transition,\n                &mut counts.e,\n                &messages.scales,\n            );')
    start=s.index('        for u in 1..length {');end=s.index('        for (((count, &initial)',start)
    s=s[:start]+'        if sequence_counts.is_none() {\n'+s[start:end]+'        }\n'+s[end:];lib.write_text(s)
    path.write_text(path.read_text()+Path('bench/exhaust_fusion_tests.rs').read_text())
e.generate=generate
e.RAW=Path('work/exhaust/fusion');e.REPORT='bench/exhaust-fusion.json'
e.CONFIGS={'combined':(1,16,16),'fusion':(2,16,16)}
if __name__=='__main__':getattr(e,sys.argv[1])()

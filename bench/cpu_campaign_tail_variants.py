"""AVX masked tails preserve live lanes and never access inactive addresses."""
from cpu_campaign_kernel_variants import replace
from cpu_campaign_split64 import prepare as split64


def prepare(scratch,label):
    assert label in ('masked','masked-wide')
    if label=='masked-wide': split64(scratch)
    path=scratch/'crates/psmc-cpu/src/simd.rs'
    mask='_mm256_set_epi64x(0, if n-end>2 {-1} else {0}, if n-end>1 {-1} else {0}, -1)'
    old='''        for k in end..n {
            let mut sum = 0.0;
            for (l, &f) in previous.iter().enumerate() {
                sum += f * matrix[l * n + k];
            }
            out[k] = emission[k] * sum;
        }'''
    new='''        if end < n {
            // SAFETY: only n-end (1..3) low lanes are active. Masked-off lanes
            // neither load nor store memory, including the final matrix row.
            unsafe {
                let mask = MASK;
                let mut sum = _mm256_setzero_pd();
                for (l, &f) in previous.iter().enumerate() {
                    let a = _mm256_maskload_pd(matrix.as_ptr().add(l*n+end),mask);
                    sum = _mm256_add_pd(sum,_mm256_mul_pd(_mm256_set1_pd(f),a));
                }
                let e = _mm256_maskload_pd(emission.as_ptr().add(end),mask);
                _mm256_maskstore_pd(out.as_mut_ptr().add(end),mask,_mm256_mul_pd(e,sum));
            }
        }'''.replace('MASK',mask)
    replace(path,old,new)
    old='''        for k in end..n {
            let mut sum = 0.0;
            for (l, &b) in next.iter().enumerate() {
                sum += transpose[l * n + k] * b;
            }
            out[k] = sum / scale;
        }'''
    new='''        if end < n {
            // SAFETY: safe wrapper checks dimensions; only existing tail lanes
            // are active. Independent sums retain the original ascending order.
            unsafe {
                let mask = MASK;
                let mut sum = _mm256_setzero_pd();
                for (l, &b) in next.iter().enumerate() {
                    let ae = _mm256_maskload_pd(transpose.as_ptr().add(l*n+end),mask);
                    sum = _mm256_add_pd(sum,_mm256_mul_pd(ae,_mm256_set1_pd(b)));
                }
                _mm256_maskstore_pd(out.as_mut_ptr().add(end),mask,_mm256_div_pd(sum,_mm256_set1_pd(scale)));
            }
        }'''.replace('MASK',mask)
    replace(path,old,new)
    old='''            for l in end..n {
                row[l] += f * ae[l] * next[l];
            }'''
    new='''            if end < n {
                // SAFETY: active lanes are exactly end..n in all three slices.
                // Masked-off values are never stored and enter no reduction.
                unsafe {
                    let mask = MASK;
                    let first = _mm256_mul_pd(_mm256_set1_pd(f),_mm256_maskload_pd(ae.as_ptr().add(end),mask));
                    let contribution = _mm256_mul_pd(first,_mm256_maskload_pd(next.as_ptr().add(end),mask));
                    let old = _mm256_maskload_pd(row.as_ptr().add(end),mask);
                    _mm256_maskstore_pd(row.as_mut_ptr().add(end),mask,_mm256_add_pd(old,contribution));
                }
            }'''.replace('MASK',mask)
    replace(path,old,new)
    if label=='masked': replace(path,'for n in 1..=13 {','for n in (1..=33).chain([63,64,65]) {')
    with path.open('a') as file:
        file.write('''
#[cfg(all(test,target_os="linux",target_arch="x86_64"))]
mod guarded_tail_tests {
    use super::*;
    use std::ffi::{c_int,c_long,c_void};
    unsafe extern "C" {
        fn getpagesize()->c_int;
        fn mmap(address:*mut c_void,length:usize,prot:c_int,flags:c_int,fd:c_int,offset:c_long)->*mut c_void;
        fn mprotect(address:*mut c_void,length:usize,prot:c_int)->c_int;
        fn munmap(address:*mut c_void,length:usize)->c_int;
    }
    struct Guarded { base:*mut u8,page:usize,length:usize }
    impl Guarded {
        fn new(length:usize,value:f64)->Self {
            // SAFETY: anonymous private mapping is owned by this object. The
            // second page is inaccessible, and the initialized slice ends at it.
            unsafe {
                let page=getpagesize() as usize;
                assert!(page>0 && length*8<=page);
                let base=mmap(std::ptr::null_mut(),2*page,3,0x22,-1,0).cast::<u8>();
                assert_ne!(base as usize,usize::MAX);
                assert_eq!(mprotect(base.add(page).cast(),page,0),0);
                let mut result=Self{base,page,length};
                result.values_mut().fill(value);
                result
            }
        }
        fn values(&self)->&[f64] {
            // SAFETY: initialized in-bounds region; lifetime bound to this owner.
            unsafe { std::slice::from_raw_parts(self.base.add(self.page-self.length*8).cast(),self.length) }
        }
        fn values_mut(&mut self)->&mut [f64] {
            // SAFETY: unique owner borrow and initialized writable first page.
            unsafe { std::slice::from_raw_parts_mut(self.base.add(self.page-self.length*8).cast(),self.length) }
        }
    }
    impl Drop for Guarded {
        fn drop(&mut self) {
            // SAFETY: the complete original mapping belongs exclusively to self.
            assert_eq!(unsafe{munmap(self.base.cast(),2*self.page)},0);
        }
    }
    #[test]
    fn inactive_tail_lanes_never_touch_guard_pages() {
        let Some(avx)=Avx::select(SimdMode::Auto,4).unwrap() else{return;};
        for n in [5,6,7] {
            let matrix=Guarded::new(n*n,0.125);
            let f=Guarded::new(n,0.25);
            let b=Guarded::new(n,0.75);
            let mut out=Guarded::new(n,0.0);
            let mut counts=Guarded::new(n*n,1e-25);
            avx.forward(out.values_mut(),f.values(),matrix.values(),b.values());
            for k in 0..n {
                let mut sum=0.0;
                for l in 0..n {sum+=f.values()[l]*matrix.values()[l*n+k];}
                assert_eq!(out.values()[k].to_bits(),(b.values()[k]*sum).to_bits());
            }
            avx.backward(out.values_mut(),b.values(),matrix.values(),1.25);
            for k in 0..n {
                let mut sum=0.0;
                for l in 0..n {sum+=matrix.values()[l*n+k]*b.values()[l];}
                assert_eq!(out.values()[k].to_bits(),(sum/1.25).to_bits());
            }
            avx.counts(counts.values_mut(),f.values(),matrix.values(),b.values());
            for k in 0..n {for l in 0..n {
                assert_eq!(counts.values()[k*n+l].to_bits(),(1e-25+f.values()[k]*matrix.values()[k*n+l]*b.values()[l]).to_bits());
            }}
        }
    }
}
''')

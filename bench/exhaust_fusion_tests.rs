#[cfg(test)]
mod fusion_tests {
    use super::*;
    #[test]
    fn tiled_emissions_preserve_site_order_masks_tiny_counts_and_last_site_omission() {
        let Some(avx) = Avx::select(SimdMode::Auto,64).unwrap() else {return;};
        let values=[0.0,-0.0,f64::from_bits(1),-f64::from_bits(1),1e-300,1e300,0.1,-1.0,f64::INFINITY,f64::NEG_INFINITY,f64::NAN];
        for length in [1,2,3,7,8,9,15,16,17,31,32,33,63,64,65,129] {
            for mode in 0..3 {
                let make=|count:usize,salt:usize|->Vec<f64>{(0..count).map(|i|if mode==0 {((i*17+salt)%103) as f64/107.0} else {values[(i*7+salt)%if mode==1 {8}else{values.len()}]}).collect()};
                let cells=(length+1)*64;
                let f=make(cells+1,1);let b=make(cells+1,3);let p=make(12288+1,7);let scales=make(length+2,2);
                for mask in 0..4 {
                    let obs:Vec<u8>=(0..length).map(|u|if mask==3 {(u%3) as u8}else{mask}).collect();
                    let mut a=vec![1e-25;4097];let mut e=vec![1e-25;194];
                    let mut ra=vec![1e-25;4096];let mut re=vec![1e-25;192];
                    for u in 1..length {
                        for k in 0..64 {
                            for l in 0..64 {ra[k*64+l]+=(f[1+u*64+k]*p[1+obs[u] as usize*4096+k*64+l])*b[1+(u+1)*64+l];}
                            re[obs[u-1] as usize*64+k]+=(f[1+u*64+k]*b[1+u*64+k])*scales[1+u];
                        }
                    }
                    avx.counts_emissions64(&mut a[1..],&obs,&f[1..],&b[1..],&p[1..],&mut e[1..193],&scales[1..]);
                    for (&actual,&expected) in a[1..].iter().zip(&ra).chain(e[1..193].iter().zip(&re)) {
                        if expected.is_nan() {assert!(actual.is_nan());}else{assert_eq!(actual.to_bits(),expected.to_bits());}
                    }
                    assert_eq!(a[0],1e-25);assert_eq!(e[0],1e-25);assert_eq!(e[193],1e-25);
                }
            }
        }
    }
    #[test]
    fn fused_count_shapes_reject_before_access() {
        let Some(avx)=Avx::select(SimdMode::Auto,64).unwrap() else {return;};
        for (emissions,scales) in [(191,3),(193,3),(192,2),(192,4)] {
            assert!(std::panic::catch_unwind(||avx.counts_emissions64(&mut vec![0.0;4096],&[0,1],&vec![0.0;192],&vec![0.0;192],&vec![0.0;12288],&mut vec![0.0;emissions],&vec![1.0;scales])).is_err());
        }
    }
}

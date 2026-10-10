#[cfg(test)]
mod normalization_tests {
    use super::*;
    #[test]
    fn ordered_division_matches_scalar_with_tails_and_ieee_extremes() {
        let Some(avx) = Avx::select(SimdMode::Auto, 64).unwrap() else { return; };
        let values = [0.0, -0.0, f64::from_bits(1), -f64::from_bits(1), f64::MIN_POSITIVE,
            0.1, -1.0, 1e-300, 1e300, f64::INFINITY, f64::NEG_INFINITY, f64::NAN];
        for n in [0,1,2,3,4,7,8,15,16,17,23,31,32,33,63,64,65,129] {
            for offset in 0..values.len() {
                for &scale in &values {
                    let input:Vec<_>=(0..n).map(|k|values[(k+offset)%values.len()]).collect();
                    let expected:Vec<_>=input.iter().map(|&v|v/scale).collect();
                    let mut out=vec![123.0;n+2];out[1..n+1].copy_from_slice(&input);
                    avx.normalize(&mut out[1..n+1],scale);
                    for (&a,&e) in out[1..n+1].iter().zip(&expected) {
                        if e.is_nan() {assert!(a.is_nan());} else {assert_eq!(a.to_bits(),e.to_bits());}
                    }
                    assert_eq!(out[0],123.0);assert_eq!(out[n+1],123.0);
                }
            }
        }
    }
}

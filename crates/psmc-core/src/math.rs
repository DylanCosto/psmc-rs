//! Same libm entry points as the pinned C oracle on the supported Linux stack.
//! Safety is isolated here: these C functions take and return scalar doubles.
#[link(name = "m")]
unsafe extern "C" {
    #[link_name = "log"]
    fn c_log(x: f64) -> f64;
    #[link_name = "exp"]
    fn c_exp(x: f64) -> f64;
}

#[inline]
pub fn ln(x: f64) -> f64 {
    // SAFETY: libm log accepts every IEEE754 double, including NaN/Inf/domain errors.
    unsafe { c_log(x) }
}

#[inline]
pub fn exp(x: f64) -> f64 {
    // SAFETY: libm exp accepts every IEEE754 double; no pointers or owned state.
    unsafe { c_exp(x) }
}

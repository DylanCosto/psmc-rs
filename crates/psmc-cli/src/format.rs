//! Match libc printf's legacy float formatting, including signed NaN and %g.
//! The inference implementation is Rust; this audited boundary formats scalars.
use std::ffi::{CStr, c_char, c_int};

unsafe extern "C" {
    fn snprintf(buffer: *mut c_char, size: usize, format: *const c_char, ...) -> c_int;
}

pub fn float(value: f64, precision: usize, general: bool) -> String {
    let mut bytes = [0_u8; 512]; // ample for any finite f64 in fixed form plus <=17 decimals
    let precision: c_int = precision.try_into().expect("small formatting precision");
    let format = if general { c"%.*g" } else { c"%.*f" };
    // SAFETY: buffer has the supplied writable capacity; the static format has
    // exactly an int then a double argument and is NUL-terminated. snprintf
    // writes at most capacity bytes including NUL. No untrusted format strings.
    let len = unsafe {
        snprintf(
            bytes.as_mut_ptr().cast(),
            bytes.len(),
            format.as_ptr(),
            precision,
            value,
        )
    };
    assert!(
        len >= 0 && (len as usize) < bytes.len(),
        "float format exceeded bounded buffer"
    );
    // SAFETY: successful bounded snprintf above always adds a terminal NUL.
    unsafe { CStr::from_ptr(bytes.as_ptr().cast()) }
        .to_str()
        .expect("ASCII numeric output")
        .to_owned()
}

pub fn f(value: f64) -> String {
    float(value, 6, false)
}
pub fn g(value: f64) -> String {
    float(value, 6, true)
}

//! Small system-zlib input boundary. Tested target: Linux with libz.so.1.
//!
//! zlib transparently reads gzip and plain files; none of the inference uses FFI.
//! The input handle is owned, never shared, and always closed. stdin is duplicated
//! before gzdopen so closing this handle does not close the process's stdin.

use std::ffi::{CStr, CString, c_char, c_int, c_uint, c_void};
use std::ptr::NonNull;

#[cfg_attr(
    target_os = "linux",
    link(name = "libz.so.1", kind = "dylib", modifiers = "+verbatim")
)]
#[cfg_attr(not(target_os = "linux"), link(name = "z"))]
unsafe extern "C" {
    fn gzopen(path: *const c_char, mode: *const c_char) -> *mut c_void;
    fn gzdopen(fd: c_int, mode: *const c_char) -> *mut c_void;
    fn gzread(file: *mut c_void, buffer: *mut c_void, len: c_uint) -> c_int;
    fn gzerror(file: *mut c_void, error: *mut c_int) -> *const c_char;
    fn gzclose(file: *mut c_void) -> c_int;
}

unsafe extern "C" {
    fn dup(fd: c_int) -> c_int;
    fn close(fd: c_int) -> c_int;
}

struct Input(NonNull<c_void>);

impl Drop for Input {
    fn drop(&mut self) {
        // SAFETY: this handle was returned by gzopen/gzdopen; Input is its sole
        // owner, and Drop runs once after all reads and error-message copies.
        unsafe {
            gzclose(self.0.as_ptr());
        }
    }
}

impl Input {
    fn error(&self) -> String {
        let mut code = 0;
        // SAFETY: the handle remains live; zlib's error string belongs to it,
        // is NUL terminated, and is copied before another zlib call or Drop.
        unsafe {
            let ptr = gzerror(self.0.as_ptr(), &mut code);
            if ptr.is_null() {
                format!("zlib read error {code}")
            } else {
                CStr::from_ptr(ptr).to_string_lossy().into_owned()
            }
        }
    }
}

pub(crate) fn read(path: &str) -> Result<Vec<u8>, String> {
    let mode = c"rb";
    let handle = if path == "-" {
        // SAFETY: dup accepts any descriptor, reporting failure with -1. The
        // duplicate is either transferred to zlib or closed on gzdopen failure.
        let fd = unsafe { dup(0) };
        if fd < 0 {
            return Err(format!(
                "cannot duplicate stdin: {}",
                std::io::Error::last_os_error()
            ));
        }
        // SAFETY: fd is an open owned descriptor and mode is a C string.
        let ptr = unsafe { gzdopen(fd, mode.as_ptr()) };
        if ptr.is_null() {
            // SAFETY: ownership was not transferred because gzdopen failed.
            unsafe {
                close(fd);
            }
            return Err("cannot open stdin with zlib".into());
        }
        ptr
    } else {
        let name = CString::new(path).map_err(|_| "input path contains NUL".to_string())?;
        // SAFETY: both C strings live for the duration of gzopen; the returned
        // pointer is checked for null and wrapped in an exclusively owned Input.
        unsafe { gzopen(name.as_ptr(), mode.as_ptr()) }
    };
    let input = Input(
        NonNull::new(handle)
            .ok_or_else(|| format!("cannot open {path}: {}", std::io::Error::last_os_error()))?,
    );
    let mut result = Vec::new();
    let mut buffer = [0_u8; 65_536];
    loop {
        // SAFETY: buffer has exactly the advertised writable extent. The zlib
        // handle is valid, exclusively owned, and never accessed concurrently.
        let n = unsafe {
            gzread(
                input.0.as_ptr(),
                buffer.as_mut_ptr().cast(),
                buffer.len() as c_uint,
            )
        };
        if n < 0 {
            return Err(format!("cannot read {path}: {}", input.error()));
        }
        if n == 0 {
            let mut code = 0;
            // SAFETY: valid handle and writable error-code pointer. Check the
            // code even at EOF: truncated gzip streams can produce Z_BUF_ERROR.
            unsafe {
                gzerror(input.0.as_ptr(), &mut code);
            }
            if code != 0 && code != 1 {
                return Err(format!("cannot read {path}: {}", input.error()));
            }
            break;
        }
        result
            .try_reserve(n as usize)
            .map_err(|_| "input is too large to allocate".to_string())?;
        result.extend_from_slice(&buffer[..n as usize]);
    }
    Ok(result)
}

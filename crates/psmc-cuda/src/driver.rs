//! Audited Linux CUDA Driver/NVRTC boundary. No link-time CUDA dependency.
//! Handles and allocations stay on their creating thread (Rc marker). All host
//! copies are synchronous; kernel completion is checked before results are read.
use std::{
    ffi::{CStr, CString, c_char, c_int, c_uint, c_void},
    marker::PhantomData,
    ptr,
    rc::Rc,
    sync::OnceLock,
};
type Handle = *mut c_void;
type DevicePtr = u64;
type Result<T> = std::result::Result<T, String>;
#[link(name = "dl")]
unsafe extern "C" {
    fn dlopen(name: *const c_char, flags: c_int) -> Handle;
    fn dlsym(handle: Handle, name: *const c_char) -> Handle;
    fn dlclose(handle: Handle) -> c_int;
    fn dlerror() -> *const c_char;
}
struct Library(Handle);
impl Library {
    fn open(name: &str) -> Result<Self> {
        let name = CString::new(name).map_err(|_| "library path contains NUL")?;
        // SAFETY: name is terminated and valid throughout dlopen; RTLD_NOW=2.
        let handle = unsafe { dlopen(name.as_ptr(), 2) };
        if handle.is_null() {
            let error = unsafe { dlerror() };
            return Err(if error.is_null() {
                "dlopen failed".into()
            } else {
                unsafe { CStr::from_ptr(error) }
                    .to_string_lossy()
                    .into_owned()
            });
        }
        Ok(Self(handle))
    }
    fn symbol(&self, name: &CStr) -> Result<Handle> {
        let p = unsafe { dlsym(self.0, name.as_ptr()) };
        if p.is_null() {
            Err(format!("missing CUDA symbol {}", name.to_string_lossy()))
        } else {
            Ok(p)
        }
    }
}
impl Drop for Library {
    fn drop(&mut self) {
        unsafe {
            dlclose(self.0);
        }
    }
}
// Each symbol's declared type follows the official CUDA Driver/NVRTC C ABI.
// Libraries outlive all copied function pointers and all owned CUDA handles.
macro_rules! api {
    ($name:ident { $($field:ident : $ty:ty = $symbol:literal),* $(,)? }) => {
        struct $name { $($field: $ty,)* _library: Library }
        impl $name { fn load(library: Library) -> Result<Self> {
            Ok(Self { $($field: unsafe { std::mem::transmute::<Handle, $ty>(library.symbol($symbol)?) },)* _library: library })
        } }
    }
}
api!(Nvrtc {
    create: unsafe extern "C" fn(*mut Handle,*const c_char,*const c_char,c_int,*const *const c_char,*const *const c_char)->c_int = c"nvrtcCreateProgram",
    compile: unsafe extern "C" fn(Handle,c_int,*const *const c_char)->c_int = c"nvrtcCompileProgram",
    log_size: unsafe extern "C" fn(Handle,*mut usize)->c_int = c"nvrtcGetProgramLogSize",
    log: unsafe extern "C" fn(Handle,*mut c_char)->c_int = c"nvrtcGetProgramLog",
    size: unsafe extern "C" fn(Handle,*mut usize)->c_int = c"nvrtcGetPTXSize",
    ptx: unsafe extern "C" fn(Handle,*mut c_char)->c_int = c"nvrtcGetPTX",
    destroy: unsafe extern "C" fn(*mut Handle)->c_int = c"nvrtcDestroyProgram",
});
fn check(code: c_int, operation: &str) -> Result<()> {
    if code == 0 {
        Ok(())
    } else {
        Err(format!(
            "{operation} failed (CUDA/NVRTC status {code}); no CPU fallback performed"
        ))
    }
}
fn compile() -> Result<Vec<u8>> {
    let library = if let Ok(path) = std::env::var("PSMC_NVRTC_LIBRARY") {
        Library::open(&path)?
    } else {
        Library::open("libnvrtc.so")
            .or_else(|_| Library::open("libnvrtc.so.12"))
            .or_else(|_| Library::open("libnvrtc.so.13"))
            .map_err(|e| {
                format!("NVRTC unavailable: {e}; set PSMC_NVRTC_LIBRARY to its library path")
            })?
    };
    let nv = Nvrtc::load(library)?;
    let source = CString::new(include_str!("counts.cu")).unwrap();
    let mut program = ptr::null_mut();
    unsafe {
        check(
            (nv.create)(
                &mut program,
                source.as_ptr(),
                c"psmc_counts.cu".as_ptr(),
                0,
                ptr::null(),
                ptr::null(),
            ),
            "nvrtcCreateProgram",
        )?;
    }
    // Explicit nonfused round-to-nearest intrinsics in the kernel, plus compiler
    // safeguards. compute_75 PTX permits driver JIT on Turing and newer GPUs.
    let flags = [
        c"--gpu-architecture=compute_75",
        c"--std=c++11",
        c"--fmad=false",
        c"--ftz=false",
        c"--prec-div=true",
        c"--prec-sqrt=true",
    ];
    let pointers: Vec<_> = flags.iter().map(|s| s.as_ptr()).collect();
    let result = (|| unsafe {
        let code = (nv.compile)(program, pointers.len() as c_int, pointers.as_ptr());
        if code != 0 {
            let mut size = 0;
            check((nv.log_size)(program, &mut size), "nvrtcGetProgramLogSize")?;
            let mut log = vec![0u8; size.max(1)];
            check(
                (nv.log)(program, log.as_mut_ptr().cast()),
                "nvrtcGetProgramLog",
            )?;
            return Err(format!(
                "NVRTC compilation failed ({code}): {}",
                String::from_utf8_lossy(&log)
            ));
        }
        let mut size = 0;
        check((nv.size)(program, &mut size), "nvrtcGetPTXSize")?;
        let mut ptx = vec![0u8; size];
        check((nv.ptx)(program, ptx.as_mut_ptr().cast()), "nvrtcGetPTX")?;
        Ok(ptx)
    })();
    unsafe {
        (nv.destroy)(&mut program);
    }
    result
}
static PTX: OnceLock<Result<Vec<u8>>> = OnceLock::new();
api!(Driver {
    init: unsafe extern "C" fn(c_uint)->c_int = c"cuInit",
    device: unsafe extern "C" fn(*mut c_int,c_int)->c_int = c"cuDeviceGet",
    retain: unsafe extern "C" fn(*mut Handle,c_int)->c_int = c"cuDevicePrimaryCtxRetain",
    release: unsafe extern "C" fn(c_int)->c_int = c"cuDevicePrimaryCtxRelease_v2",
    current: unsafe extern "C" fn(Handle)->c_int = c"cuCtxSetCurrent",
    load: unsafe extern "C" fn(*mut Handle,*const c_void)->c_int = c"cuModuleLoadData",
    unload: unsafe extern "C" fn(Handle)->c_int = c"cuModuleUnload",
    function: unsafe extern "C" fn(*mut Handle,Handle,*const c_char)->c_int = c"cuModuleGetFunction",
    alloc: unsafe extern "C" fn(*mut DevicePtr,usize)->c_int = c"cuMemAlloc_v2",
    free: unsafe extern "C" fn(DevicePtr)->c_int = c"cuMemFree_v2",
    htod: unsafe extern "C" fn(DevicePtr,*const c_void,usize)->c_int = c"cuMemcpyHtoD_v2",
    dtoh: unsafe extern "C" fn(*mut c_void,DevicePtr,usize)->c_int = c"cuMemcpyDtoH_v2",
    stream_create: unsafe extern "C" fn(*mut Handle,c_uint)->c_int = c"cuStreamCreate",
    stream_destroy: unsafe extern "C" fn(Handle)->c_int = c"cuStreamDestroy_v2",
    sync: unsafe extern "C" fn(Handle)->c_int = c"cuStreamSynchronize",
    launch: unsafe extern "C" fn(Handle,c_uint,c_uint,c_uint,c_uint,c_uint,c_uint,c_uint,Handle,*mut *mut c_void,*mut *mut c_void)->c_int = c"cuLaunchKernel",
});
#[derive(Default)]
struct Buffer {
    ptr: DevicePtr,
    capacity: usize,
}
pub struct Device {
    api: Driver,
    device: c_int,
    context: Handle,
    module: Handle,
    kernel: Handle,
    stream: Handle,
    buffers: [Buffer; 5], // f, next b, symbols, ae, counts
    _thread_bound: PhantomData<Rc<()>>,
}
impl Device {
    pub fn new() -> Result<Self> {
        let api = Driver::load(Library::open("libcuda.so.1")?)?;
        let mut device = 0;
        let mut context = ptr::null_mut();
        unsafe {
            check((api.init)(0), "cuInit")?;
            check((api.device)(&mut device, 0), "cuDeviceGet")?;
            check(
                (api.retain)(&mut context, device),
                "cuDevicePrimaryCtxRetain",
            )?;
        }
        // Construct ownership immediately: all later failure paths release handles.
        let mut result = Self {
            api,
            device,
            context,
            module: ptr::null_mut(),
            kernel: ptr::null_mut(),
            stream: ptr::null_mut(),
            buffers: std::array::from_fn(|_| Buffer::default()),
            _thread_bound: PhantomData,
        };
        result.activate()?;
        let ptx = PTX.get_or_init(compile).as_ref().map_err(Clone::clone)?;
        unsafe {
            check(
                (result.api.load)(&mut result.module, ptx.as_ptr().cast()),
                "cuModuleLoadData",
            )?;
            check(
                (result.api.function)(&mut result.kernel, result.module, c"counts".as_ptr()),
                "cuModuleGetFunction",
            )?;
            check(
                (result.api.stream_create)(&mut result.stream, 1),
                "cuStreamCreate",
            )?;
        }
        Ok(result)
    }
    fn activate(&self) -> Result<()> {
        unsafe { check((self.api.current)(self.context), "cuCtxSetCurrent") }
    }
    fn ensure(&mut self, index: usize, bytes: usize) -> Result<()> {
        self.activate()?;
        let b = &mut self.buffers[index];
        if bytes > b.capacity {
            if b.ptr != 0 {
                unsafe {
                    check((self.api.free)(b.ptr), "cuMemFree")?;
                }
                b.ptr = 0;
                b.capacity = 0;
            }
            unsafe {
                check((self.api.alloc)(&mut b.ptr, bytes), "cuMemAlloc")?;
            }
            b.capacity = bytes;
        }
        Ok(())
    }
    fn upload_f64(&mut self, index: usize, values: &[f64]) -> Result<()> {
        self.ensure(index, std::mem::size_of_val(values))?;
        unsafe {
            check(
                (self.api.htod)(
                    self.buffers[index].ptr,
                    values.as_ptr().cast(),
                    std::mem::size_of_val(values),
                ),
                "cuMemcpyHtoD",
            )
        }
    }
    pub fn prepare(&mut self, ae: &[f64]) -> Result<()> {
        self.upload_f64(3, ae)
    }
    /// Caller validates dimensions, symbols, and n/sites fit i32. CUDA receives
    /// contiguous rows and one symbol per row. Each thread owns one count cell.
    pub fn tile(
        &mut self,
        f: &[f64],
        b: &[f64],
        obs: &[u8],
        out: &mut [f64],
        n: usize,
        reset: bool,
        last: bool,
    ) -> Result<()> {
        let cells = n.checked_mul(n).ok_or("count shape overflow")?;
        if n == 0
            || n > i32::MAX as usize
            || obs.is_empty()
            || obs.len() > i32::MAX as usize
            || f.len() != obs.len() * n
            || b.len() != f.len()
            || out.len() != cells
            || self.buffers[3].capacity != 3 * cells * 8
            || obs.iter().any(|&s| s > 2)
        {
            return Err("invalid CUDA count tile shape".into());
        }
        self.upload_f64(0, f)?;
        self.upload_f64(1, b)?;
        self.ensure(2, obs.len())?;
        self.ensure(4, std::mem::size_of_val(out))?;
        unsafe {
            check(
                (self.api.htod)(self.buffers[2].ptr, obs.as_ptr().cast(), obs.len()),
                "cuMemcpyHtoD observations",
            )?;
        }
        let mut pointers: [DevicePtr; 5] = std::array::from_fn(|i| self.buffers[i].ptr);
        let mut states = n as i32;
        let mut sites = obs.len() as i32;
        let mut init = i32::from(reset);
        let mut args: Vec<*mut c_void> = pointers
            .iter_mut()
            .map(|p| (p as *mut DevicePtr).cast())
            .collect();
        args.extend([
            (&mut states as *mut i32).cast(),
            (&mut sites as *mut i32).cast(),
            (&mut init as *mut i32).cast(),
        ]);
        unsafe {
            // Pageable synchronous HtoD may return after staging, before the DMA
            // has completed. Our nonblocking compute stream does not inherit a
            // legacy-default-stream dependency: explicitly finish its uploads.
            check(
                (self.api.sync)(ptr::null_mut()),
                "cuStreamSynchronize uploads",
            )?;
            check(
                (self.api.launch)(
                    self.kernel,
                    cells.div_ceil(128) as u32,
                    1,
                    1,
                    128,
                    1,
                    1,
                    0,
                    self.stream,
                    args.as_mut_ptr(),
                    ptr::null_mut(),
                ),
                "cuLaunchKernel",
            )?;
            // Synchronize this worker's stream, not the entire primary context.
            check((self.api.sync)(self.stream), "cuStreamSynchronize")?;
            if last {
                check(
                    (self.api.dtoh)(
                        out.as_mut_ptr().cast(),
                        self.buffers[4].ptr,
                        std::mem::size_of_val(out),
                    ),
                    "cuMemcpyDtoH",
                )?;
            }
        }
        Ok(())
    }
}
impl Drop for Device {
    fn drop(&mut self) {
        unsafe {
            // No unchecked async access to host memory exists. On an error we
            // still drain work before freeing; driver cleanup errors are ignored.
            (self.api.current)(self.context);
            if !self.stream.is_null() {
                (self.api.sync)(self.stream);
            }
            for b in &self.buffers {
                if b.ptr != 0 {
                    (self.api.free)(b.ptr);
                }
            }
            if !self.stream.is_null() {
                (self.api.stream_destroy)(self.stream);
            }
            if !self.module.is_null() {
                (self.api.unload)(self.module);
            }
            (self.api.release)(self.device);
        }
    }
}
#[cfg(test)]
mod tests {
    #[test]
    fn kernel_uses_explicit_nonfused_rounding() {
        let source = include_str!("counts.cu");
        assert!(source.contains("__dadd_rn"));
        assert!(source.contains("__dmul_rn"));
        assert!(!source.contains("atomicAdd"));
    }
    #[test]
    #[ignore = "requires a CUDA GPU and NVRTC; executed explicitly by GPU gate"]
    fn ptx_has_no_fma() {
        let ptx = super::compile().unwrap();
        let source = String::from_utf8(ptx).unwrap();
        assert!(!source.contains("fma.rn.f64"));
        assert!(source.contains("add.rn.f64"));
        assert!(source.contains("mul.rn.f64"));
    }
}

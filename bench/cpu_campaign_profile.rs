//! Linux-only diagnostic instrumentation, injected into a disposable source copy.
//! Never linked into the delivered inference executable or used for speed claims.
use std::cell::RefCell;
#[repr(C)]
struct Timespec { seconds: std::ffi::c_long, nanoseconds: std::ffi::c_long }
unsafe extern "C" { fn clock_gettime(clock: std::ffi::c_int, value: *mut Timespec) -> std::ffi::c_int; }
const LABELS: [&str; 12] = ["expectation_inclusive", "prepare", "model_update", "q", "normalizer", "workspace_setup", "forward", "backward", "likelihood_check", "counts", "fit_process_main", "iteration_inclusive"];
thread_local! {
    static TOTALS: RefCell<([u64; 12], [u64; 12], [u64; 2])> = const { RefCell::new(([0; 12], [0; 12], [0; 2])) };
}
pub fn now() -> u64 {
    let mut value = Timespec { seconds: 0, nanoseconds: 0 };
    // SAFETY: Linux CLOCK_THREAD_CPUTIME_ID=3, writable correctly laid-out timespec.
    assert_eq!(unsafe { clock_gettime(3, &mut value) }, 0);
    value.seconds as u64 * 1_000_000_000 + value.nanoseconds as u64
}
pub fn record(index: usize, start: u64) {
    let elapsed = now() - start;
    TOTALS.with(|totals| { let mut t = totals.borrow_mut(); t.0[index] += elapsed; t.1[index] += 1; });
}
pub struct Guard(usize, u64);
impl Guard { pub fn new(index: usize) -> Self { Self(index, now()) } }
impl Drop for Guard { fn drop(&mut self) { record(self.0, self.1); } }
pub fn math_call(index: usize) { TOTALS.with(|totals| totals.borrow_mut().2[index] += 1); }
pub fn dump() {
    let path = std::env::var("PSMC_CPU_DIAGNOSTIC").expect("diagnostic output path required");
    // Measured separately after fitting; a lower-level clock-overhead estimate,
    // not a correction subtracted from the reported sections.
    let calibration_start = now();
    for _ in 0..20_000 { std::hint::black_box(now()); }
    let clock_ns_per_call = (now() - calibration_start) as f64 / 20_000.0;
    let result = TOTALS.with(|totals| {
        let t = totals.borrow();
        let mut s = String::from("{\"clock\":\"CLOCK_THREAD_CPUTIME_ID\",\"sections\":{");
        for (i, label) in LABELS.iter().enumerate() {
            if i != 0 { s.push(','); }
            s.push_str(&format!("\"{label}\":{{\"nanoseconds\":{},\"calls\":{}}}", t.0[i], t.1[i]));
        }
        s.push_str(&format!("}},\"log_calls\":{},\"exp_calls\":{},\"clock_ns_per_call\":{clock_ns_per_call}}}\n", t.2[0], t.2[1]));
        s
    });
    std::fs::write(path, result).unwrap();
}

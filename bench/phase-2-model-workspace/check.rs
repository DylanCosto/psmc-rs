// Synthetic differential fixture. See README.md for source/license provenance.
#[path = "../../crates/psmc-core/src/math.rs"]
mod math;
#[path = "../../crates/psmc-core/src/model.rs"]
mod model;
#[path = "../../crates/psmc-core/src/model_workspace.rs"]
mod model_workspace;
#[path = "../../crates/psmc-core/src/rng.rs"]
mod rng;
#[derive(Clone, Debug)]
pub struct Pattern {
    pub text: String,
    pub groups: Vec<usize>,
    pub n_free: usize,
}
impl Pattern {
    pub fn states(&self) -> usize {
        self.groups.len()
    }
}
#[derive(Clone, Debug)]
pub struct Settings {
    pub pattern: Pattern,
    pub max_t: f64,
    pub alpha: f64,
    pub tr_ratio: f64,
    pub ran_init: f64,
    pub divergence: Option<f64>,
    pub initial_params: Option<Vec<f64>>,
    pub explicit_times: Option<Vec<f64>>,
}
fn out(v: &[f64]) {
    use std::io::Write;
    for x in v {
        std::io::stdout().write_all(&x.to_ne_bytes()).unwrap()
    }
}
fn main() {
    let reuse = match std::env::args().nth(1).as_deref() {
        Some("dense") => false,
        Some("workspace") => true,
        Some("benchmark") => {
            benchmark();
            return;
        }
        Some("allocations") => {
            allocations();
            return;
        }
        _ => panic!("expected dense, workspace or allocations"),
    };
    let mut rng = rng::LegacyRng::new(42);
    for n in [1, 2, 4, 23, 64] {
        for mode in 0..6 {
            let s = Settings {
                pattern: Pattern {
                    text: String::new(),
                    groups: (0..n).map(|k| k / 3).collect(),
                    n_free: (n + 2) / 3,
                },
                max_t: 15.0,
                alpha: 0.1,
                tr_ratio: 4.0,
                ran_init: if mode >= 4 { 0.1 } else { 0.0 },
                divergence: if mode % 2 == 1 { Some(0.7) } else { None },
                initial_params: None,
                explicit_times: if mode == 2 || mode == 3 {
                    Some((0..n).map(|i| i as f64 * 0.3).collect())
                } else {
                    None
                },
            };
            let mut m = model::Model::new(&s, 23, 177, &mut rng);
            let mut workspace = model_workspace::ModelWorkspace::new(n);
            if reuse {
                workspace.update(&mut m, &s);
            }
            for _ in 0..2 {
                out(&m.params);
                out(&m.t);
                out(&m.sigma);
                out(&[m.c_pi, m.c_sigma]);
                out(&m.initial);
                out(&m.transition);
                out(&m.emission);
                out(&m.avg_times(&s));
                for i in 0..m.params.len() {
                    m.params[i] = m.params[i] * (1.0 + i as f64 * 0.01)
                }
                if reuse {
                    workspace.update(&mut m, &s);
                } else {
                    m.update(&s);
                }
            }
        }
    }
}

// Process-local counter: this standalone harness is single-threaded and is not
// used by production or Cargo's concurrent test runner.
#[cfg(allocation_probe)]
use std::alloc::{GlobalAlloc, Layout, System};
#[cfg(allocation_probe)]
use std::sync::atomic::{AtomicUsize, Ordering};
#[cfg(allocation_probe)]
struct CountingAllocator;
#[cfg(allocation_probe)]
static ALLOCATIONS: AtomicUsize = AtomicUsize::new(0);
#[cfg(allocation_probe)]
#[global_allocator]
static ALLOCATOR: CountingAllocator = CountingAllocator;
#[cfg(allocation_probe)]
unsafe impl GlobalAlloc for CountingAllocator {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        ALLOCATIONS.fetch_add(1, Ordering::Relaxed);
        // SAFETY: forward the caller's allocation layout to the system allocator.
        unsafe { System.alloc(layout) }
    }
    unsafe fn alloc_zeroed(&self, layout: Layout) -> *mut u8 {
        ALLOCATIONS.fetch_add(1, Ordering::Relaxed);
        // SAFETY: forward the caller's allocation layout to the system allocator.
        unsafe { System.alloc_zeroed(layout) }
    }
    unsafe fn realloc(&self, ptr: *mut u8, layout: Layout, new_size: usize) -> *mut u8 {
        ALLOCATIONS.fetch_add(1, Ordering::Relaxed);
        // SAFETY: this allocator delegates every allocation to System; the caller
        // supplies the live allocation and layout required by GlobalAlloc.
        unsafe { System.realloc(ptr, layout, new_size) }
    }
    unsafe fn dealloc(&self, ptr: *mut u8, layout: Layout) {
        // SAFETY: this allocator delegates every allocation to System; the caller
        // supplies the live allocation and layout required by GlobalAlloc.
        unsafe { System.dealloc(ptr, layout) }
    }
}
#[cfg(allocation_probe)]
fn allocations() {
    let n = 64;
    let settings = Settings {
        pattern: Pattern {
            text: String::new(),
            groups: (0..n).map(|k| k / 3).collect(),
            n_free: (n + 2) / 3,
        },
        max_t: 15.0,
        alpha: 0.1,
        tr_ratio: 4.0,
        ran_init: 0.0,
        divergence: None,
        initial_params: None,
        explicit_times: None,
    };
    let mut rng = rng::LegacyRng::new(42);
    let mut model = model::Model::new(&settings, 23, 177, &mut rng);
    let mut workspace = model_workspace::ModelWorkspace::new(n);
    let iterations = 1000;
    ALLOCATIONS.store(0, Ordering::Relaxed);
    for _ in 0..iterations {
        model.update(std::hint::black_box(&settings));
        std::hint::black_box(&model);
    }
    let dense = ALLOCATIONS.load(Ordering::Relaxed);
    ALLOCATIONS.store(0, Ordering::Relaxed);
    for _ in 0..iterations {
        workspace.update(std::hint::black_box(&mut model), &settings);
        std::hint::black_box(&model);
    }
    let reused = ALLOCATIONS.load(Ordering::Relaxed);
    println!("iterations={iterations} dense_allocations={dense} workspace_allocations={reused}");
    assert_eq!(dense, iterations * 6);
    assert_eq!(reused, 0);
}

#[cfg(not(allocation_probe))]
fn allocations() {
    panic!("allocation counter requires rustc --cfg allocation_probe");
}

fn benchmark() {
    let args: Vec<String> = std::env::args().collect();
    let reuse = match args[2].as_str() {
        "dense" => false,
        "workspace" => true,
        _ => panic!("invalid benchmark backend"),
    };
    let n: usize = args[3].parse().unwrap();
    let iterations: usize = args[4].parse().unwrap();
    let settings = Settings {
        pattern: Pattern {
            text: String::new(),
            groups: (0..n).map(|k| k / 3).collect(),
            n_free: (n + 2) / 3,
        },
        max_t: 15.0,
        alpha: 0.1,
        tr_ratio: 4.0,
        ran_init: 0.0,
        divergence: None,
        initial_params: None,
        explicit_times: None,
    };
    let mut rng = rng::LegacyRng::new(42);
    let mut model = model::Model::new(&settings, 23, 177, &mut rng);
    let mut workspace = model_workspace::ModelWorkspace::new(n);
    let base_theta = model.params[0];
    let start = std::time::Instant::now();
    if reuse {
        for i in 0..iterations {
            model.params[0] = base_theta * (1.0 + (i % 197) as f64 * 0.0001);
            workspace.update(std::hint::black_box(&mut model), &settings);
            std::hint::black_box(&model);
        }
    } else {
        for i in 0..iterations {
            model.params[0] = base_theta * (1.0 + (i % 197) as f64 * 0.0001);
            model.update(std::hint::black_box(&settings));
            std::hint::black_box(&model);
        }
    }
    println!("{:.9}", start.elapsed().as_secs_f64());
}

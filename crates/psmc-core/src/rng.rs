//! POSIX/glibc srand48/drand48 replay, explicit owned RNG state.
#[derive(Clone, Debug)]
pub struct LegacyRng {
    state: u64,
}

impl LegacyRng {
    pub fn new(seed: i64) -> Self {
        Self {
            state: ((seed as u32 as u64) << 16) | 0x330e,
        }
    }
    pub fn next_f64(&mut self) -> f64 {
        self.state = self.state.wrapping_mul(0x5deece66d).wrapping_add(0xb) & ((1_u64 << 48) - 1);
        self.state as f64 / (1_u64 << 48) as f64
    }
}

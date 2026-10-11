//! Optional Linux affinity policy, restricted to the process's allowed CPUs.
//! Reported maximum frequency is a heuristic; unknown topology stays unpinned.
#[derive(Clone, Debug)]
pub struct Cpu {
    pub id: usize,
    pub fast: bool,
}
#[cfg(target_os = "linux")]
unsafe extern "C" {
    fn sched_getaffinity(pid: i32, size: usize, mask: *mut usize) -> i32;
    fn sched_setaffinity(pid: i32, size: usize, mask: *const usize) -> i32;
}
pub fn discover() -> Vec<Cpu> {
    #[cfg(target_os = "linux")]
    {
        let mut mask = [0usize; 16];
        // SAFETY: kernel receives the exact size of the writable mask buffer.
        if unsafe { sched_getaffinity(0, std::mem::size_of_val(&mask), mask.as_mut_ptr()) } != 0 {
            return Vec::new();
        }
        let mut cpus = Vec::new();
        for id in 0..mask.len() * usize::BITS as usize {
            if mask[id / usize::BITS as usize] & (1usize << (id % usize::BITS as usize)) == 0 {
                continue;
            }
            let root = format!("/sys/devices/system/cpu/cpu{id}");
            let frequency = std::fs::read_to_string(format!("{root}/cpufreq/cpuinfo_max_freq"))
                .ok()
                .and_then(|s| s.trim().parse::<usize>().ok());
            let siblings =
                std::fs::read_to_string(format!("{root}/topology/thread_siblings_list")).ok();
            let primary = siblings
                .as_deref()
                .and_then(|s| s.split([',', '-']).next())
                .and_then(|s| s.trim().parse::<usize>().ok())
                .unwrap_or(id);
            let Some(frequency) = frequency else {
                return Vec::new();
            };
            cpus.push((id, frequency, id == primary));
        }
        let maximum = cpus.iter().map(|x| x.1).max().unwrap_or(0);
        cpus.sort_by_key(|&(id, freq, primary)| (std::cmp::Reverse(freq), !primary, id));
        return cpus
            .into_iter()
            .map(|(id, freq, _)| Cpu {
                id,
                fast: freq == maximum,
            })
            .collect();
    }
    #[cfg(not(target_os = "linux"))]
    Vec::new()
}
pub fn pin(cpu: usize) -> bool {
    #[cfg(target_os = "linux")]
    {
        let mut mask = [0usize; 16];
        if cpu >= mask.len() * usize::BITS as usize {
            return false;
        }
        mask[cpu / usize::BITS as usize] |= 1usize << (cpu % usize::BITS as usize);
        // SAFETY: kernel receives the exact size of the initialized mask.
        return unsafe { sched_setaffinity(0, std::mem::size_of_val(&mask), mask.as_ptr()) } == 0;
    }
    #[cfg(not(target_os = "linux"))]
    {
        let _ = cpu;
        false
    }
}

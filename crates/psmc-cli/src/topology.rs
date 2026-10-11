//! Optional Linux affinity policy, restricted to the process's allowed CPUs.
//! Hybrid PMU CPU lists take precedence over a tolerant frequency heuristic.
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
// Parse Linux cpulist syntax. Bound expansion to the affinity-mask capacity.
fn cpu_list(text: &str) -> Option<std::collections::BTreeSet<usize>> {
    let mut result = std::collections::BTreeSet::new();
    for item in text.trim().split(',') {
        let (first, last) = item.split_once('-').unwrap_or((item, item));
        let first = first.parse::<usize>().ok()?;
        let last = last.parse::<usize>().ok()?;
        if first > last || last >= 16 * usize::BITS as usize {
            return None;
        }
        result.extend(first..=last);
    }
    Some(result)
}

fn classify(
    mut allowed: Vec<(usize, Option<usize>, bool)>,
    core: Option<&str>,
    atom: Option<&str>,
) -> Vec<Cpu> {
    let hybrid = core.and_then(cpu_list).zip(atom.and_then(cpu_list));
    let hybrid = hybrid.filter(|(core, atom)| {
        core.is_disjoint(atom)
            && allowed
                .iter()
                .all(|(id, _, _)| core.contains(id) || atom.contains(id))
    });
    let maximum = allowed.iter().filter_map(|x| x.1).max().unwrap_or(0);
    if hybrid.is_none() && (maximum == 0 || allowed.iter().any(|x| x.1.is_none())) {
        return Vec::new(); // Unknown topology: ordinary unpinned fit workers.
    }
    let fast = |id: usize, freq: Option<usize>| match &hybrid {
        // An affinity mask restricted entirely to Atom CPUs must still own fits.
        Some((core, _)) => core.contains(&id),
        None => (freq.unwrap() as u128) * 100 >= (maximum as u128) * 85,
    };
    allowed.sort_by_key(|&(id, freq, primary)| {
        (!fast(id, freq), !primary, std::cmp::Reverse(freq), id)
    });
    allowed
        .into_iter()
        .map(|(id, freq, _)| Cpu {
            id,
            fast: fast(id, freq),
        })
        .collect()
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
            cpus.push((id, frequency, id == primary));
        }
        let core = std::fs::read_to_string("/sys/devices/cpu_core/cpus").ok();
        let atom = std::fs::read_to_string("/sys/devices/cpu_atom/cpus").ok();
        return classify(cpus, core.as_deref(), atom.as_deref());
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

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn hybrid_type_overrides_frequency_and_respects_allowed_cpus() {
        let cpus = classify(
            vec![(2, None, true), (7, Some(6000), true)],
            Some("0-5"),
            Some("6-9"),
        );
        assert_eq!(
            cpus.iter().map(|c| (c.id, c.fast)).collect::<Vec<_>>(),
            [(2, true), (7, false)]
        );
        let only_atom = classify(vec![(7, None, true)], Some("0-5"), Some("6-9"));
        assert_eq!(only_atom.len(), 1);
        assert!(!only_atom[0].fast); // batch's zero-fast-worker fallback owns fits
    }
    #[test]
    fn preferred_core_boost_does_not_starve_fit_owners() {
        let cpus = classify(
            vec![
                (0, Some(5500), true),
                (1, Some(5000), true),
                (2, Some(4675), true),
                (3, Some(4674), true),
            ],
            None,
            None,
        );
        assert_eq!(
            cpus.iter().map(|c| c.fast).collect::<Vec<_>>(),
            [true, true, true, false]
        );
    }
    #[test]
    fn malformed_or_incomplete_topology_falls_back_safely() {
        for text in ["", "3-1", "0-999999999", "a", "0-1-2"] {
            assert!(cpu_list(text).is_none());
        }
        assert_eq!(cpu_list("0-2,7\n").unwrap().len(), 4);
        for (core, atom) in [("0", "1"), ("0,2", "2")] {
            let cpus = classify(vec![(2, Some(5000), true)], Some(core), Some(atom));
            assert!(cpus[0].fast);
        }
        assert!(classify(vec![(0, None, true)], None, None).is_empty());
    }
}

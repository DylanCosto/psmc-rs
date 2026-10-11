//! Conservative single-fit admission. Idle TLS workspaces remain resident, so
//! reserve largest-record slots for the entire fit, not only active queue jobs.
use std::{fs, path::Path};
const MIB: usize = 1024 * 1024;

#[derive(Clone, Debug)]
pub struct Admission {
    pub budget: usize,
    pub requested: usize,
    pub workers: usize,
    pub estimated: usize,
    pub message_bytes: usize,
}

pub fn message_bytes(states: usize, length: usize) -> Option<usize> {
    length
        .checked_add(1)?
        .checked_mul(states.checked_mul(2)?.checked_add(1)?)?
        .checked_mul(8)
}

fn mem_available(text: &str) -> Option<usize> {
    text.lines().find_map(|line| {
        let mut fields = line.split_whitespace();
        if fields.next()? != "MemAvailable:" {
            return None;
        }
        let value = fields.next()?.parse::<usize>().ok()?;
        (fields.next()? == "kB").then_some(())?;
        value.checked_mul(1024)
    })
}

fn limit_remaining(limit: &str, used: &str) -> Option<usize> {
    let limit = limit.trim().parse::<u64>().ok()?;
    let used = used.trim().parse::<u64>().ok()?;
    usize::try_from(limit.saturating_sub(used)).ok()
}

pub fn default_budget() -> usize {
    let mut available = fs::read_to_string("/proc/meminfo")
        .ok()
        .and_then(|s| mem_available(&s));
    // Respect finite cgroup limits, including ancestors. These are best-effort
    // detections; missing platform information uses a conservative 1 GiB budget.
    if let Ok(groups) = fs::read_to_string("/proc/self/cgroup") {
        for line in groups.lines() {
            let fields: Vec<_> = line.splitn(3, ':').collect();
            if fields.len() != 3 {
                continue;
            }
            let (root, max, current) = if fields[1].is_empty() {
                ("/sys/fs/cgroup", "memory.max", "memory.current")
            } else if fields[1].split(',').any(|s| s == "memory") {
                (
                    "/sys/fs/cgroup/memory",
                    "memory.limit_in_bytes",
                    "memory.usage_in_bytes",
                )
            } else {
                continue;
            };
            let relative = Path::new(fields[2].trim_start_matches('/'));
            if relative
                .components()
                .any(|c| !matches!(c, std::path::Component::Normal(_)))
            {
                continue;
            }
            let root = Path::new(root);
            let start = root.join(relative);
            for path in start.ancestors().take_while(|p| p.starts_with(root)) {
                if let (Ok(limit), Ok(used)) = (
                    fs::read_to_string(path.join(max)),
                    fs::read_to_string(path.join(current)),
                ) {
                    if let Some(headroom) = limit_remaining(&limit, &used) {
                        available = Some(available.map_or(headroom, |a| a.min(headroom)));
                    }
                }
            }
        }
    }
    available.map_or(1024 * MIB, |a| a / 2)
}

pub fn admit(
    states: usize,
    lengths: &[usize],
    input_bytes: usize,
    requested: usize,
    budget: usize,
    decoding: bool,
) -> Result<Admission, String> {
    let estimate = || -> Option<(usize, usize)> {
        let longest = lengths.iter().copied().max().unwrap_or(0);
        let messages = message_bytes(states, longest)?;
        let total = lengths.iter().try_fold(0usize, |a, &b| a.checked_add(b))?;
        // Loaded input, all queued observation copies (cache off included),
        // retained count results/cache/aggregate, model layouts, metadata and
        // allocator/thread overhead. Do not assume duplicates reduce memory.
        let counts = states
            .checked_mul(states)?
            .checked_add(states.checked_mul(4)?)?
            .checked_mul(8)?;
        let fixed = input_bytes
            .checked_add(total)?
            .checked_add(
                counts
                    .checked_mul(lengths.len().checked_add(1)?)?
                    .checked_mul(4)?,
            )?
            .checked_add(states.checked_mul(states)?.checked_mul(128)?)?
            .checked_add(lengths.len().checked_mul(1024)?)?
            .checked_add(if decoding {
                longest
                    .checked_add(1)?
                    .checked_mul(std::mem::size_of::<usize>())?
            } else {
                0
            })?
            .checked_add(32 * MIB)?;
        Some((messages, fixed))
    };
    let (messages, fixed) = estimate().ok_or("single-fit memory estimate overflow")?;
    let maximum = requested.max(1).min(lengths.len().max(1));
    for workers in (1..=maximum).rev() {
        // With sharing, the fit's serial workspace may remain allocated after
        // startup/bypass, in addition to one TLS workspace per numerical worker.
        // Decoding holds another dense history while those buffers still exist.
        let slots = workers + usize::from(workers > 1) + usize::from(decoding);
        let per_worker = states
            .checked_mul(states)
            .and_then(|n| n.checked_mul(128))
            .and_then(|n| n.checked_add(2 * MIB))
            .ok_or("single-fit memory estimate overflow")?;
        let estimated = messages
            .checked_mul(slots)
            .and_then(|n| n.checked_add(workers.checked_mul(per_worker)?))
            .and_then(|n| n.checked_add(fixed))
            .ok_or("single-fit memory estimate overflow")?;
        if estimated <= budget {
            return Ok(Admission {
                budget,
                requested,
                workers,
                estimated,
                message_bytes: messages,
            });
        }
    }
    Err(format!(
        "single-fit memory budget {budget} bytes cannot admit one record (largest message history {messages} bytes plus input, counts and overhead); increase --memory-mib or use equivalent mode"
    ))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn retained_buffers_fit_even_when_idle_or_decoding() {
        let lengths = vec![1_000_000; 8];
        let a = admit(64, &lengths, 8_000_000, 16, 2500 * MIB, false).unwrap();
        assert_eq!(a.workers, 1);
        let a = admit(64, &lengths, 8_000_000, 16, 3500 * MIB, false).unwrap();
        assert_eq!(a.workers, 2); // two TLS histories plus the owner
        assert!(a.estimated <= a.budget);
        let d = admit(64, &lengths, 8_000_000, 16, 3500 * MIB, true).unwrap();
        assert_eq!(d.workers, 1);
        let uneven = admit(64, &[10, 1_000_000, 100], 1_000_110, 16, 3500 * MIB, false).unwrap();
        assert_eq!(uneven.workers, 2); // no assumption about which worker gets the large record
    }
    #[test]
    fn too_small_and_overflow_are_errors() {
        let genome = admit(64, &[2_500_000; 16], 40_000_000, 16, 9 * 1024 * MIB, false).unwrap();
        assert_eq!(genome.workers, 2);
        assert!(genome.estimated < 9 * 1024 * MIB);
        assert!(admit(64, &[1_000_000], 1_000_000, 1, 512 * MIB, false).is_err());
        assert!(message_bytes(64, usize::MAX).is_none());
        assert!(admit(usize::MAX, &[100], 100, 16, usize::MAX, false).is_err());
        assert!(admit(64, &[usize::MAX], 1, 1, usize::MAX, false).is_err());
    }
    #[test]
    fn availability_and_container_headroom() {
        assert_eq!(
            mem_available("MemTotal: 9000 kB\nMemAvailable: 2000 kB\n"),
            Some(2048000)
        );
        assert_eq!(mem_available("MemAvailable: 2000 bytes"), None);
        assert_eq!(limit_remaining("1000", "250"), Some(750));
        assert_eq!(limit_remaining("1000", "2000"), Some(0));
        assert_eq!(limit_remaining("max", "250"), None);
    }
}

//! A single bounded queue of independent bootstrap fits. No nested numerical
//! pools: each worker reduces each fit's records in original occurrence order.
use crate::{Options, default_seed, fit, snapshot::string, write_trace};
use psmc_core::{Sequence, em::NoObserver, rng::LegacyRng};
use psmc_io::{read_sequences, resample_indices};
use std::{
    fs::{self, File, OpenOptions},
    io::BufWriter,
    path::PathBuf,
    sync::{
        Mutex,
        atomic::{AtomicUsize, Ordering},
    },
};

#[derive(Clone)]
pub struct BatchOptions {
    replicates: usize,
    workers: usize,
    memory_mib: usize,
    output_dir: Option<String>,
    reverse: bool,
}
impl Default for BatchOptions {
    fn default() -> Self {
        Self {
            replicates: 30,
            workers: std::thread::available_parallelism().map_or(1, usize::from),
            memory_mib: 2048,
            output_dir: None,
            reverse: false,
        }
    }
}
impl BatchOptions {
    pub fn set(&mut self, flag: &str, value: &str) -> Result<(), String> {
        fn positive(value: &str, flag: &str) -> Result<usize, String> {
            let n = value
                .parse::<usize>()
                .map_err(|_| format!("{flag} requires a positive integer"))?;
            if n == 0 {
                return Err(format!("{flag} requires a positive integer"));
            }
            Ok(n)
        }
        match flag {
            "--replicates" => self.replicates = positive(value, flag)?,
            "--workers" => self.workers = positive(value, flag)?,
            "--memory-mib" => self.memory_mib = positive(value, flag)?,
            "--output-dir" => self.output_dir = Some(value.into()),
            "--task-order" => {
                self.reverse = match value {
                    "forward" => false,
                    "reverse" => true,
                    _ => return Err("--task-order must be forward or reverse".into()),
                }
            }
            _ => return Err(format!("unknown bootstrap option: {flag}")),
        }
        Ok(())
    }
}

/// Conservative admission estimate, not an OS-enforced RSS limit. It includes
/// message capacity growth, count caches, model/optimizer scratch, and overhead.
fn estimated_worker_bytes(
    states: usize,
    max_length: usize,
    records: usize,
    maximum_draws: usize,
) -> Option<usize> {
    let messages = max_length
        .checked_add(1)?
        .checked_mul(states.checked_mul(2)?.checked_add(1)?)?
        .checked_mul(8)?;
    let counts = states
        .checked_mul(states)?
        .checked_add(states.checked_mul(4)?)?
        .checked_mul(8)?;
    let cached = counts.checked_mul(records)?;
    let sampled = maximum_draws.checked_mul(
        3 * std::mem::size_of::<usize>() + 2 * std::mem::size_of::<psmc_io::BootstrapDraw>(),
    )?;
    messages
        .checked_mul(2)?
        .checked_add(cached.checked_mul(4)?)?
        .checked_add(states.checked_mul(states)?.checked_mul(16 * 8)?)?
        .checked_add(sampled)?
        .checked_add(16 * 1024 * 1024)
}

fn fingerprint(sequences: &[Sequence]) -> String {
    // Stable noncryptographic identity for encoded input, clearly labeled.
    // Published benchmark provenance additionally uses SHA-256 of source files.
    let mut hash = 0xcbf29ce484222325_u64;
    for sequence in sequences {
        for value in (sequence.name.len() as u64)
            .to_le_bytes()
            .iter()
            .chain(sequence.name.as_bytes())
            .chain((sequence.observations.len() as u64).to_le_bytes().iter())
            .chain(&sequence.observations)
        {
            hash = (hash ^ u64::from(*value)).wrapping_mul(0x100000001b3);
        }
    }
    format!("{hash:016x}")
}

struct JobReport {
    index: usize,
    seed: i64,
    indices: Vec<usize>,
    length: usize,
    nonfinite: bool,
}

fn job(
    options: &Options,
    sequences: &[Sequence],
    directory: &std::path::Path,
    index: usize,
    seed: i64,
) -> Result<JobReport, Box<dyn std::error::Error>> {
    let mut rng = LegacyRng::new(seed);
    let (indices, draws) = resample_indices(sequences, &mut rng)?;
    let ordered: Vec<_> = indices.iter().map(|&i| &sequences[i]).collect();
    let open = |suffix: &str| {
        OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(directory.join(format!("replicate-{index:02}.{suffix}")))
    };
    write_trace(open("draws.jsonl")?, sequences, &indices, &draws)?;
    let mut output = BufWriter::new(open("psmc")?);
    let report = fit(options, &ordered, &mut rng, &mut output, &mut NoObserver)?;
    use std::io::Write;
    let mut stats = open("stats.json")?;
    stats.write_all(report.json(options, seed).as_bytes())?;
    stats.flush()?;
    Ok(JobReport {
        index,
        seed,
        length: ordered.iter().map(|s| s.observations.len()).sum(),
        indices,
        nonfinite: report.nonfinite_output,
    })
}

pub fn run(options: Options) -> Result<(), Box<dyn std::error::Error>> {
    let config = options.batch.as_ref().expect("batch configuration");
    if options.bootstrap
        || options.output.is_some()
        || options.snapshot.is_some()
        || options.stats.is_some()
    {
        return Err("bootstrap command manages separate per-replicate outputs/statistics; -b, -o, --snapshot and --stats are unavailable here".into());
    }
    if options.input == "-" {
        return Err("bootstrap command requires a named input file".into());
    }
    if std::env::var("PSMC_BOOTSTRAP_TRACE").is_ok_and(|v| !v.is_empty()) {
        return Err(
            "bootstrap command writes per-replicate traces; unset PSMC_BOOTSTRAP_TRACE".into(),
        );
    }
    let directory = PathBuf::from(
        config
            .output_dir
            .as_ref()
            .ok_or("bootstrap requires --output-dir")?,
    );
    // Check before reading/allocating; create_dir below also prevents races with
    // an existing directory/symlink without replacing any user content.
    if fs::symlink_metadata(&directory).is_ok() {
        return Err("bootstrap output directory must not already exist".into());
    }
    let budget = config
        .memory_mib
        .checked_mul(1024 * 1024)
        .ok_or("memory budget overflow")?;
    let seed = options.seed.unwrap_or_else(default_seed);
    let last_index =
        i64::try_from(config.replicates - 1).map_err(|_| "replicate count exceeds seed range")?;
    seed.checked_add(last_index)
        .ok_or("bootstrap seed range overflow")?;
    let sequences = read_sequences(&options.input)?;
    if options.settings.initial_params.is_none()
        && sequences.iter().all(|s| s.effective_length() == 0)
    {
        return Err("all-missing input requires explicit valid initial parameters (-i)".into());
    }
    let input_bytes = sequences
        .iter()
        .try_fold(0_usize, |total, s| {
            total
                .checked_add(s.observations.capacity())?
                .checked_add(s.name.capacity())?
                .checked_add(std::mem::size_of::<Sequence>())
        })
        .ok_or("input size overflow")?;
    let max_length = sequences
        .iter()
        .map(|s| s.observations.len())
        .max()
        .unwrap_or(0);
    let total_length = sequences
        .iter()
        .try_fold(0_usize, |sum, s| sum.checked_add(s.observations.len()))
        .ok_or("bootstrap total length overflow")?;
    if total_length > i32::MAX as usize {
        return Err(
            "bootstrap total raw length exceeds the legacy signed-int stopping-rule range".into(),
        );
    }
    let min_length = sequences
        .iter()
        .map(|s| s.observations.len())
        .min()
        .ok_or("empty bootstrap source")?;
    let maximum_draws = total_length
        .div_ceil(min_length)
        .checked_add(1)
        .ok_or("bootstrap draw bound overflow")?;
    let estimate = estimated_worker_bytes(
        options.settings.pattern.states(),
        max_length,
        sequences.len(),
        maximum_draws,
    )
    .ok_or("worker memory estimate overflow")?;
    // Completed indices and JSON construction are retained for deterministic
    // manifest order, so reserve their worst-case metadata separately as well.
    let result_bytes = maximum_draws
        .checked_mul(128)
        .and_then(|n| n.checked_add(4096))
        .and_then(|n| n.checked_mul(config.replicates))
        .ok_or("result metadata estimate overflow")?;
    let source_metadata_bytes = sequences
        .iter()
        .try_fold(0_usize, |sum, s| {
            sum.checked_add(s.name.len().checked_mul(12)?)?
                .checked_add(256)
        })
        .ok_or("source metadata estimate overflow")?;
    let metadata_bytes = result_bytes
        .checked_add(source_metadata_bytes)
        .ok_or("metadata estimate overflow")?;
    let resident_bytes = input_bytes
        .checked_add(metadata_bytes)
        .ok_or("resident memory estimate overflow")?;
    let available = std::thread::available_parallelism().map_or(1, usize::from);
    let by_memory = budget.saturating_sub(resident_bytes) / estimate;
    let device_worker_bytes = if options.backend == "cuda" {
        crate::cuda_worker_bytes(&options)?
    } else {
        0
    };
    let by_device_memory = if device_worker_bytes == 0 {
        usize::MAX
    } else {
        options.cuda_memory_mib * 1024 * 1024 / device_worker_bytes
    };
    let workers = config
        .workers
        .min(config.replicates)
        .min(available)
        .min(by_memory)
        .min(by_device_memory);
    if workers == 0 {
        return Err(format!("memory budget cannot admit one worker: input/metadata {resident_bytes} bytes plus estimated worker {estimate} bytes; increase --memory-mib").into());
    }
    let mut results = Vec::new();
    results
        .try_reserve_exact(config.replicates)
        .map_err(|_| "too many bootstrap replicates to allocate")?;
    results.resize_with(config.replicates, || None);
    fs::create_dir(&directory)?;
    let results = Mutex::new(results);
    let next = AtomicUsize::new(0);
    std::thread::scope(|scope| {
        for _ in 0..workers {
            scope.spawn(|| {
                loop {
                    let position = next.fetch_add(1, Ordering::Relaxed);
                    if position >= config.replicates {
                        break;
                    }
                    let index = if config.reverse {
                        config.replicates - 1 - position
                    } else {
                        position
                    };
                    let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                        job(&options, &sequences, &directory, index, seed + index as i64)
                            .map_err(|e| e.to_string())
                    }))
                    .unwrap_or_else(|_| Err("fit worker panicked; partial output retained".into()));
                    results.lock().expect("result lock")[index] = Some(result);
                }
            });
        }
    });
    let results = results
        .into_inner()
        .map_err(|_| "bootstrap result lock poisoned")?;
    let mut items = Vec::new();
    let mut failed = 0;
    let mut nonfinite = 0;
    for (index, result) in results.into_iter().enumerate() {
        match result.ok_or("bootstrap worker did not return a result")? {
            Ok(report) => {
                nonfinite += usize::from(report.nonfinite);
                let indices = report
                    .indices
                    .iter()
                    .map(|v| v.to_string())
                    .collect::<Vec<_>>()
                    .join(",");
                items.push(format!("{{\"index\":{},\"seed\":{},\"source_indices\":[{}],\"length\":{},\"output\":\"replicate-{index:02}.psmc\",\"stats\":\"replicate-{index:02}.stats.json\",\"draws\":\"replicate-{index:02}.draws.jsonl\",\"nonfinite_output\":{}}}",report.index,report.seed,indices,report.length,report.nonfinite));
            }
            Err(error) => {
                failed += 1;
                items.push(format!(
                    "{{\"index\":{index},\"seed\":{},\"error\":{}}}",
                    seed + index as i64,
                    string(&error)
                ));
            }
        }
    }
    let records = sequences
        .iter()
        .enumerate()
        .map(|(i, s)| {
            format!(
                "{{\"index\":{i},\"name\":{},\"length\":{}}}",
                string(&s.name),
                s.observations.len()
            )
        })
        .collect::<Vec<_>>()
        .join(",");
    let manifest = format!(
        "{{\"mode\":{},\"version\":1,\"cuda_buffer_budget_mib\":{},\"cuda_worker_buffer_bytes\":{device_worker_bytes},\"backend\":{},\"seed\":{seed},\"input\":{},\"input_fingerprint_fnv1a64\":{},\"requested_workers\":{},\"workers\":{workers},\"memory_mib\":{},\"input_bytes\":{input_bytes},\"estimated_metadata_bytes\":{metadata_bytes},\"estimated_worker_bytes\":{estimate},\"memory_policy\":\"conservative admission estimate, not an OS RSS hard limit; input loading precedes admission\",\"task_order\":{},\"iterations\":{},\"states\":{},\"source_records\":[{records}],\"replicates\":[{}],\"failed_replicates\":{failed},\"nonfinite_replicates\":{nonfinite}}}\n",
        string(&options.mode),
        options.cuda_memory_mib,
        string(&options.backend),
        string(&options.input),
        string(&fingerprint(&sequences)),
        config.workers,
        config.memory_mib,
        string(if config.reverse { "reverse" } else { "forward" }),
        options.iterations,
        options.settings.pattern.states(),
        items.join(",")
    );
    use std::io::Write;
    let mut file = File::create(directory.join("manifest.json"))?;
    file.write_all(manifest.as_bytes())?;
    file.flush()?;
    if failed > 0 {
        return Err(format!(
            "{failed} bootstrap fits failed; manifest and partial outputs retained in {}",
            directory.display()
        )
        .into());
    }
    eprintln!(
        "completed {} bootstrap fits using {workers} workers; {nonfinite} contain nonfinite legacy output",
        config.replicates
    );
    Ok(())
}

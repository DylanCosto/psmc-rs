mod batch;
mod format;
mod legacy;
mod memory;
mod snapshot;
mod topology;

use psmc_core::{
    Settings,
    em::{BackendStats, DenseBackend, ExpectationBackend, FitState, NoObserver, Observer},
    rng::LegacyRng,
};
use psmc_io::{parse_pattern, read_parameter_file, read_sequences, resample_indices};
use std::{
    env,
    fs::File,
    io::{self, BufWriter, Write},
    path::{Path, PathBuf},
    time::{SystemTime, UNIX_EPOCH},
};

const HELP: &str = concat!(
    "psmc-rs ",
    env!("CARGO_PKG_VERSION"),
    " — double-precision PSMC\n\nUsage: psmc-rs [options] input.psmcfa[.gz]\n       psmc-rs bootstrap [options] --output-dir DIRECTORY blocks.psmcfa\n\nLegacy options: -p PATTERN -N ITERATIONS -t MAX_TIME -r THETA_RHO\n  -l GRID_ALPHA -I RANDOM_AMPLITUDE -i PARAMETERS -o OUTPUT\n  -b bootstrap records; -d segments; -D full posterior; -s scales\n  -T divergence; -C decoding transition cap\nNew options: --backend cpu|dense|cuda --mode strict|equivalent --seed INTEGER\n  --snapshot FILE --stats FILE --cache on|off --simd auto|off|avx --help --version\nCUDA: --cuda-tile-sites COUNT (16384) --cuda-memory-mib MIB (1024)\nSingle fit: --record-workers COUNT (available CPUs); independent records only.\n  Strict single fit: --memory-mib MIB (half available memory; limits record workers).\nBootstrap runner: --scheduler fit|shared (shared) --replicates COUNT --workers COUNT --memory-mib MIB\n  --task-order forward|reverse; output directory must be new.\n\nCPU (default) reuses buffers and repeated-record counts; dense is the scalar oracle.\nInput '-' reads stdin for a single fit. CUDA counts are experimental and require a cuda-feature build.\n-c and -S are unsupported; -S is not the seed flag.\n"
);

#[derive(Clone)]
struct Options {
    settings: Settings,
    iterations: usize,
    input: String,
    output: Option<String>,
    parameters: Option<String>,
    bootstrap: bool,
    decode: bool,
    full: bool,
    probability: bool,
    cap: i64,
    seed: Option<i64>,
    snapshot: Option<String>,
    stats: Option<String>,
    backend: String,
    mode: String,
    cache: bool,
    cuda_tile_sites: usize,
    cuda_memory_mib: usize,
    simd: psmc_cpu::SimdMode,
    batch: Option<batch::BatchOptions>,
    record_pool: Option<std::sync::Arc<psmc_cpu::record_pool::RecordPool>>,
    record_workers: usize,
    memory_mib: Option<usize>,
    admission: Option<memory::Admission>,
}

fn number(value: &str, flag: &str) -> Result<f64, String> {
    let number = value
        .parse::<f64>()
        .map_err(|_| format!("{flag}: invalid number '{value}'"))?;
    if !number.is_finite() {
        return Err(format!("{flag}: finite value required"));
    }
    Ok(number)
}

fn parse() -> Result<Option<Options>, String> {
    let mut args: Vec<String> = env::args().skip(1).collect();
    let batch = if args.first().is_some_and(|arg| arg == "bootstrap") {
        args.remove(0);
        Some(batch::BatchOptions::default())
    } else {
        None
    };
    if args.is_empty() {
        return Err(HELP.into());
    }
    let mut options = Options {
        settings: Settings {
            pattern: parse_pattern("4+5*3+4")?,
            max_t: 15.0,
            alpha: 0.1,
            tr_ratio: 4.0,
            ran_init: 0.0,
            divergence: None,
            initial_params: None,
            explicit_times: None,
        },
        iterations: 30,
        input: String::new(),
        output: None,
        parameters: None,
        bootstrap: false,
        decode: false,
        full: false,
        probability: false,
        cap: -1,
        seed: None,
        snapshot: None,
        stats: None,
        backend: "cpu".into(),
        mode: "strict".into(),
        cache: true,
        cuda_tile_sites: 16384,
        cuda_memory_mib: 1024,
        simd: psmc_cpu::SimdMode::Auto,
        batch,
        record_pool: None,
        record_workers: 1,
        memory_mib: None,
        admission: None,
    };
    let mut record_workers_explicit = false;
    let mut i = 0;
    let mut positional = false;
    while i < args.len() {
        let arg = &args[i];
        if !positional && arg == "--" {
            positional = true;
            i += 1;
            continue;
        }
        if !positional && arg.starts_with("--") {
            let (flag, inline) = arg
                .split_once('=')
                .map_or((arg.as_str(), None), |(f, v)| (f, Some(v.to_owned())));
            if flag == "--help" {
                print!("{HELP}");
                return Ok(None);
            }
            if flag == "--version" {
                println!(
                    "psmc-rs {}; strict f64 dense/cpu Rust; legacy reference 82fa2ada83ee463fe1251b562ae3d60e82d7ad6a",
                    env!("CARGO_PKG_VERSION")
                );
                return Ok(None);
            }
            if !matches!(
                flag,
                "--seed"
                    | "--snapshot"
                    | "--mode"
                    | "--backend"
                    | "--stats"
                    | "--cache"
                    | "--cuda-tile-sites"
                    | "--cuda-memory-mib"
                    | "--simd"
                    | "--record-workers"
                    | "--scheduler"
                    | "--workers"
                    | "--replicates"
                    | "--output-dir"
                    | "--memory-mib"
                    | "--task-order"
            ) {
                return Err(format!("unsupported option: {flag}"));
            }
            let value = if let Some(v) = inline {
                v
            } else {
                i += 1;
                args.get(i)
                    .ok_or_else(|| format!("missing value for {flag}"))?
                    .clone()
            };
            match flag {
                "--seed" => {
                    options.seed = Some(
                        value
                            .parse()
                            .map_err(|_| "--seed requires a signed64-bit integer")?,
                    )
                }
                "--record-workers" => {
                    record_workers_explicit = true;
                    options.record_workers = value
                        .parse()
                        .map_err(|_| "--record-workers requires a positive integer")?;
                    if options.record_workers == 0 {
                        return Err("--record-workers requires a positive integer".into());
                    }
                }
                "--scheduler" => options
                    .batch
                    .as_mut()
                    .ok_or("--scheduler requires bootstrap")?
                    .set(flag, &value)?,
                "--snapshot" => options.snapshot = Some(value),
                "--stats" => options.stats = Some(value),
                "--backend" => {
                    if !matches!(value.as_str(), "dense" | "cpu" | "cuda") {
                        return Err(format!(
                            "unsupported backend '{value}'; choose dense, cpu or cuda"
                        ));
                    }
                    options.backend = value;
                }
                "--cuda-memory-mib" => {
                    options.cuda_memory_mib =
                        value.parse().map_err(|_| "invalid CUDA memory budget")?;
                    if options.cuda_memory_mib == 0
                        || options.cuda_memory_mib.checked_mul(1024 * 1024).is_none()
                    {
                        return Err(
                            "--cuda-memory-mib requires a positive, representable budget".into(),
                        );
                    }
                }
                "--cuda-tile-sites" => {
                    options.cuda_tile_sites =
                        value.parse().map_err(|_| "invalid CUDA tile sites")?;
                    if !(1..=1_048_576).contains(&options.cuda_tile_sites) {
                        return Err("--cuda-tile-sites must be 1..1048576".into());
                    }
                }
                "--simd" => options.simd = psmc_cpu::SimdMode::parse(&value)?,
                "--cache" => {
                    options.cache = match value.as_str() {
                        "on" => true,
                        "off" => false,
                        _ => return Err("--cache must be on or off".into()),
                    };
                }
                "--memory-mib" if options.batch.is_none() => {
                    let mib = value
                        .parse::<usize>()
                        .map_err(|_| "--memory-mib requires a positive integer")?;
                    if mib == 0 || mib.checked_mul(1024 * 1024).is_none() {
                        return Err(
                            "--memory-mib requires a positive nonoverflowing integer".into()
                        );
                    }
                    options.memory_mib = Some(mib);
                }
                "--workers" | "--replicates" | "--output-dir" | "--memory-mib" | "--task-order" => {
                    let batch = options.batch.as_mut().ok_or_else(|| {
                        format!("{flag} is only available in the bootstrap command")
                    })?;
                    batch.set(flag, &value)?;
                }
                "--mode" => {
                    if !matches!(value.as_str(), "strict" | "equivalent") {
                        return Err(format!(
                            "unsupported mode '{value}'; choose strict or equivalent"
                        ));
                    }
                    options.mode = value;
                }
                _ => {}
            }
        } else if !positional && arg.starts_with('-') && arg != "-" {
            let mut offset = 1;
            while offset < arg.len() {
                let flag = arg.as_bytes()[offset] as char;
                offset += 1;
                match flag {
                    'b' => options.bootstrap = true,
                    'd' => options.decode = true,
                    'D' => {
                        options.decode = true;
                        options.full = true;
                    }
                    's' => options.probability = true,
                    'c' | 'S' => {
                        return Err(format!(
                            "-{flag} is explicitly unsupported in Phase1; use the retained original PSMC executable"
                        ));
                    }
                    'p' | 'N' | 't' | 'r' | 'l' | 'I' | 'i' | 'o' | 'T' | 'C' => {
                        let value = if offset < arg.len() {
                            let v = arg[offset..].to_owned();
                            offset = arg.len();
                            v
                        } else {
                            i += 1;
                            args.get(i)
                                .ok_or_else(|| format!("missing value for -{flag}"))?
                                .clone()
                        };
                        match flag {
                            'p' => options.settings.pattern = parse_pattern(&value)?,
                            'N' => {
                                let n = value
                                    .parse::<i64>()
                                    .map_err(|_| "-N requires a nonnegative integer")?;
                                if n < 0 {
                                    return Err("-N must be nonnegative; negative legacy values can loop indefinitely".into());
                                }
                                options.iterations = n as usize;
                            }
                            't' => options.settings.max_t = number(&value, "-t")?,
                            'r' => options.settings.tr_ratio = number(&value, "-r")?,
                            'l' => options.settings.alpha = number(&value, "-l")?,
                            'I' => options.settings.ran_init = number(&value, "-I")?,
                            'i' => options.parameters = Some(value),
                            'o' => options.output = Some(value),
                            'T' => {
                                let t = number(&value, "-T")?;
                                if t >= 0.0 || options.settings.divergence.is_some() {
                                    options.settings.divergence = Some(t);
                                }
                            }
                            'C' => {
                                options.cap = value.parse().map_err(|_| "-C requires an integer")?
                            }
                            _ => unreachable!(),
                        }
                    }
                    _ => return Err(format!("unsupported option: -{flag}")),
                }
            }
        } else {
            if !options.input.is_empty() {
                return Err("exactly one input file is supported".into());
            }
            options.input = arg.clone();
        }
        i += 1;
    }
    if options.input.is_empty() {
        return Err("missing input file".into());
    }
    if let Some(path) = &options.parameters {
        read_parameter_file(path, &mut options.settings)?;
    }
    if options.settings.alpha <= 0.0 || options.settings.tr_ratio <= 0.0 {
        return Err("positive grid alpha and theta/rho are required".into());
    }
    if options.settings.explicit_times.is_none()
        && (options.settings.max_t <= 0.0 || options.settings.max_t >= 1000.0)
    {
        return Err("maximum time must be in (0,1000) without an explicit grid".into());
    }
    if options.seed.is_none() {
        if let Ok(value) = env::var("PSMC_SEED") {
            options.seed = Some(value.parse().map_err(|_| "invalid PSMC_SEED integer")?);
        }
    }
    if options.snapshot.is_none() {
        options.snapshot = env::var("PSMC_SNAPSHOT").ok().filter(|v| !v.is_empty());
    }
    if !record_workers_explicit
        && options.batch.is_none()
        && options.backend == "cpu"
        && options.snapshot.is_none()
    {
        options.record_workers = std::thread::available_parallelism().map_or(1, usize::from);
    }
    if options.record_workers > 1
        && (options.batch.is_some() || options.backend != "cpu" || options.snapshot.is_some())
    {
        return Err("--record-workers requires a single CPU fit without snapshots; bootstrap uses its shared worker budget".into());
    }
    if options.memory_mib.is_some() && (options.backend != "cpu" || options.mode != "strict") {
        return Err("single-fit --memory-mib requires --backend cpu --mode strict; bootstrap has its own memory budget".into());
    }
    if options.mode == "equivalent" {
        if options.backend != "cpu" {
            return Err("--mode equivalent requires --backend cpu".into());
        }
        if options.snapshot.is_some() {
            return Err("--snapshot is not supported in experimental equivalent mode".into());
        }
    }
    if options.backend == "cpu" || options.backend == "cuda" {
        options.simd.validate()?;
    } else if options.simd == psmc_cpu::SimdMode::Avx {
        return Err("--simd avx requires --backend cpu or cuda".into());
    }
    if options.backend == "cuda" {
        #[cfg(not(feature = "cuda"))]
        return Err("CUDA backend requires a build with --features cuda".into());
        #[cfg(feature = "cuda")]
        {
            let n = options.settings.pattern.states();
            if n > 1024 {
                return Err("CUDA supports at most 1024 states".into());
            }
            if cuda_worker_bytes(&options)? > options.cuda_memory_mib * 1024 * 1024 {
                return Err("CUDA buffer budget cannot admit one worker; reduce --cuda-tile-sites or increase --cuda-memory-mib".into());
            }
        }
    }
    Ok(Some(options))
}

// Exact upper bound for explicitly allocated device buffers per independent fit.
// Driver context/module overhead and other applications are outside this budget.
fn cuda_worker_bytes(options: &Options) -> Result<usize, String> {
    let n = options.settings.pattern.states();
    n.checked_mul(options.cuda_tile_sites)
        .and_then(|x| x.checked_mul(16))
        .and_then(|x| x.checked_add(options.cuda_tile_sites))
        .and_then(|x| {
            n.checked_mul(n)
                .and_then(|s| s.checked_mul(32))
                .and_then(|s| x.checked_add(s))
        })
        .ok_or_else(|| "CUDA buffer estimate overflow".into())
}

fn same_file(a: &str, b: &str) -> bool {
    if a == b {
        return true;
    }
    // Canonical paths resolve symlinks; inode identity also protects hardlinks.
    #[cfg(unix)]
    if let (Ok(a), Ok(b)) = (std::fs::metadata(a), std::fs::metadata(b)) {
        use std::os::unix::fs::MetadataExt;
        if a.dev() == b.dev() && a.ino() == b.ino() {
            return true;
        }
    }
    fn resolved(path: &str) -> Option<PathBuf> {
        let path = Path::new(path);
        path.canonicalize().ok().or_else(|| {
            let parent = path
                .parent()
                .filter(|p| !p.as_os_str().is_empty())
                .unwrap_or_else(|| Path::new("."));
            Some(parent.canonicalize().ok()?.join(path.file_name()?))
        })
    }
    match (resolved(a), resolved(b)) {
        (Some(a), Some(b)) => a == b,
        _ => false,
    }
}

fn nonfinite_state(state: &FitState) -> bool {
    let m = &state.model;
    [state.lk, state.q0, state.q1, m.c_pi, m.c_sigma]
        .iter()
        .any(|v| !v.is_finite())
        || [
            &m.params,
            &m.t,
            &m.sigma,
            &m.initial,
            &m.transition,
            &m.emission,
            &state.post_sigma,
        ]
        .iter()
        .any(|values| values.iter().any(|v| !v.is_finite()))
}

fn run(mut options: Options) -> Result<(), Box<dyn std::error::Error>> {
    if options.batch.is_some() {
        return batch::run(options);
    }
    let trace_path = options
        .bootstrap
        .then(|| env::var("PSMC_BOOTSTRAP_TRACE").ok())
        .flatten()
        .filter(|p| !p.is_empty());
    let input_path = if options.input == "-" {
        "/proc/self/fd/0"
    } else {
        &options.input
    };
    check_destinations(
        input_path,
        options.parameters.as_deref(),
        &[
            Some(options.output.as_deref().unwrap_or("/proc/self/fd/1")),
            options.snapshot.as_deref(),
            options.stats.as_deref(),
            trace_path.as_deref(),
        ],
    )?;
    let sequences = read_sequences(&options.input)?;
    let seed = options.seed.unwrap_or_else(default_seed);
    let mut rng = LegacyRng::new(seed);
    let (indices, draws) = if options.bootstrap {
        resample_indices(&sequences, &mut rng)?
    } else {
        ((0..sequences.len()).collect(), Vec::new())
    };
    let ordered: Vec<_> = indices.iter().map(|&i| &sequences[i]).collect();
    // Validate the selected records before opening any output, including the
    // trace. A mixed source can resample only missing blocks.
    if ordered.iter().all(|s| s.effective_length() == 0)
        && options.settings.initial_params.is_none()
    {
        return Err("all-missing input requires explicit valid initial parameters (-i)".into());
    }
    if options.backend == "cpu" && options.mode == "strict" {
        let input_bytes = sequences
            .iter()
            .try_fold(0usize, |sum, s| {
                sum.checked_add(s.observations.capacity())?
                    .checked_add(s.name.capacity())?
                    .checked_add(std::mem::size_of::<psmc_core::Sequence>())
            })
            .ok_or("input memory estimate overflow")?;
        let budget = options
            .memory_mib
            .map_or_else(memory::default_budget, |m| m * 1024 * 1024);
        let requested = options
            .record_workers
            .min(std::thread::available_parallelism().map_or(1, usize::from));
        let admission = memory::admit(
            options.settings.pattern.states(),
            &ordered
                .iter()
                .map(|s| s.observations.len())
                .collect::<Vec<_>>(),
            input_bytes,
            requested,
            budget,
            options.decode || options.probability,
        )?;
        eprintln!(
            "strict memory admission: {} of {} record workers, estimated {} MiB within {} MiB budget (not an RSS hard limit)",
            admission.workers,
            admission.requested,
            admission.estimated.div_ceil(1024 * 1024),
            admission.budget / (1024 * 1024)
        );
        options.record_workers = admission.workers;
        options.admission = Some(admission);
    }
    if let Some(path) = &trace_path {
        write_trace(File::create(path)?, &sequences, &indices, &draws)?;
    }
    let mut output: Box<dyn Write> = if let Some(path) = &options.output {
        Box::new(BufWriter::new(File::create(path)?))
    } else {
        Box::new(BufWriter::new(io::stdout()))
    };
    let mut observer: Box<dyn Observer> = if let Some(path) = &options.snapshot {
        Box::new(snapshot::Snapshot::new(Box::new(BufWriter::new(
            File::create(path)?,
        ))))
    } else {
        Box::new(NoObserver)
    };
    let report = fit(&options, &ordered, &mut rng, &mut output, observer.as_mut())?;
    if let Some(path) = &options.stats {
        std::fs::write(path, report.json(&options, seed))?;
    }
    Ok(())
}

fn default_seed() -> i64 {
    (SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
        ^ std::process::id() as u64) as i64
}

fn check_destinations(
    input: &str,
    parameters: Option<&str>,
    destinations: &[Option<&str>],
) -> Result<(), Box<dyn std::error::Error>> {
    let destinations: Vec<_> = destinations.iter().flatten().copied().collect();
    for (index, &output) in destinations.iter().enumerate() {
        if std::fs::symlink_metadata(output).is_ok_and(|m| m.file_type().is_symlink())
            && std::fs::metadata(output).is_err()
        {
            return Err("refusing an output path that is a dangling symlink".into());
        }
        if same_file(output, input) || parameters.is_some_and(|p| same_file(output, p)) {
            return Err("refusing to overwrite an input file".into());
        }
        if destinations[..index]
            .iter()
            .any(|previous| same_file(output, previous))
        {
            return Err(
                "legacy output, snapshot, statistics and bootstrap trace must use separate files"
                    .into(),
            );
        }
    }
    Ok(())
}

fn write_trace(
    file: File,
    sequences: &[psmc_core::Sequence],
    indices: &[usize],
    draws: &[psmc_io::BootstrapDraw],
) -> io::Result<()> {
    let mut trace = BufWriter::new(file);
    for (i, d) in draws.iter().enumerate() {
        writeln!(
            trace,
            "{{\"event\":\"bootstrap_draw\",\"draw\":{i},\"source_index\":{},\"length\":{},\"accepted\":{},\"before_length\":{},\"after_length\":{},\"target_length\":{},\"stop\":{}}}",
            d.source_index,
            d.length,
            d.accepted,
            d.before_length,
            d.after_length,
            d.target_length,
            d.stop
        )?;
    }
    writeln!(
        trace,
        "{{\"event\":\"bootstrap_end\",\"accepted_sequences\":{},\"length\":{},\"target_length\":{}}}",
        indices.len(),
        indices
            .iter()
            .map(|&i| sequences[i].observations.len())
            .sum::<usize>(),
        sequences
            .iter()
            .map(|s| s.observations.len())
            .sum::<usize>()
    )?;
    trace.flush()
}

struct FitReport {
    counters: BackendStats,
    expectation_seconds: f64,
    mstep_seconds: f64,
    nonfinite_output: bool,
    simd_kernel: &'static str,
}
impl FitReport {
    fn json(&self, options: &Options, seed: i64) -> String {
        let c = &self.counters;
        let admission = options.admission.as_ref().map_or_else(|| "null".into(), |a| {
            format!("{{\"budget_bytes\":{},\"requested_workers\":{},\"workers\":{},\"estimated_bytes\":{},\"largest_message_bytes\":{}}}",
                a.budget, a.requested, a.workers, a.estimated, a.message_bytes)
        });
        format!(
            "{{\"memory_admission\":{admission},\"mode\":{},\"structured_fallbacks\":{},\"backend\":{},\"cuda_tile_sites\":{},\"cuda_memory_mib\":{},\"cuda_launches\":{},\"cuda_upload_bytes\":{},\"cuda_download_bytes\":{},\"cuda_count_seconds\":{},\"cuda_fallbacks\":0,\"seed\":{seed},\"sequence_visits\":{},\"sequence_evaluations\":{},\"cache_hits\":{},\"snapshot_cache_bypass\":{},\"model_updates\":{},\"profile_enabled\":{},\"expectation_seconds\":{},\"mstep_seconds\":{},\"nonfinite_output\":{},\"iterations\":{},\"cache_enabled\":{},\"simd_requested\":{},\"simd_selected\":{}}}\n",
            snapshot::string(&options.mode),
            c.structured_fallbacks,
            snapshot::string(&options.backend),
            options.cuda_tile_sites,
            options.cuda_memory_mib,
            c.cuda_launches,
            c.cuda_upload_bytes,
            c.cuda_download_bytes,
            c.cuda_count_seconds,
            c.sequence_visits,
            c.sequence_evaluations,
            c.cache_hits,
            c.snapshot_cache_bypass,
            c.model_updates,
            options.stats.is_some(),
            self.expectation_seconds,
            self.mstep_seconds,
            self.nonfinite_output,
            options.iterations,
            options.cache,
            snapshot::string(options.simd.name()),
            snapshot::string(self.simd_kernel)
        )
    }
}

fn fit(
    options: &Options,
    sequences: &[&psmc_core::Sequence],
    rng: &mut LegacyRng,
    output: &mut dyn Write,
    observer: &mut dyn Observer,
) -> Result<FitReport, Box<dyn std::error::Error>> {
    if options.record_pool.is_none() && options.record_workers > 1 {
        let pool = std::sync::Arc::new(psmc_cpu::record_pool::RecordPool::default());
        let mut nested = options.clone();
        nested.record_pool = Some(pool.clone());
        let workers = options
            .record_workers
            .min(std::thread::available_parallelism().map_or(1, usize::from));
        return std::thread::scope(|scope| {
            struct Stop(std::sync::Arc<psmc_cpu::record_pool::RecordPool>);
            impl Drop for Stop {
                fn drop(&mut self) {
                    self.0.stop();
                }
            }
            let _stop = Stop(pool.clone());
            for _ in 1..workers {
                let pool = pool.clone();
                scope.spawn(move || pool.help_until_stopped());
            }
            fit(&nested, sequences, rng, output, observer)
        });
    }
    let effective_length = sequences.iter().map(|s| s.effective_length()).sum();
    if effective_length == 0 && options.settings.initial_params.is_none() {
        return Err("all-missing input requires explicit valid initial parameters (-i)".into());
    }
    let simd_kernel;
    let mut backend: Box<dyn ExpectationBackend> = if options.mode == "equivalent" {
        let mut engine = psmc_cpu::EquivalentBackend::with_simd(&options.settings, options.simd)?;
        simd_kernel = engine.simd_kernel();
        engine.profile = options.stats.is_some();
        engine.cache_enabled = options.cache;
        engine.record_pool = options.record_pool.clone();
        Box::new(engine)
    } else if options.backend == "cpu" {
        let mut engine =
            psmc_cpu::CpuBackend::with_simd(options.settings.pattern.states(), options.simd)?;
        simd_kernel = engine.simd_kernel();
        engine.profile = options.stats.is_some();
        engine.cache_enabled = options.cache;
        engine.record_pool = options.record_pool.clone();
        Box::new(engine)
    } else if options.backend == "cuda" {
        #[cfg(feature = "cuda")]
        {
            let mut engine = psmc_cuda::CudaBackend::new(
                options.settings.pattern.states(),
                options.simd,
                options.cuda_tile_sites,
            )?;
            simd_kernel = engine.simd_kernel();
            engine.profile = options.stats.is_some();
            engine.cache_enabled = options.cache;
            Box::new(engine)
        }
        #[cfg(not(feature = "cuda"))]
        {
            return Err("CUDA backend requires a build with --features cuda; CPU builds require no CUDA installation".into());
        }
    } else {
        simd_kernel = "scalar-dense";
        Box::new(DenseBackend {
            profile: options.stats.is_some(),
            ..DenseBackend::default()
        })
    };
    legacy::header(
        output,
        &options.settings,
        options.iterations,
        options.decode,
        sequences,
        &options.mode,
    )?;
    let mut state = FitState::new_ordered(&options.settings, sequences, rng);
    observer.model(0, &options.settings, &state.model)?;
    let mut nonfinite_output = legacy::round(
        output,
        &options.settings,
        &state,
        effective_length,
        0,
        &options.mode,
    )?;
    let mut warned = nonfinite_state(&state) || nonfinite_output;
    if warned {
        eprintln!(
            "warning: nonfinite legacy calculation at round 0; output retained for reference comparison"
        );
    }
    for round in 1..=options.iterations {
        let evaluations = state.iteration_with_backend(
            &options.settings,
            sequences,
            round,
            observer,
            backend.as_mut(),
        )?;
        writeln!(output, "IT\t{evaluations}")?;
        nonfinite_output |= legacy::round(
            output,
            &options.settings,
            &state,
            effective_length,
            round,
            &options.mode,
        )?;
        if !warned && (nonfinite_state(&state) || nonfinite_output) {
            eprintln!(
                "warning: nonfinite legacy calculation at round {round}; output retained for reference comparison"
            );
            warned = true;
        }
    }
    if options.decode || options.probability {
        if options.cap > 0 {
            if options.cap as usize >= state.model.n - 1 {
                eprintln!(
                    "ERROR: -C must be smaller than {}; option disabled",
                    state.model.n - 1
                );
            } else {
                state.model.cap_transition(options.cap as usize);
            }
        }
        legacy::decode(
            output,
            &options.settings,
            &state,
            sequences,
            options.full,
            options.probability,
        )?;
    }
    observer.finish()?;
    output.flush()?;
    Ok(FitReport {
        counters: backend.stats(),
        expectation_seconds: state.expectation_seconds,
        mstep_seconds: state.mstep_seconds,
        nonfinite_output,
        simd_kernel,
    })
}

fn main() {
    let result = parse()
        .map_err(|e| -> Box<dyn std::error::Error> { e.into() })
        .and_then(|options| {
            if let Some(options) = options {
                run(options)
            } else {
                Ok(())
            }
        });
    if let Err(error) = result {
        eprintln!("psmc-rs: {error}");
        std::process::exit(2);
    }
}

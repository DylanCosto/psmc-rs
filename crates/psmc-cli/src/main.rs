mod batch;
mod format;
mod legacy;
mod snapshot;

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

const HELP: &str = "psmc-rs 0.3.2 — strict double-precision PSMC\n\nUsage: psmc-rs [options] input.psmcfa[.gz]\n       psmc-rs bootstrap [options] --output-dir DIRECTORY blocks.psmcfa\n\nLegacy options: -p PATTERN -N ITERATIONS -t MAX_TIME -r THETA_RHO\n  -l GRID_ALPHA -I RANDOM_AMPLITUDE -i PARAMETERS -o OUTPUT\n  -b bootstrap records; -d segments; -D full posterior; -s scales\n  -T divergence; -C decoding transition cap\nNew options: --backend dense|cpu --mode strict --seed INTEGER\n  --snapshot FILE --stats FILE --cache on|off --simd auto|off|avx --help --version\nBootstrap runner: --replicates COUNT --workers COUNT --memory-mib MIB\n  --task-order forward|reverse; output directory must be new.\n\nDense remains the scalar oracle. CPU reuses buffers and repeated-record counts.\nInput '-' reads stdin for a single fit. GPU/equivalent/research are unavailable.\n-c and -S are unsupported; -S is not the seed flag.\n";

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
    cache: bool,
    simd: psmc_cpu::SimdMode,
    batch: Option<batch::BatchOptions>,
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
        backend: "dense".into(),
        cache: true,
        simd: psmc_cpu::SimdMode::Auto,
        batch,
    };
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
                    "psmc-rs 0.3.2; strict f64 dense/cpu Rust; legacy reference 82fa2ada83ee463fe1251b562ae3d60e82d7ad6a"
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
                    | "--simd"
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
                "--snapshot" => options.snapshot = Some(value),
                "--stats" => options.stats = Some(value),
                "--backend" => {
                    if !matches!(value.as_str(), "dense" | "cpu") {
                        return Err(format!(
                            "unsupported backend '{value}'; choose dense or cpu"
                        ));
                    }
                    options.backend = value;
                }
                "--simd" => options.simd = psmc_cpu::SimdMode::parse(&value)?,
                "--cache" => {
                    options.cache = match value.as_str() {
                        "on" => true,
                        "off" => false,
                        _ => return Err("--cache must be on or off".into()),
                    };
                }
                "--workers" | "--replicates" | "--output-dir" | "--memory-mib" | "--task-order" => {
                    let batch = options.batch.as_mut().ok_or_else(|| {
                        format!("{flag} is only available in the bootstrap command")
                    })?;
                    batch.set(flag, &value)?;
                }
                "--mode" if value != "strict" => {
                    return Err(format!(
                        "mode '{value}' is unavailable; only strict arithmetic is implemented"
                    ));
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
    if options.backend == "cpu" {
        options.simd.validate()?;
    } else if options.simd == psmc_cpu::SimdMode::Avx {
        return Err("--simd avx requires --backend cpu".into());
    }
    Ok(Some(options))
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

fn run(options: Options) -> Result<(), Box<dyn std::error::Error>> {
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
        format!(
            "{{\"backend\":{},\"seed\":{seed},\"sequence_visits\":{},\"sequence_evaluations\":{},\"cache_hits\":{},\"snapshot_cache_bypass\":{},\"model_updates\":{},\"profile_enabled\":{},\"expectation_seconds\":{},\"mstep_seconds\":{},\"nonfinite_output\":{},\"iterations\":{},\"cache_enabled\":{},\"simd_requested\":{},\"simd_selected\":{}}}\n",
            snapshot::string(&options.backend),
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
    let effective_length = sequences.iter().map(|s| s.effective_length()).sum();
    if effective_length == 0 && options.settings.initial_params.is_none() {
        return Err("all-missing input requires explicit valid initial parameters (-i)".into());
    }
    let simd_kernel;
    let mut backend: Box<dyn ExpectationBackend> = if options.backend == "cpu" {
        let mut engine =
            psmc_cpu::CpuBackend::with_simd(options.settings.pattern.states(), options.simd)?;
        simd_kernel = engine.simd_kernel();
        engine.profile = options.stats.is_some();
        engine.cache_enabled = options.cache;
        Box::new(engine)
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
    )?;
    let mut state = FitState::new_ordered(&options.settings, sequences, rng);
    observer.model(0, &options.settings, &state.model)?;
    let mut nonfinite_output =
        legacy::round(output, &options.settings, &state, effective_length, 0)?;
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
        nonfinite_output |=
            legacy::round(output, &options.settings, &state, effective_length, round)?;
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

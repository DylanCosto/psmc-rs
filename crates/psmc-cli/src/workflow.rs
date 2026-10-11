//! Workflow utilities; no changes to inference or legacy observation encoding.
use psmc_core::Sequence;
use std::{
    fs::OpenOptions,
    io::{BufWriter, Write},
    ops::Range,
};

type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;

const HELP: &str = "Workflow commands:\n  inspect INPUT.psmcfa[.gz]\n  split --block-bins COUNT --output NEW_FILE INPUT.psmcfa[.gz]\n  export --mutation-rate RATE --generation-years YEARS --bin-bp BP --output NEW.csv FIT.psmc\nInspection and splitting use the same observation encoding as fitting. Splitting\nnever crosses records and merges a final tail shorter than half a block, as splitfa.\nExport uses the last complete round, printed RS precision, and upstream PSMC scaling.\n";

pub fn run(args: &[String]) -> Result<()> {
    if args.iter().any(|a| a == "--help") {
        print!("{HELP}");
        return Ok(());
    }
    let mut input = None;
    let mut output = None;
    let mut block = None;
    let mut mutation = None;
    let mut years = None;
    let mut bp = None;
    let mut i = 1;
    let mut positional = false;
    while i < args.len() {
        let arg = &args[i];
        if !positional && arg == "--" {
            positional = true;
        } else if !positional && arg.starts_with('-') && arg != "-" {
            i += 1;
            let value = args.get(i).ok_or("missing option value")?;
            match (args[0].as_str(), arg.as_str()) {
                ("split" | "export", "--output") if output.is_none() => output = Some(value),
                ("split", "--block-bins") if block.is_none() => {
                    let n = value.parse::<usize>()?;
                    if n == 0 || n.checked_mul(3).is_none() {
                        return Err("invalid block size".into());
                    }
                    block = Some(n);
                }
                ("export", "--mutation-rate") if mutation.is_none() => {
                    mutation = Some(positive(value)?)
                }
                ("export", "--generation-years") if years.is_none() => {
                    years = Some(positive(value)?)
                }
                ("export", "--bin-bp") if bp.is_none() => bp = Some(positive(value)?),
                _ => return Err(format!("unsupported or repeated option: {arg}").into()),
            }
        } else if input.replace(arg).is_some() {
            return Err("exactly one input is required".into());
        }
        i += 1;
    }
    let input = input.ok_or(HELP)?;
    match args[0].as_str() {
        "inspect" => inspect(&psmc_io::read_sequences(input)?),
        "split" => {
            let sequences = psmc_io::read_sequences(input)?;
            let size = block.ok_or("split requires --block-bins (bins, not base pairs)")?;
            let mut out = create(output.ok_or("split requires --output")?)?;
            split(&sequences, size, &mut out)?;
            out.flush()?;
            Ok(())
        }
        "export" => {
            let text = std::fs::read_to_string(input)?;
            // Validate everything before creating a destination.
            let csv = export(
                &text,
                mutation.ok_or("export requires --mutation-rate")?,
                years.ok_or("export requires --generation-years")?,
                bp.ok_or("export requires --bin-bp")?,
            )?;
            let mut out = create(output.ok_or("export requires --output")?)?;
            out.write_all(csv.as_bytes())?;
            out.flush()?;
            Ok(())
        }
        _ => Err(HELP.into()),
    }
}

fn positive(text: &str) -> Result<f64> {
    let n: f64 = text.parse()?;
    if !n.is_finite() || n <= 0.0 {
        return Err("a finite positive value is required".into());
    }
    Ok(n)
}
fn finite(text: &str) -> Result<f64> {
    let n: f64 = text.parse()?;
    if !n.is_finite() {
        return Err("nonfinite curve value".into());
    }
    Ok(n)
}
fn create(path: &str) -> Result<BufWriter<std::fs::File>> {
    Ok(BufWriter::new(
        OpenOptions::new().write(true).create_new(true).open(path)?,
    ))
}
fn inspect(sequences: &[Sequence]) -> Result<()> {
    let mut counts = [0_u64; 3];
    for s in sequences {
        for &c in &s.observations {
            counts[c as usize] += 1;
        }
    }
    let mut names = std::collections::HashSet::new();
    let duplicates = sequences.iter().filter(|s| !names.insert(&s.name)).count();
    println!(
        "records\t{}\nbins\t{}\nhomozygous_bins\t{}\nheterozygous_bins\t{}\nmissing_bins\t{}\nlongest_record_bins\t{}\nduplicate_record_names\t{}",
        sequences.len(),
        counts.iter().sum::<u64>(),
        counts[0],
        counts[1],
        counts[2],
        sequences
            .iter()
            .map(|s| s.observations.len())
            .max()
            .unwrap_or(0),
        duplicates
    );
    if counts[0] + counts[1] == 0 {
        return Err("all bins are missing; a fit needs explicit initial parameters".into());
    }
    if counts[1] == 0 {
        eprintln!("warning: no heterozygous bins; population history may not be estimable");
    }
    Ok(())
}

/// Exact pinned splitfa integer tail rule. Each source record starts a new series.
fn blocks(length: usize, size: usize) -> Vec<Range<usize>> {
    let mut result = Vec::new();
    let mut begin = 0;
    while begin < length {
        let end = if length - begin < size * 3 / 2 {
            length
        } else {
            length.min(begin.saturating_add(size))
        };
        result.push(begin..end);
        begin = end;
    }
    result
}
fn split(sequences: &[Sequence], size: usize, out: &mut dyn Write) -> Result<()> {
    for s in sequences {
        for (i, range) in blocks(s.observations.len(), size).into_iter().enumerate() {
            writeln!(out, ">{}_{}", s.name, i + 1)?;
            for chunk in s.observations[range].chunks(60) {
                for &c in chunk {
                    out.write_all(&[b"TKN"[c as usize]])?;
                }
                writeln!(out)?;
            }
        }
    }
    Ok(())
}

#[derive(Default)]
struct Round {
    index: usize,
    theta: Option<f64>,
    dt: f64,
    rows: Vec<(f64, f64)>,
}
fn export(text: &str, mu: f64, years: f64, bp: f64) -> Result<String> {
    let mut skip = None;
    let mut source_version = "unspecified";
    let mut current: Option<Round> = None;
    let mut last = None;
    for line in text.lines() {
        if let Some(version) = line.strip_prefix("MM\tVersion:") {
            source_version = version.trim();
        }
        let words: Vec<_> = line.split_whitespace().collect();
        if words.first() == Some(&"MM") {
            for w in &words {
                if let Some(value) = w.strip_prefix("skip:") {
                    skip = Some(positive(value.trim_end_matches(','))?);
                }
            }
        }
        match words.first().copied() {
            Some("RD") if words.len() == 2 => {
                if current.is_some() {
                    return Err("unterminated round before next RD".into());
                }
                current = Some(Round {
                    index: words[1].parse()?,
                    ..Round::default()
                });
            }
            Some("TR") if current.is_some() => {
                let r = current.as_mut().unwrap();
                if words.len() != 3 || r.theta.is_some() {
                    return Err("invalid or duplicate TR".into());
                }
                r.theta = Some(positive(words[1])?);
                positive(words[2])?;
            }
            Some("DT") if current.is_some() => {
                if words.len() != 2 {
                    return Err("invalid DT".into());
                }
                current.as_mut().unwrap().dt = finite(words[1])?;
            }
            Some("RS") if current.is_some() => {
                let r = current.as_mut().unwrap();
                if words.len() < 4 || words[1].parse::<usize>()? != r.rows.len() {
                    return Err("invalid RS index".into());
                }
                let t = finite(words[2])?;
                if t < 0.0 || r.rows.last().is_some_and(|&(prev, _)| t < prev) {
                    return Err("RS times are not ordered".into());
                }
                r.rows.push((t, positive(words[3])?));
            }
            Some("//") if current.is_some() => {
                let r = current.take().unwrap();
                if r.theta.is_none() || r.rows.is_empty() {
                    return Err("complete round lacks TR/RS".into());
                }
                last = Some(r);
            }
            _ => {}
        }
    }
    if current.is_some() {
        eprintln!("warning: trailing incomplete round ignored during export");
    }
    let r = last.ok_or("no complete PSMC round")?;
    let n0 = r.theta.unwrap()
        / (skip.ok_or("missing MM skip; cannot infer bin scaling")? * bp * 4.0 * mu);
    let source_sha256 = crate::digest::reader(text.as_bytes())?;
    let mode = if source_version.starts_with("psmc-rs ") && source_version.contains("(strict f64;")
    {
        "strict"
    } else if source_version.starts_with("psmc-rs ") && source_version.contains("(equivalent f64;")
    {
        "equivalent"
    } else {
        "unspecified"
    };
    // Prefix makes this a text cell even if a foreign header starts with a
    // spreadsheet formula character; double quotes are escaped per CSV.
    let source_version = format!("\"Version: {}\"", source_version.replace('"', "\"\""));
    let mut out = String::from(
        "round,state,time_generations,time_years,ne,theta,mutation_rate,bin_bp,generation_years,mode,source_version,source_sha256\n",
    );
    for (i, &(t, lambda)) in r.rows.iter().enumerate() {
        let generations = 2.0 * n0 * (t + r.dt);
        let ne = n0 * lambda;
        if ![n0, generations, generations * years, ne]
            .iter()
            .all(|v| v.is_finite())
            || n0 <= 0.0
            || ne <= 0.0
            || generations < 0.0
        {
            return Err("invalid scaled curve (check units and DT)".into());
        }
        out.push_str(&format!("{},{i},{generations:.17e},{:.17e},{ne:.17e},{:.17e},{mu:.17e},{bp:.17e},{years:.17e},{mode},{source_version},{source_sha256}\n", r.index, generations * years, r.theta.unwrap()));
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn split_tail_boundaries_and_conservation() {
        assert_eq!(blocks(149, 100), vec![0..149]);
        assert_eq!(blocks(150, 100), vec![0..100, 100..150]);
        assert_eq!(blocks(249, 100), vec![0..100, 100..249]);
        for size in 1..20 {
            for length in 1..100 {
                assert_eq!(
                    blocks(length, size)
                        .into_iter()
                        .flatten()
                        .collect::<Vec<_>>(),
                    (0..length).collect::<Vec<_>>()
                );
            }
        }
    }
    #[test]
    fn export_scaling_complete_round_and_divergence() {
        let text = "MM\tskip:2,\nRD\t0\nTR\t0.008\t0.001\nDT\t0.1\nRS\t0\t0\t2\nRS\t1\t1\t3\n//\nRD\t1\nTR\t0.1\t0.1\n";
        let result = export(text, 1e-8, 25.0, 100.0).unwrap();
        let first: Vec<_> = result.lines().nth(1).unwrap().split(',').collect();
        assert!((first[2].parse::<f64>().unwrap() - 200.0).abs() < 1e-10);
        assert!((first[3].parse::<f64>().unwrap() - 5000.0).abs() < 1e-9);
        assert!((first[4].parse::<f64>().unwrap() - 2000.0).abs() < 1e-9);
        let provenance = export(
            &format!("MM\tVersion: psmc-rs 0.8.0 (equivalent f64; reference test)\n{text}"),
            1e-8,
            25.0,
            100.0,
        )
        .unwrap();
        assert!(provenance.contains(",equivalent,\"Version: psmc-rs 0.8.0"));
        assert!(export(&text.replace("0.008", "NaN"), 1e-8, 25.0, 100.0).is_err());
        assert!(export(&text.replace("skip:2,", "other"), 1e-8, 25.0, 100.0).is_err());
    }
}

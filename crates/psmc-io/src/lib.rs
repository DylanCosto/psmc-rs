//! Rust input and bootstrap translation of legacy PSMC cli.c/aux.c/kseq.h.
//!
//! The accepted sequence alphabet is ASCII. For successfully parsed records,
//! header boundaries, printable-byte filtering, aliases and FASTQ quality
//! handling follow the pinned kseq implementation. Empty/malformed records,
//! truncated qualities, non-ASCII bytes, and malformed patterns are rejected
//! rather than reproducing the reference's crashes or silent truncation.
//! Upstream source and MIT license notices are retained under reference/.

mod gzip;

use psmc_core::{Pattern, Sequence, Settings, rng::LegacyRng};

/// Parse a canonical positive-integer pattern such as `4+5*3+4`.
pub fn parse_pattern(text: &str) -> Result<Pattern, String> {
    if text.is_empty()
        || !text
            .bytes()
            .all(|c| c.is_ascii_digit() || c == b'+' || c == b'*')
    {
        return Err("pattern must contain positive integers separated by + or *".into());
    }
    let integer = |s: &str| -> Result<usize, String> {
        let n = s
            .parse::<usize>()
            .map_err(|_| format!("invalid pattern integer: {s:?}"))?;
        if n == 0 {
            return Err("pattern integers must be positive".into());
        }
        Ok(n)
    };
    let mut groups = Vec::new();
    let mut n_free = 0_usize;
    for term in text.split('+') {
        let mut factors = term.split('*');
        let first = integer(factors.next().unwrap_or_default())?;
        let (repeats, width) = match factors.next() {
            Some(value) => (first, integer(value)?),
            None => (1, first),
        };
        if factors.next().is_some() {
            return Err("each pattern term may contain at most one *".into());
        }
        let new_free = n_free
            .checked_add(repeats)
            .ok_or("pattern group count overflow")?;
        if new_free > 255 {
            return Err("legacy PSMC supports at most 255 parameter groups".into());
        }
        let added = repeats
            .checked_mul(width)
            .ok_or("pattern state count overflow")?;
        let states = groups
            .len()
            .checked_add(added)
            .ok_or("pattern state count overflow")?;
        if states > i32::MAX as usize {
            return Err("pattern state count exceeds the legacy signed-int limit".into());
        }
        groups
            .try_reserve(added)
            .map_err(|_| "pattern is too large to allocate".to_string())?;
        for group in n_free..new_free {
            groups.extend(std::iter::repeat_n(group, width));
        }
        n_free = new_free;
    }
    Ok(Pattern {
        text: text.to_owned(),
        groups,
        n_free,
    })
}

fn observation(byte: u8) -> u8 {
    match byte {
        b'0' | b'A' | b'a' | b'C' | b'c' | b'G' | b'g' | b'T' | b't' => 0,
        b'1' | b'K' | b'k' | b'M' | b'm' | b'R' | b'r' | b'S' | b's' | b'W' | b'w' | b'Y'
        | b'y' => 1,
        _ => 2,
    }
}

fn c_whitespace(byte: u8) -> bool {
    // Rust's is_ascii_whitespace excludes vertical tab, whereas C isspace in
    // the pinned C locale includes it. Header tokenization must use C's set.
    matches!(byte, b' ' | b'\t' | b'\n' | b'\r' | 11 | 12)
}

/// Read transparent plain/gzip input or `-` for stdin. zlib only supplies bytes;
/// record parsing, validation and observation encoding are performed in Rust.
pub fn read_sequences(path: &str) -> Result<Vec<Sequence>, String> {
    parse_sequences(&gzip::read(path)?)
}

fn parse_sequences(data: &[u8]) -> Result<Vec<Sequence>, String> {
    if !data.is_ascii() {
        return Err("sequence input must be ASCII (non-ASCII bytes are unsupported)".into());
    }
    let mut at = 0;
    let mut pending_header = false;
    let mut sequences = Vec::new();
    loop {
        if !pending_header {
            while at < data.len() && data[at] != b'>' && data[at] != b'@' {
                at += 1;
            }
            if at == data.len() {
                break;
            }
            at += 1;
        }
        // kseq's name ends at the first C-locale whitespace, not just a space.
        let begin = at;
        while at < data.len() && !c_whitespace(data[at]) {
            at += 1;
        }
        if begin == at {
            return Err(format!("record {} has an empty name", sequences.len() + 1));
        }
        // strdup in the original reader truncates a name at an embedded NUL.
        let name_end = data[begin..at]
            .iter()
            .position(|&c| c == 0)
            .map_or(at, |n| begin + n);
        if name_end == begin {
            return Err("record has an empty NUL-terminated name".into());
        }
        let name = String::from_utf8(data[begin..name_end].to_vec()).unwrap();
        let delimiter = data.get(at).copied();
        if at < data.len() {
            at += 1;
        }
        if delimiter != Some(b'\n') {
            while at < data.len() && data[at] != b'\n' {
                at += 1;
            }
            if at < data.len() {
                at += 1;
            }
        }
        let mut observations = Vec::new();
        while at < data.len() && !matches!(data[at], b'>' | b'@' | b'+') {
            let c = data[at];
            at += 1;
            if c.is_ascii_graphic() {
                observations.push(observation(c));
            }
        }
        if observations.is_empty() {
            return Err(format!("record {name:?} is empty"));
        }
        if observations.len() > i32::MAX as usize {
            return Err(format!(
                "record {name:?} exceeds the legacy signed-int length limit"
            ));
        }
        let end = data.get(at).copied();
        if at < data.len() {
            at += 1;
        }
        pending_header = matches!(end, Some(b'>' | b'@'));
        if end == Some(b'+') {
            // As in kseq, the '+' label is ignored regardless of header marker.
            while at < data.len() && data[at] != b'\n' {
                at += 1;
            }
            if at == data.len() {
                return Err(format!(
                    "record {name:?} has a truncated FASTQ quality header"
                ));
            }
            at += 1;
            let mut quality_length = 0;
            loop {
                // kseq consumes one extra character after the final quality.
                // On conventional FASTQ this is the line ending. Preserving it
                // also preserves the original parser on embedded delimiters.
                let Some(&c) = data.get(at) else {
                    break;
                };
                at += 1;
                if quality_length == observations.len() {
                    break;
                }
                if (33..=127).contains(&c) {
                    quality_length += 1;
                }
            }
            if quality_length != observations.len() {
                return Err(format!(
                    "record {name:?} has truncated FASTQ qualities ({quality_length} for {} observations)",
                    observations.len()
                ));
            }
        }
        sequences.push(Sequence { name, observations });
        if end.is_none() {
            break;
        }
    }
    if sequences.is_empty() {
        return Err("input contains no nonempty FASTA/FASTQ records".into());
    }
    Ok(sequences)
}

/// Load the raw `pattern theta rho max_t lambdas... [times...] [divergence]`
/// format consumed by `-i`; a report's `PA` prefix must already be removed.
///
/// With a negative max_t, exactly one time per state follows the parameters.
/// Explicit-grid plus divergence is rejected because the C reader reuses an
/// array index and can overwrite parameters or write beyond its allocation.
pub fn read_parameter_file(path: &str, settings: &mut Settings) -> Result<(), String> {
    let text = std::fs::read_to_string(path)
        .map_err(|e| format!("cannot read parameter file {path}: {e}"))?;
    parse_parameter_text(&text, settings)
}

fn parse_parameter_text(text: &str, settings: &mut Settings) -> Result<(), String> {
    if !text.is_ascii() {
        return Err("parameter file must be ASCII".into());
    }
    let mut fields = text
        .split(|c: char| c_whitespace(c as u8))
        .filter(|s| !s.is_empty());
    let pattern = parse_pattern(fields.next().ok_or("empty parameter file")?)?;
    let mut values = Vec::new();
    for field in fields {
        let value = field
            .parse::<f64>()
            .map_err(|_| format!("invalid parameter number: {field:?}"))?;
        if !value.is_finite() {
            return Err("parameter file numbers must be finite".into());
        }
        values.push(value);
    }
    let count = pattern.n_free + 3;
    if values.len() < count {
        return Err(format!(
            "parameter file needs {count} parameters after its pattern, found {}",
            values.len()
        ));
    }
    let mut parameters = values[..count].to_vec();
    let max_t = parameters[2];
    let explicit_times;
    let divergence;
    if max_t < 0.0 {
        let required = count + pattern.states();
        if values.len() != required {
            return Err(format!(
                "explicit-grid parameter file needs exactly {required} numbers; explicit-grid/divergence combinations are unsupported because the legacy reader uses an unsafe index"
            ));
        }
        if settings.divergence.is_some() {
            return Err("explicit-grid parameter files cannot be combined with -T (unsafe legacy divergence loading)".into());
        }
        explicit_times = Some(values[count..].to_vec());
        divergence = None;
    } else {
        if values.len() > count + 1 {
            return Err("ordinary parameter file has unexpected trailing values; positive max_t cannot mark an explicit grid".into());
        }
        divergence = values.get(count).copied();
        if settings.divergence.is_some() && divergence.is_none() {
            return Err("-T with a parameter file requires a final divergence value; the legacy reader otherwise uses uninitialized memory".into());
        }
        if let Some(dt) = divergence {
            parameters.push(dt);
        }
        explicit_times = None;
    }
    // Commit only after validating the whole file, so an error leaves settings
    // untouched rather than accidentally continuing with a partial parameter set.
    settings.max_t = max_t;
    settings.tr_ratio = parameters[0] / parameters[1];
    settings.pattern = pattern;
    settings.initial_params = Some(parameters);
    settings.explicit_times = explicit_times;
    settings.divergence = divergence;
    Ok(())
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct BootstrapDraw {
    pub source_index: usize,
    pub length: usize,
    pub accepted: bool,
    pub before_length: usize,
    pub after_length: usize,
    pub target_length: usize,
    pub stop: bool,
}

/// Preserve the original nearest-total-raw-length stopping rule and draw order.
/// Repeated records are cloned for this scalar oracle; each remains a separate
/// HMM sequence and contributes its own statistics and count initializers.
pub fn resample(
    sequences: &[Sequence],
    rng: &mut LegacyRng,
) -> Result<(Vec<Sequence>, Vec<BootstrapDraw>), String> {
    let (indices, draws) = resample_indices(sequences, rng)?;
    Ok((
        indices.into_iter().map(|i| sequences[i].clone()).collect(),
        draws,
    ))
}

/// Ordered block references; no observation data is copied. The existing
/// materializing API delegates here so both use exactly the same RNG draws.
pub fn resample_indices(
    sequences: &[Sequence],
    rng: &mut LegacyRng,
) -> Result<(Vec<usize>, Vec<BootstrapDraw>), String> {
    if sequences.is_empty() || sequences.iter().any(|s| s.observations.is_empty()) {
        return Err("bootstrap requires nonempty input records".into());
    }
    let target_length = sequences
        .iter()
        .try_fold(0_usize, |sum, s| sum.checked_add(s.observations.len()))
        .ok_or("bootstrap total length overflow")?;
    // aux.c narrows each remaining/excess length to signed int. Restrict this
    // literal port to the defined range instead of reproducing wrapped decisions.
    if target_length > i32::MAX as usize {
        return Err(
            "bootstrap total raw length exceeds the legacy signed-int stopping-rule range".into(),
        );
    }
    let mut sampled = Vec::new();
    let mut draws = Vec::new();
    let mut total = 0_usize;
    loop {
        let source_index = (sequences.len() as f64 * rng.next_f64()) as usize;
        let source = &sequences[source_index];
        let length = source.observations.len();
        let before_length = total;
        let tmp1 = target_length as i64 - total as i64;
        let tmp2 = total as i64 + length as i64 - target_length as i64;
        let accepted = tmp2 <= 0 || (tmp2 > 0 && tmp1 > 0 && tmp2 < tmp1);
        if accepted {
            sampled.push(source_index);
            total += length;
        }
        let stop = tmp1 >= 0 && tmp2 >= 0;
        draws.push(BootstrapDraw {
            source_index,
            length,
            accepted,
            before_length,
            after_length: total,
            target_length,
            stop,
        });
        if stop {
            break;
        }
    }
    Ok((sampled, draws))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn settings() -> Settings {
        Settings {
            pattern: parse_pattern("4+5*3+4").unwrap(),
            max_t: 15.0,
            alpha: 0.1,
            tr_ratio: 4.0,
            ran_init: 0.0,
            divergence: None,
            initial_params: None,
            explicit_times: None,
        }
    }

    #[test]
    fn pattern_group_mapping_and_legacy_limit() {
        let p = parse_pattern("2+2*3+1").unwrap();
        assert_eq!(p.groups, [0, 0, 1, 1, 1, 2, 2, 2, 3]);
        assert_eq!(p.n_free, 4);
        assert_eq!(parse_pattern("4+5*3+4").unwrap().states(), 23);
        assert_eq!(parse_pattern("4+25*2+4+6").unwrap().states(), 64);
        assert!(parse_pattern("255*1").is_ok());
        for bad in [
            "",
            "0",
            "2+",
            "2**3",
            "2*0",
            "256*1",
            "2 +3",
            "-1",
            "999999999999999999999999999999",
        ] {
            assert!(parse_pattern(bad).is_err(), "accepted {bad:?}");
        }
    }

    #[test]
    fn fasta_aliases_whitespace_names_and_boundaries() {
        let seq = parse_sequences(b">chr1 comment\r\nACGTacgt0\tKMRSWYkmrswy1 N.-?!\n>chr2\nKTT\n")
            .unwrap();
        assert_eq!(seq.len(), 2);
        assert_eq!(seq[0].name, "chr1");
        assert_eq!(
            seq[0].observations,
            [vec![0; 9], vec![1; 13], vec![2; 5]].concat()
        );
        assert_eq!(seq[1].observations, [1, 0, 0]);
        assert_eq!(seq[0].effective_length(), 22);
        assert_eq!(seq[0].heterozygous_count(), 13);
        assert_eq!(
            parse_sequences(b">name\x0bcomment\nTK").unwrap()[0].name,
            "name"
        );
        assert_eq!(
            parse_sequences(b">name\0trailer\nTK").unwrap()[0].name,
            "name"
        );
    }

    #[test]
    fn fastq_qualities_ignored_and_kseq_delimiters_preserved() {
        let seq =
            parse_sequences(b"preamble\n@one c\nTK\nN\n+ignored label\n!\n##\n@two\n0Y\n+\nAB\n")
                .unwrap();
        assert_eq!(seq.len(), 2);
        assert_eq!(seq[0].observations, [0, 1, 2]);
        assert_eq!(seq[1].observations, [0, 1]);
        let embedded = parse_sequences(b">one\nTK>two comment\nNK").unwrap();
        assert_eq!(embedded.len(), 2);
        assert_eq!(embedded[1].name, "two");
        // An '@' header without '+' is still FASTA in the pinned kseq reader.
        assert_eq!(
            parse_sequences(b"@one\nTK").unwrap()[0].observations,
            [0, 1]
        );
    }

    #[test]
    fn malformed_sequence_input_fails_explicitly() {
        for bad in [
            &b""[..],
            b"no header",
            b">one\n",
            b">one\n>two\nTK",
            b">\nTK",
            b"@one\nTK\n+\n!",
            b"@one\nTK\n+",
            b">one\nT\xff",
        ] {
            assert!(parse_sequences(bad).is_err(), "accepted {bad:?}");
        }
    }

    #[test]
    fn supplied_parameter_formats_and_atomic_errors() {
        let mut config = settings();
        parse_parameter_text("2+2 0.1 0.02 15 1.2 0.8", &mut config).unwrap();
        assert_eq!(config.pattern.groups, [0, 0, 1, 1]);
        assert_eq!(config.tr_ratio, 5.0);
        assert_eq!(
            config.initial_params.as_ref().unwrap(),
            &[0.1, 0.02, 15.0, 1.2, 0.8]
        );
        parse_parameter_text("2+2 0.1 0.02 -1 1.2 0.8 0 0.5 2 15", &mut config).unwrap();
        assert_eq!(config.explicit_times, Some(vec![0.0, 0.5, 2.0, 15.0]));
        assert_eq!(config.max_t, -1.0);
        assert!(
            parse_parameter_text("2+2 0.1 0.02 -1 1.2 0.8 0 0.5 2 15 0.3", &mut config).is_err()
        );
        assert_eq!(config.max_t, -1.0);
        parse_parameter_text("2+2 0.1 0.02 15 1.2 0.8 0.3", &mut config).unwrap();
        assert_eq!(config.divergence, Some(0.3));
        assert_eq!(config.initial_params.as_ref().unwrap().last(), Some(&0.3));
        assert!(parse_parameter_text("2+2 0.1 0.02 15 1.2 0.8", &mut config).is_err());
        for bad in [
            "",
            "PA 2+2 0.1 0.02 15 1 1",
            "2+2 0.1",
            "2+2 nan 0.02 15 1 1",
            "2+2 0.1 0.02 15 1 1 0 1",
        ] {
            assert!(
                parse_parameter_text(bad, &mut settings()).is_err(),
                "accepted {bad:?}"
            );
        }
        assert!(parse_parameter_text("2+2\x0b0.1 0.02 15 1 1", &mut settings()).is_ok());
    }

    #[test]
    fn system_zlib_plain_gzip_and_corruption() {
        let plain = b">one\nTKNN\n>two comment\n01T\n";
        // gzip-compressed `plain`, including a valid CRC and length trailer.
        let compressed = [
            31, 139, 8, 0, 0, 0, 0, 0, 2, 3, 179, 203, 207, 75, 229, 10, 241, 246, 243, 227, 178,
            43, 41, 207, 87, 72, 206, 207, 205, 77, 205, 43, 225, 50, 48, 12, 225, 2, 0, 152, 252,
            214, 67, 27, 0, 0, 0,
        ];
        let dir = std::env::temp_dir().join(format!("psmc-io-test-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("records");
        let path_text = path.to_str().unwrap();
        std::fs::write(&path, plain).unwrap();
        assert_eq!(
            read_sequences(path_text).unwrap()[1].observations,
            [0, 1, 0]
        );
        std::fs::write(&path, compressed).unwrap();
        let loaded = read_sequences(path_text).unwrap();
        assert_eq!(loaded.len(), 2);
        assert_eq!(loaded[0].observations, [0, 1, 2, 2]);
        std::fs::write(&path, &compressed[..compressed.len() - 5]).unwrap();
        assert!(read_sequences(path_text).is_err());
        let mut corrupt = compressed;
        corrupt[40] ^= 1;
        std::fs::write(&path, corrupt).unwrap();
        assert!(read_sequences(path_text).is_err());
        std::fs::remove_file(&path).unwrap();
        assert!(read_sequences(path_text).is_err());
        std::fs::remove_dir(&dir).unwrap();
    }

    #[test]
    fn rng_matches_pinned_libc_reference_draws() {
        // Values recorded from glibc srand48(1); every value has denominator 2^48.
        let mut rng = LegacyRng::new(1);
        let expected = [
            0.041630344771878214,
            0.45449244472862915,
            0.8348172181669149,
            0.33598603014520023,
            0.5654894035661364,
        ];
        for value in expected {
            assert_eq!(rng.next_f64(), value);
        }
    }

    #[test]
    fn bootstrap_nearest_total_and_duplicate_multiplicity() {
        let input = vec![
            Sequence {
                name: "short".into(),
                observations: vec![0, 1, 2],
            },
            Sequence {
                name: "long".into(),
                observations: vec![0, 1, 2, 0, 1, 2, 0],
            },
        ];
        let (sample, draws) = resample(&input, &mut LegacyRng::new(1)).unwrap();
        assert_eq!(
            draws.iter().map(|d| d.source_index).collect::<Vec<_>>(),
            [0, 0, 1]
        );
        assert_eq!(
            draws.iter().map(|d| d.accepted).collect::<Vec<_>>(),
            [true, true, true]
        );
        assert_eq!(
            sample.iter().map(|s| s.name.as_str()).collect::<Vec<_>>(),
            ["short", "short", "long"]
        );
        assert_eq!(
            sample.iter().map(Sequence::effective_length).sum::<usize>(),
            9
        );
        assert_eq!(
            sample
                .iter()
                .map(Sequence::heterozygous_count)
                .sum::<usize>(),
            4
        );
        assert_eq!(draws.last().unwrap().after_length, 13);
        assert!(draws.last().unwrap().stop);
        // A three-bin overshoot versus three-bin undershoot is rejected on ties.
        let ties = vec![
            Sequence {
                name: "a".into(),
                observations: vec![0; 3],
            },
            Sequence {
                name: "b".into(),
                observations: vec![1; 6],
            },
        ];
        let (sample, draws) = resample(&ties, &mut LegacyRng::new(1)).unwrap();
        assert_eq!(sample.len(), 2);
        assert!(!draws.last().unwrap().accepted);
        assert_eq!(draws.last().unwrap().after_length, 6);
        assert!(draws.last().unwrap().stop);
    }

    #[test]
    fn bootstrap_exact_length_stops_without_extra_draw() {
        let input = [Sequence {
            name: "a".into(),
            observations: vec![1, 0, 2],
        }];
        let (sample, draws) = resample(&input, &mut LegacyRng::new(1)).unwrap();
        assert_eq!(sample.len(), 1);
        assert_eq!(draws.len(), 1);
        assert!(draws[0].accepted && draws[0].stop);
        assert!(resample(&[], &mut LegacyRng::new(1)).is_err());
    }
}

//! Legacy report and posterior-decoding records, translated from cli.c/aux.c.
use crate::format::{f, float, g};
use psmc_core::{Sequence, Settings, em::FitState, hmm, math};
use std::io::{self, Write};

pub fn header(
    out: &mut dyn Write,
    settings: &Settings,
    iterations: usize,
    decode: bool,
    sequences: &[&Sequence],
    mode: &str,
) -> io::Result<()> {
    write!(
        out,
        "CC\nCC\tBrief Description of the file format:\nCC\t  CC  comments\nCC\t  MM  useful-messages\nCC\t  RD  round-of-iterations\nCC\t  LL  \\log[P(sequence)]\nCC\t  QD  Q-before-opt Q-after-opt\nCC\t  TR  \\theta_0 \\rho_0\nCC\t  RS  k t_k \\lambda_k \\pi_k \\sum_{{l\\not=k}}A_{{kl}} A_{{kk}}\nCC\t  DC  begin end best-k t_k+\\Delta_k max-prob\nCC\n"
    )?;
    writeln!(
        out,
        "MM\tVersion: psmc-rs {} ({mode} f64; reference 82fa2ada83ee)",
        env!("CARGO_PKG_VERSION")
    )?;
    writeln!(
        out,
        "MM\tpattern:{}, n:{}, n_free_lambdas:{}",
        settings.pattern.text,
        settings.pattern.states() - 1,
        settings.pattern.n_free
    )?;
    writeln!(
        out,
        "MM\tn_iterations:{iterations}, skip:1, max_t:{}, theta/rho:{}",
        g(settings.max_t),
        g(settings.tr_ratio)
    )?;
    writeln!(out, "MM\tis_decoding:{}", usize::from(decode))?;
    writeln!(
        out,
        "MM\tn_seqs:{}, sum_L:{}, sum_n:{}",
        sequences.len(),
        sequences
            .iter()
            .map(|s| s.effective_length())
            .sum::<usize>(),
        sequences
            .iter()
            .map(|s| s.heterozygous_count())
            .sum::<usize>()
    )?;
    out.flush()
}

pub fn round(
    out: &mut dyn Write,
    settings: &Settings,
    s: &FitState,
    effective_length: usize,
    round: usize,
) -> io::Result<bool> {
    let m = &s.model;
    let n_recomb = effective_length as f64 / m.c_sigma;
    writeln!(
        out,
        "RD\t{round}\nLK\t{}\nQD\t{} -> {}",
        f(s.lk),
        f(s.q0),
        f(s.q1)
    )?;
    let mut sum = 0.0;
    for k in 0..m.n {
        sum += m.sigma[k] * math::ln(m.sigma[k] / s.post_sigma[k]);
    }
    writeln!(out, "RI\t{}", float(sum, 10, false))?;
    let mut nonfinite = (!sum.is_finite() && !(round == 0 && sum == f64::INFINITY))
        || !s.lk.is_finite()
        || !s.q0.is_finite()
        || !s.q1.is_finite()
        || !n_recomb.is_finite()
        || !m.c_pi.is_finite()
        || m.params
            .iter()
            .chain(&m.t)
            .chain(&m.sigma)
            .chain(&s.post_sigma)
            .any(|v| !v.is_finite());
    writeln!(
        out,
        "TR\t{}\t{}\nMT\t{}",
        f(m.params[0]),
        f(m.params[1]),
        f(m.params[2])
    )?;
    if settings.divergence.is_some() {
        writeln!(out, "DT\t{}", f(m.params[m.params.len() - 1]))?;
    }
    writeln!(out, "MM\tC_pi: {}, n_recomb: {}", f(m.c_pi), f(n_recomb))?;
    for k in 0..m.n {
        nonfinite |= !(n_recomb * m.initial[k]).is_finite();
        writeln!(
            out,
            "RS\t{k}\t{}\t{}\t{}\t{}\t{}",
            f(m.t[k]),
            f(m.params[settings.pattern.groups[k] + 3]),
            f(n_recomb * m.initial[k]),
            f(m.sigma[k]),
            f(s.post_sigma[k])
        )?;
    }
    write!(out, "PA\t{}", settings.pattern.text)?;
    for &value in &m.params {
        write!(out, " {}", float(value, 9, false))?;
    }
    if let Some(times) = &settings.explicit_times {
        for &value in times {
            write!(out, " {}", float(value, 9, false))?;
        }
    }
    writeln!(out, "\n//")?;
    out.flush()?;
    Ok(nonfinite)
}

pub fn decode(
    out: &mut dyn Write,
    settings: &Settings,
    s: &FitState,
    sequences: &[&Sequence],
    full: bool,
    probability: bool,
) -> io::Result<()> {
    let m = &s.model;
    let theta = m.params[0];
    let times = m.avg_times(settings);
    for k in 0..m.n {
        writeln!(
            out,
            "TC\t{k}\t{}\t{}\t{}",
            f(m.t[k] * theta),
            f(times[k] * theta),
            f(m.t[k + 1] * theta)
        )?;
    }
    let ae = hmm::pre_backward(m);
    for seq in sequences {
        let messages = hmm::forward_backward(m, &seq.observations, &ae);
        let length = seq.observations.len();
        if probability {
            write!(out, "PR\t{}\t{length}", seq.name)?;
            for k in 1..=length {
                write!(out, "\t{}", float(messages.scales[k], 3, false))?;
            }
            writeln!(out)?;
        } else if full {
            for k in 1..=length {
                let mut prob = 0.0;
                if k < length {
                    let symbol = seq.observations[k] as usize;
                    for l in 0..m.n {
                        prob += messages.forward[k * m.n + l]
                            * m.transition[l * m.n + l]
                            * messages.backward[(k + 1) * m.n + l]
                            * m.emission[symbol * m.n + l];
                    }
                    prob = 1.0 - prob;
                }
                write!(out, "DF\t{k}\t{}", f(prob))?;
                for l in 0..m.n {
                    write!(
                        out,
                        "\t{}",
                        float(
                            messages.forward[k * m.n + l]
                                * messages.backward[k * m.n + l]
                                * messages.scales[k],
                            4,
                            false
                        )
                    )?;
                }
                writeln!(out)?;
            }
        } else {
            let mut path = vec![0_usize; length + 1];
            for u in 1..=length {
                let mut max = -1.0;
                let mut chosen = None;
                for k in 0..m.n {
                    let prob = messages.forward[u * m.n + k]
                        * messages.backward[u * m.n + k]
                        * messages.scales[u];
                    if max < prob {
                        max = prob;
                        chosen = Some(k);
                    }
                }
                path[u] = chosen.ok_or_else(|| {
                    io::Error::other("cannot decode nonfinite posterior; legacy C would assert")
                })?;
            }
            let mut start = 1;
            let mut prev = path[1];
            let mut max_prob =
                messages.forward[m.n + prev] * messages.backward[m.n + prev] * messages.scales[1];
            for k in 2..=length {
                if prev != path[k] {
                    writeln!(
                        out,
                        "DC\t{}\t{start}\t{}\t{prev}\t{}\t{}",
                        seq.name,
                        k - 1,
                        f(times[prev] * theta),
                        float(max_prob, 3, false)
                    )?;
                    prev = path[k];
                    start = k;
                    max_prob = 0.0;
                }
                let prob = messages.forward[k * m.n + path[k]]
                    * messages.backward[k * m.n + path[k]]
                    * messages.scales[k];
                if max_prob < prob {
                    max_prob = prob;
                }
            }
            writeln!(
                out,
                "DC\t{}\t{start}\t{length}\t{prev}\t{}\t{}",
                seq.name,
                float(times[prev] * theta, 3, false),
                float(max_prob, 2, false)
            )?;
        }
        out.flush()?;
    }
    Ok(())
}

//! Additive JSONL snapshots; names/layout align with the instrumented C oracle.
use psmc_core::{
    Sequence, Settings,
    em::{FitState, Observer},
    hmm::{Counts, Messages},
    model::Model,
};
use std::io::{self, Write};

fn num(value: f64) -> String {
    if value.is_nan() {
        "\"nan\"".into()
    } else if value == f64::INFINITY {
        "\"inf\"".into()
    } else if value == f64::NEG_INFINITY {
        "\"-inf\"".into()
    } else {
        format!("{value:.17e}")
    }
}
fn vector(values: &[f64]) -> String {
    format!(
        "[{}]",
        values.iter().map(|&v| num(v)).collect::<Vec<_>>().join(",")
    )
}
fn matrix(values: &[f64], columns: usize) -> String {
    format!(
        "[{}]",
        values
            .chunks(columns)
            .map(vector)
            .collect::<Vec<_>>()
            .join(",")
    )
}
fn ints<I: IntoIterator<Item = usize>>(values: I) -> String {
    format!(
        "[{}]",
        values
            .into_iter()
            .map(|v| v.to_string())
            .collect::<Vec<_>>()
            .join(",")
    )
}
pub(crate) fn string(value: &str) -> String {
    let mut out = String::from("\"");
    for c in value.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            c if c < ' ' => out.push_str(&format!("\\u{:04x}", c as u32)),
            c => out.push(c),
        }
    }
    out.push('"');
    out
}
fn counts(c: &Counts) -> String {
    format!(
        ",\"A0\":{},\"A\":{},\"E\":{},\"stored_Q0\":{}",
        vector(&c.a0),
        matrix(&c.a, c.n),
        matrix(&c.e, c.n),
        num(c.q0)
    )
}

pub struct Snapshot {
    output: Box<dyn Write>,
    model_id: usize,
}
impl Snapshot {
    pub fn new(output: Box<dyn Write>) -> Self {
        Self {
            output,
            model_id: 0,
        }
    }
}
impl Observer for Snapshot {
    fn finish(&mut self) -> io::Result<()> {
        self.output.flush()
    }
    fn model(&mut self, iteration: usize, settings: &Settings, m: &Model) -> io::Result<()> {
        self.model_id += 1;
        writeln!(
            self.output,
            "{{\"event\":\"model\",\"iteration\":{iteration},\"model_id\":{},\"states\":{},\"symbols\":2,\"params\":{},\"par_map\":{},\"t\":{},\"initial\":{},\"transition\":{},\"emission\":{},\"sigma\":{},\"C_pi\":{},\"C_sigma\":{}}}",
            self.model_id,
            m.n,
            vector(&m.params),
            ints(settings.pattern.groups.iter().copied()),
            vector(&m.t),
            vector(&m.initial),
            matrix(&m.transition, m.n),
            matrix(&m.emission, m.n),
            vector(&m.sigma),
            num(m.c_pi),
            num(m.c_sigma)
        )
    }
    fn sequence(
        &mut self,
        iteration: usize,
        index: usize,
        seq: &Sequence,
        m: &Messages,
        c: &Counts,
    ) -> io::Result<()> {
        writeln!(
            self.output,
            "{{\"event\":\"sequence\",\"iteration\":{iteration},\"model_id\":{},\"index\":{index},\"name\":{},\"length\":{},\"observations\":{},\"scales\":{},\"forward\":{},\"backward\":{},\"log_likelihood\":{}{}}}",
            self.model_id,
            string(&seq.name),
            m.length,
            ints(seq.observations.iter().map(|&x| x as usize)),
            vector(&m.scales),
            matrix(&m.forward, m.n),
            matrix(&m.backward, m.n),
            num(m.log_likelihood),
            counts(c)
        )
    }
    fn aggregate(&mut self, iteration: usize, c: &Counts, likelihood: f64) -> io::Result<()> {
        writeln!(
            self.output,
            "{{\"event\":\"aggregate\",\"iteration\":{iteration},\"model_id\":{},\"log_likelihood\":{}{}}}",
            self.model_id,
            num(likelihood),
            counts(c)
        )
    }
    fn objective(
        &mut self,
        iteration: usize,
        evaluation: usize,
        raw: &[f64],
        m: &Model,
        negative_q: f64,
    ) -> io::Result<()> {
        writeln!(
            self.output,
            "{{\"event\":\"objective\",\"iteration\":{iteration},\"model_id\":{},\"evaluation\":{evaluation},\"raw_params\":{},\"params\":{},\"negative_Q\":{}}}",
            self.model_id,
            vector(raw),
            vector(&m.params),
            num(negative_q)
        )
    }
    fn em_end(&mut self, iteration: usize, s: &FitState, evaluations: usize) -> io::Result<()> {
        writeln!(
            self.output,
            "{{\"event\":\"em_end\",\"iteration\":{iteration},\"model_id\":{},\"optimizer_evaluations\":{evaluations},\"params\":{},\"Q0\":{},\"Q1\":{},\"last_candidate_Q\":{},\"log_likelihood\":{},\"post_sigma\":{}}}",
            self.model_id,
            vector(&s.model.params),
            num(s.q0),
            num(s.q1),
            num(s.last_candidate_q),
            num(s.lk),
            vector(&s.post_sigma)
        )?;
        self.output.flush()
    }
}

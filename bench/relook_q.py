"""Revisit the prior K64 flat-Q gain with an explicit K64-only dispatch."""
from pathlib import Path
import relook_forward as harness
from common import sha256

def generate(scratch):
    code='''//! K64-only flat ordered Q; scalar libm and every original term retained.
use psmc_core::{hmm::Counts,model::Model,math::ln};
pub fn q(counts:&Counts,model:&Model)->f64 {
    if counts.n!=64 {return counts.q(model);}
    assert_eq!(counts.a0.len(),64); assert_eq!(counts.a.len(),4096); assert_eq!(counts.e.len(),192);
    assert_eq!(model.n,64); assert_eq!(model.initial.len(),64);
    assert_eq!(model.transition.len(),4096); assert_eq!(model.emission.len(),192);
    let mut sum=0.0;
    for (&count,&p) in counts.e[..128].iter().zip(&model.emission[..128]) {
        if p<=0.0 {return -1e300;} sum+=count*ln(p);
    }
    for (&count,&p) in counts.a.iter().zip(&model.transition) {
        if p<=0.0 {return -1e300;} sum+=count*ln(p);
    }
    sum-counts.q0
}
'''
    old=Path('bench/cpu_campaign_q.rs').read_text()
    tests=old[old.index('#[cfg(test)]'):old.index('    #[test]\n    fn replacement_collision')]+ '}\n'
    tests=tests.replace('            let mut cache = QCache::new(n);\n','').replace('cache.q(&counts, &model)','q(&counts, &model)')
    tests=tests.replace('exact_probability_reuse_preserves_q_and_invalid_order','k64_dispatch_preserves_q_and_invalid_order')
    (scratch/'crates/psmc-cpu/src/q_candidate.rs').write_text(code+tests)
    p=scratch/'crates/psmc-cpu/src/lib.rs';p.write_text(p.read_text()+'\nmod q_candidate;\n')
    p=scratch/'crates/psmc-cpu/src/engine.rs';s=p.read_text();needle='    fn stats(&self) -> BackendStats {';assert s.count(needle)==1
    p.write_text(s.replace(needle,'    fn q(&self, counts: &Counts, model: &Model) -> f64 { crate::q_candidate::q(counts,model) }\n'+needle))

if __name__=='__main__':
    harness.RAW=Path('work/relook/q');harness.REPORT='bench/relook-q.json';harness.generate=generate
    harness.EXTRA_METADATA=dict(generator_sha256=sha256(__file__),prior_candidate_sha256=sha256('bench/cpu_campaign_q.rs'),reason='Guard the previously promising flat objective at K64; preserve original Q for other shapes.')
    harness.main()

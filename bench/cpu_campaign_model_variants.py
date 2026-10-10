"""Exact time-grid and demography-only invariant cache candidates."""
from cpu_campaign_kernel_variants import replace


def prepare(scratch, label):
    assert label in ('grid','invariants')
    original=(scratch/'crates/psmc-core/src/model_workspace.rs').read_text()
    source=original.split('#[cfg(test)]')[0]
    source=source.replace('use crate::{','use psmc_core::{').replace('ModelWorkspace','CachedModelWorkspace')
    source=source.replace('Only the lifetime of six scratch\n//! allocations changes. This is not the later factored model/objective method.',
        'Exact grid/invariant caching is added in this isolated candidate.\n//! No factors, model equations or arithmetic groupings are changed.')
    source=source.replace('Nothing is cached across parameter vectors.','Only functions of bit-identical dependencies may be reused; full rows are overwritten.')
    source=source.replace('    tau: Vec<f64>,','''    tau: Vec<f64>,
    grid: Vec<f64>,
    grid_key: Option<(u64,u64)>,
    derived_valid: bool,
    saved_c_pi: f64,''')
    source=source.replace('            tau: vec![0.0; n],','''            tau: vec![0.0; n],
            grid: vec![0.0; n+1],
            grid_key: None,
            derived_valid: false,
            saved_c_pi: 0.0,''')
    old='''        } else {
            let grid_beta = ln(1.0 + max_t / settings.alpha) / (n - 1) as f64;'''
    new='''        } else if self.grid_key == Some((max_t.to_bits(), settings.alpha.to_bits())) {
            model.t[..n+1].copy_from_slice(&self.grid);
        } else {
            let grid_beta = ln(1.0 + max_t / settings.alpha) / (n - 1) as f64;'''
    assert source.count(old)==1
    source=source.replace(old,new)
    source=source.replace('''            model.t[n - 1] = max_t;
        }''','''            model.t[n - 1] = max_t;
            self.grid[..n].copy_from_slice(&model.t[..n]);
            self.grid[n] = 1000.0;
            self.grid_key = if max_t.is_finite() && settings.alpha.is_finite() {
                Some((max_t.to_bits(),settings.alpha.to_bits()))
            } else { None };
        }''')
    if label=='invariants':
        source=source.replace('''        for k in 0..n {
            lambda[k] = model.params[settings.pattern.groups[k] + 3];
        }''','''        let mut same_dependencies = self.derived_valid;
        for k in 0..n {
            let next = model.params[settings.pattern.groups[k] + 3];
            same_dependencies &= next.to_bits() == lambda[k].to_bits();
            lambda[k] = next;
        }''')
        source=source.replace('''            tau[k] = model.t[k + 1] - model.t[k];''','''            let next = model.t[k + 1] - model.t[k];
            same_dependencies &= next.to_bits() == tau[k].to_bits();
            tau[k] = next;''')
        source=source.replace('''        alpha[0] = 1.0;''','''        if same_dependencies {
            model.c_pi = self.saved_c_pi;
        } else {
        alpha[0] = 1.0;''')
        source=source.replace('''        model.c_sigma = 1.0 / (model.c_pi * rho) + 0.5;''','''        self.saved_c_pi = model.c_pi;
        self.derived_valid = model.c_pi.is_finite() && lambda.iter().chain(tau.iter()).chain(alpha.iter()).chain(beta.iter()).chain(q_aux.iter()).all(|v| v.is_finite());
        }
        model.c_sigma = 1.0 / (model.c_pi * rho) + 0.5;''')
    path=scratch/'crates/psmc-cpu/src/model_candidate.rs'
    source+='''
#[cfg(test)]
mod tests {
    use super::*;
    use psmc_core::{Pattern,rng::LegacyRng};
    fn exact(a: &[f64], b: &[f64]) {
        assert_eq!(a.len(),b.len());
        for (&a,&b) in a.iter().zip(b) { assert!(a.to_bits()==b.to_bits() || a.is_nan() && b.is_nan(),"{a:?} != {b:?}"); }
    }
    fn compare(a: &Model,b: &Model) {
        for (a,b) in [(&a.params,&b.params),(&a.t,&b.t),(&a.sigma,&b.sigma),(&a.initial,&b.initial),(&a.transition,&b.transition),(&a.emission,&b.emission)] { exact(a,b); }
        exact(&[a.c_pi,a.c_sigma],&[b.c_pi,b.c_sigma]);
    }
    #[test]
    fn dependencies_settings_poison_and_invalid_recovery() {
        for n in [1,2,3,4,7,23,64,65] {
            for divergence in [None,Some(0.4)] {
                let mut settings=Settings { pattern:Pattern {text:String::new(),groups:(0..n).map(|i|i/3).collect(),n_free:(n+2)/3},max_t:15.0,alpha:0.1,tr_ratio:4.0,ran_init:0.0,divergence,initial_params:None,explicit_times:None };
                let initial=Model::new(&settings,23,177,&mut LegacyRng::new(42));
                let mut expected=initial.clone();
                let mut actual=initial.clone();
                let mut workspace=CachedModelWorkspace::new(n);
                for round in 0..160 {
                    expected.params.clone_from(&initial.params);
                    // Repeated dependencies and individual changes both exercised.
                    let coordinate=round%expected.params.len();
                    expected.params[coordinate]*=1.0+(round/expected.params.len()) as f64*0.01;
                    match round%19 {
                        3=>expected.params[1]=0.0,
                        5=>expected.params[3]=0.0,
                        7=>expected.params[0]=f64::NAN,
                        9=>expected.params[2]=f64::INFINITY,
                        11=>expected.params[0]=-0.0,
                        13=>expected.params[3]=f64::NAN,
                        _=>{}
                    }
                    settings.alpha=if round%11<5 {0.1} else {0.2};
                    settings.explicit_times=if round%13<5 {Some((0..n).map(|i|i as f64*(0.2+0.01*(round%3) as f64)).collect())} else {None};
                    if round%7==0 { settings.pattern.groups.reverse(); }
                    actual.params.clone_from(&expected.params);
                    // A caller may mutate model outputs; cached dependencies must
                    // still restore every field that the dense update overwrites.
                    actual.t.fill(f64::NAN); actual.sigma.fill(f64::NAN);
                    actual.initial.fill(f64::NAN); actual.transition.fill(f64::NAN);
                    actual.emission[..2*n].fill(f64::NAN);
                    actual.c_pi=f64::NAN; actual.c_sigma=f64::NAN;
                    expected.update(&settings);
                    workspace.update(&mut actual,&settings);
                    compare(&expected,&actual);
                    // Immediate repeated call takes eligible reuse branches.
                    expected.update(&settings);
                    workspace.update(&mut actual,&settings);
                    compare(&expected,&actual);
                }
            }
        }
    }
    #[test]
    fn retained_grid_ignores_external_time_mutation_and_explicit_switches() {
        let mut settings=Settings { pattern:Pattern{text:String::new(),groups:vec![0,0,1,1],n_free:2},max_t:15.0,alpha:0.1,tr_ratio:4.0,ran_init:0.0,divergence:None,initial_params:None,explicit_times:None };
        let mut model=Model::new(&settings,1,20,&mut LegacyRng::new(42));
        let mut reference=model.clone();
        let mut workspace=CachedModelWorkspace::new(4);
        for round in 0..8 {
            settings.explicit_times=if round%2==0 {None} else {Some(vec![1.0,2.0,4.0,8.0])};
            model.t.fill(-999.0);
            reference.update(&settings); workspace.update(&mut model,&settings);
            compare(&reference,&model);
        }
    }
}
'''
    path.write_text(source)
    library=scratch/'crates/psmc-cpu/src/lib.rs'
    with library.open('a') as file: file.write('\nmod model_candidate;\n')
    engine=scratch/'crates/psmc-cpu/src/engine.rs'
    replace(engine,'    model_workspace::ModelWorkspace,','')
    replace(engine,'use crate::{SimdMode, Workspace};','use crate::{SimdMode, Workspace};\nuse crate::model_candidate::CachedModelWorkspace as ModelWorkspace;')

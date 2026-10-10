//! Experimental exact forward/backward checkpoint and recompute workspace.
//! Injected only into disposable CPU crate copies; not a production API.
use crate::{PreparedModel, SimdMode, simd::Avx};
use psmc_core::{hmm::Counts, math::ln, model::Model};

pub struct CheckpointWorkspace {
    n: usize,
    tile: usize,
    avx: Option<Avx>,
    scales: Vec<f64>,
    bounds: Vec<usize>,
    fc: Vec<f64>,
    bc: Vec<f64>,
    f: Vec<f64>,
    b: Vec<f64>,
    rolling: [Vec<f64>; 2],
    counts: Counts,
}

fn forward(avx: Option<Avx>, prepared: &PreparedModel<'_>, symbol: u8,
           previous: &[f64], current: &mut [f64]) -> f64 {
    let model = prepared.model;
    let n = model.n;
    let emission = &model.emission[symbol as usize*n..][..n];
    if let Some(avx) = avx {
        avx.forward(current,previous,&model.transition,emission);
    } else {
        for ((target,&e),row) in current.iter_mut().zip(emission).zip(prepared.transpose.chunks_exact(n)) {
            let mut sum=0.0;
            for (&f,&a) in previous.iter().zip(row) { sum+=f*a; }
            *target=e*sum;
        }
    }
    let mut sum=0.0;
    for &value in current.iter() { sum+=value; }
    for value in current { *value/=sum; }
    sum
}

fn backward(avx: Option<Avx>, prepared: &PreparedModel<'_>, symbol: u8,
            scale: f64, next: &[f64], current: &mut [f64]) {
    let n=prepared.model.n;
    let square=n*n;
    let base=symbol as usize*square;
    if let Some(avx)=avx {
        avx.backward(current,next,&prepared.emission_transition_transpose[base..][..square],scale);
    } else {
        for (target,row) in current.iter_mut().zip(prepared.emission_transition[base..][..square].chunks_exact(n)) {
            let mut sum=0.0;
            for (&ae,&b) in row.iter().zip(next) { sum+=ae*b; }
            *target=sum/scale;
        }
    }
}

impl CheckpointWorkspace {
    pub fn new(n: usize, tile: usize, mode: SimdMode) -> Self {
        assert!(n>0 && tile>0);
        Self { n,tile,avx:Avx::select(mode,n).unwrap(),scales:Vec::new(),bounds:Vec::new(),
            fc:Vec::new(),bc:Vec::new(),f:Vec::new(),b:Vec::new(),rolling:[vec![0.0;n],vec![0.0;n]],counts:Counts::zero(n) }
    }
    pub fn prepare<'a>(&self, model: &'a Model) -> PreparedModel<'a> {
        PreparedModel::with_avx_layout(model,self.avx.is_some())
    }
    pub fn evaluate<F: FnMut(usize,&[f64],&[f64])>(&mut self, prepared: &PreparedModel<'_>, observations: &[u8], mut inspect: F)
        -> (&Counts,f64,f64) {
        assert_eq!(prepared.model.n,self.n);
        assert!(!observations.is_empty() && observations.iter().all(|&v|v<=2));
        let n=self.n;
        let length=observations.len();
        let model=prepared.model;
        let rows=length.checked_add(1).expect("length overflow");
        self.scales.resize(rows,0.0);
        self.scales[0]=1.0;
        self.bounds.clear();
        self.bounds.extend((1..length).step_by(self.tile));
        self.bounds.push(length);
        let checkpoint_cells=self.bounds.len().checked_mul(n).expect("checkpoint overflow");
        self.fc.resize(checkpoint_cells,0.0);
        self.bc.resize(checkpoint_cells,0.0);
        let [previous,current]=&mut self.rolling;
        let first=&model.emission[observations[0] as usize*n..][..n];
        let mut sum=0.0;
        for ((value,&initial),&e) in previous.iter_mut().zip(&model.initial).zip(first) {
            *value=initial*e;
            sum+=*value;
        }
        for value in previous.iter_mut() { *value/=sum; }
        self.scales[1]=sum;
        self.fc[..n].copy_from_slice(previous);
        let mut checkpoint=1;
        for u in 2..=length {
            self.scales[u]=forward(self.avx,prepared,observations[u-1],previous,current);
            std::mem::swap(previous,current);
            if checkpoint<self.bounds.len() && u==self.bounds[checkpoint] {
                self.fc[checkpoint*n..][..n].copy_from_slice(previous);
                checkpoint+=1;
            }
        }
        let mut likelihood=0.0;
        let mut product=1.0;
        for &scale in &self.scales[1..] {
            product*=scale;
            if product<1e-25 || product>=1.0/1e-25 { likelihood+=ln(product); product=1.0; }
        }
        likelihood+=ln(product);
        previous.fill(1.0/self.scales[length]);
        checkpoint=self.bounds.len()-1;
        self.bc[checkpoint*n..][..n].copy_from_slice(previous);
        for u in (1..length).rev() {
            backward(self.avx,prepared,observations[u],self.scales[u],previous,current);
            std::mem::swap(previous,current);
            if checkpoint>0 && u==self.bounds[checkpoint-1] {
                checkpoint-=1;
                self.bc[checkpoint*n..][..n].copy_from_slice(previous);
            }
        }
        assert_eq!(checkpoint,0);
        let mut check=0.0;
        for ((&initial,&b),&e) in model.initial.iter().zip(&self.bc[..n]).zip(first) { check+=initial*b*e; }
        self.counts.a0.fill(0.0);
        self.counts.a.fill(1e-25);
        self.counts.e.fill(1e-25);
        self.counts.q0=0.0;
        for tile in 0..self.bounds.len()-1 {
            let begin=self.bounds[tile];
            let stop=self.bounds[tile+1];
            let cells=(stop-begin+1).checked_mul(n).expect("tile overflow");
            self.f.resize(cells,0.0);
            self.b.resize(cells,0.0);
            self.f[..n].copy_from_slice(&self.fc[tile*n..][..n]);
            self.b[(stop-begin)*n..].copy_from_slice(&self.bc[(tile+1)*n..][..n]);
            for u in begin+1..=stop {
                let at=(u-begin)*n;
                let (earlier,later)=self.f.split_at_mut(at);
                let scale=forward(self.avx,prepared,observations[u-1],&earlier[at-n..],&mut later[..n]);
                assert!(scale.to_bits()==self.scales[u].to_bits() || scale.is_nan() && self.scales[u].is_nan());
            }
            for u in (begin..stop).rev() {
                let at=(u-begin)*n;
                let (earlier,later)=self.b.split_at_mut(at+n);
                backward(self.avx,prepared,observations[u],self.scales[u],&later[..n],&mut earlier[at..]);
            }
            inspect(begin,&self.f,&self.b);
            for u in begin..stop {
                let at=(u-begin)*n;
                let f=&self.f[at..][..n];
                let b=&self.b[at..][..n];
                let next=&self.b[at+n..][..n];
                let products=&prepared.emission_transition[observations[u] as usize*n*n..][..n*n];
                if let Some(avx)=self.avx {
                    avx.counts(&mut self.counts.a,f,products,next);
                } else {
                    for k in 0..n { for l in 0..n {
                        self.counts.a[k*n+l]+=f[k]*products[k*n+l]*next[l];
                    }}
                }
                let emission=&mut self.counts.e[observations[u-1] as usize*n..][..n];
                for ((count,&f),&b) in emission.iter_mut().zip(f).zip(b) { *count+=f*b*self.scales[u]; }
            }
        }
        if length==1 { inspect(1,&self.fc,&self.bc); }
        for (((count,&initial),&e),&b) in self.counts.a0.iter_mut().zip(&model.initial).zip(first).zip(&self.bc[..n]) {
            *count+=initial*e*b;
        }
        (&self.counts,likelihood,check)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use psmc_core::{Pattern,Settings,rng::LegacyRng};
    fn exact(a: &[f64],b: &[f64]) {
        assert_eq!(a.len(),b.len());
        for (&a,&b) in a.iter().zip(b) { assert!(a.to_bits()==b.to_bits() || a.is_nan() && b.is_nan(),"{a:?} != {b:?}"); }
    }
    #[test]
    fn checkpoints_reconstruct_all_messages_and_counts() {
        for n in [1,4,7,23,64,65] {
            let settings=Settings {pattern:Pattern{text:String::new(),groups:(0..n).map(|i|i/3).collect(),n_free:(n+2)/3},max_t:15.0,alpha:0.1,tr_ratio:4.0,ran_init:0.0,divergence:None,initial_params:None,explicit_times:None};
            let mut model=Model::new(&settings,7,100,&mut LegacyRng::new(42));
            for mode in [SimdMode::Off,SimdMode::Auto] {
                for tile in [16,64] {
                    let mut baseline=crate::Workspace::with_simd(n,mode).unwrap();
                    let mut candidate=CheckpointWorkspace::new(n,tile,mode);
                    for length in [1,2,tile-1,tile,tile+1,2*tile+1,3] {
                        let observations:Vec<_>=(0..length).map(|i|if i%29==0 {1} else if i%17<3 {2} else {0}).collect();
                        let p=baseline.prepare(&model);
                        let (messages,expected)=baseline.evaluate(&p,&observations);
                        let p=candidate.prepare(&model);
                        let (actual,lk,check)=candidate.evaluate(&p,&observations,|begin,f,b| {
                            exact(f,&messages.forward[begin*n..begin*n+f.len()]);
                            exact(b,&messages.backward[begin*n..begin*n+b.len()]);
                        });
                        exact(&actual.a,&expected.a); exact(&actual.e,&expected.e); exact(&actual.a0,&expected.a0);
                        exact(&[lk,check],&[messages.log_likelihood,messages.backward_check]);
                    }
                }
            }
            // Impossible emissions exercise nonfinite classes and recovery.
            model.emission[..n].fill(0.0);
            let mut baseline=crate::Workspace::new(n);
            let mut candidate=CheckpointWorkspace::new(n,2,SimdMode::Auto);
            let p=baseline.prepare(&model);
            let (messages,expected)=baseline.evaluate(&p,&[0,0,0,0,0]);
            let p=candidate.prepare(&model);
            let (actual,lk,check)=candidate.evaluate(&p,&[0,0,0,0,0],|begin,f,b| {
                exact(f,&messages.forward[begin*n..begin*n+f.len()]);
                exact(b,&messages.backward[begin*n..begin*n+b.len()]);
            });
            exact(&actual.a,&expected.a); exact(&actual.e,&expected.e); exact(&actual.a0,&expected.a0);
            exact(&[lk,check],&[messages.log_likelihood,messages.backward_check]);
        }
    }
}

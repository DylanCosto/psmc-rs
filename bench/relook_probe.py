"""Count exact message repetition and uniform count tiles in complete HG fits."""
import io,json,os,subprocess,tarfile
from pathlib import Path
from common import ROOT,save,sha256,timed_run
from phase2_common import clean_env
from phase1_differential import compare_output

os.chdir(ROOT)
raw=Path('work/relook/probe');raw.mkdir(parents=True)
scratch=raw/'source';scratch.mkdir()
archive=subprocess.check_output(['git','archive','30efe0b','Cargo.toml','Cargo.lock','rust-toolchain.toml','crates'])
with tarfile.open(fileobj=io.BytesIO(archive)) as tar:tar.extractall(scratch,filter='data')
p=scratch/'crates/psmc-cpu/src/lib.rs';s=p.read_text()
needle='        (messages, counts)'
assert s.count(needle)==1
diagnostic=r'''
        let equal = |a: &[f64], b: &[f64]| a.iter().zip(b).all(|(a,b)| a.to_bits()==b.to_bits() && a.is_finite());
        let mut f_equal=0usize; let mut b_equal=0usize; let mut both=0usize;
        for u in 2..length {
            let f = equal(&messages.forward[u*n..(u+1)*n], &messages.forward[(u-1)*n..u*n]);
            let b = equal(&messages.backward[u*n..(u+1)*n], &messages.backward[(u+1)*n..(u+2)*n]);
            f_equal += usize::from(f); b_equal += usize::from(b); both += usize::from(f && b);
        }
        let mut uniform=0usize;
        for begin in (1..length).step_by(16) {
            let end=(begin+16).min(length);
            if observations[begin..end].iter().all(|&z| z==observations[begin]) { uniform+=end-begin; }
        }
        eprintln!("RELOOK {{\"sites\":{},\"forward_equal\":{},\"backward_equal\":{},\"both_equal\":{},\"uniform_tile_sites\":{}}}",length,f_equal,b_equal,both,uniform);
'''
p.write_text(s.replace(needle,diagnostic+needle))
cmd=['cargo','build','--release','--locked','--offline','-p','psmc-cli']
with (raw/'build.log').open('w') as log:subprocess.run(cmd,cwd=scratch,env=clean_env(),stdout=log,stderr=subprocess.STDOUT,check=True)
binary=scratch/'target/release/psmc-rs'
r=dict(status='running',base='30efe0b',runner_sha256=sha256(__file__),binary_sha256=sha256(binary),source_sha256=sha256(p),build_command=cmd,cases=[])
cases=[('hg001-bootstrap01','work/hg-input/bootstrap-01.psmcfa',json.load(open('bench/hg-benchmark.json'))['canonical_outputs'][1]['path']),('hg002-chr1','work/cpu-next/hg002/HG002_GRCh38_chr1.psmcfa','work/cpu-next/large/vanilla.psmc')]
for name,inp,oracle in cases:
    cmd=['taskset','-c','0',str(binary),'--backend','cpu','--seed','42','-p','4+25*2+4+6','-N','30','-t','15','-r','5','-I','0',inp]
    run=timed_run(cmd,ROOT/raw/name,env=clean_env(),timeout=1800);assert run['exit_code']==0
    comparison=compare_output(Path(oracle).read_bytes(),Path(run['output']).read_bytes())
    rows=[json.loads(line[7:]) for line in (raw/(name+'.stderr')).read_text().splitlines() if line.startswith('RELOOK ')]
    totals={key:sum(row[key] for row in rows) for key in rows[0]}
    r['cases'].append(dict(name=name,input=inp,input_sha256=sha256(inp),oracle=oracle,oracle_sha256=sha256(oracle),run=run,comparison=comparison,rows=rows,totals=totals))
    save('bench/relook-probe.json',r);print(name,totals,flush=True)
r['status']='passed';save('bench/relook-probe.json',r)

#!/usr/bin/env python3
"""Pinned C sensitivity; no fast-math; same materialized samples in every build."""
import concurrent.futures as cf
import json, os, platform, subprocess, time
from pathlib import Path
from common import ROOT, save, sha256, timed_run, read_fasta, write_fasta, draw_bootstrap
from phase2_common import clean_env
RAW=Path('work/equivalent/c-baseline')
REPORT='bench/equivalent-c-baseline.json'
ARGS=['-p','4+25*2+4+6','-N','30','-t','15','-r','5','-I','0']
def main():
    os.chdir(ROOT); RAW.mkdir()
    source=Path('work/vanilla')
    sources=['khmm.c','kmin.c','cli.c','core.c','em.c','aux.c','main.c']
    report=dict(status='running',runner_sha256=sha256(__file__),source_commit='82fa2ada83ee463fe1251b562ae3d60e82d7ad6a',source_hashes={p.name:sha256(p) for p in source.glob('*') if p.suffix in ['.c','.h']},compiler=subprocess.check_output(['gcc','--version'],text=True),platform=platform.platform(),selected_builds=['o2','fma'],builds={},datasets={},runs=[])
    for name,flags in [('o2',['-O2','-ffp-contract=off']),('o0',['-O0','-ffp-contract=off']),('fma',['-O2','-march=native','-ffp-contract=fast'])]:
        binary=RAW/name
        cmd=['gcc','-g','-Wall','-Wno-unused-function','-Iwork/deps/zlib/usr/include',*flags,*[str(source/p) for p in sources],'-o',str(binary),'-lm','-l:libz.so.1']
        build=subprocess.run(cmd,capture_output=True,text=True);(RAW/(name+'.build.log')).write_text(build.stdout+build.stderr);assert build.returncode==0
        asm=subprocess.check_output(['objdump','-d',str(binary)],text=True)
        fmas=[line for line in asm.splitlines() if any(x in line for x in ['vfmadd','vfmsub','vfnmadd','vfnmsub'])]
        report['builds'][name]=dict(path=str(binary),sha256=sha256(binary),command=cmd,fma_instructions=len(fmas));save(REPORT,report)
    for label,original,blocks,seed in [
        ('hg001','work/hg-input/NA12878_chr22.psmcfa','work/hg-input/blocks-50000.psmcfa',20261012),
        ('hg002','work/cpu-next/hg002/HG002_GRCh38_chr1.psmcfa','work/cpu-next/large/blocks-50000.psmcfa',20261101)]:
        records=read_fasta(blocks); samples=[]
        for i in range(30):
            indices,draws=draw_bootstrap(records,seed+i);p=RAW/f'{label}-sample-{i:02}.psmcfa';write_fasta(p,[records[j] for j in indices])
            samples.append(dict(index=i,seed=seed+i,path=str(p),sha256=sha256(p),indices=indices,draws=draws))
        report['datasets'][label]=dict(original=original,original_sha256=sha256(original),blocks=blocks,blocks_sha256=sha256(blocks),samples=samples)
    save(REPORT,report)
    for label,data in report['datasets'].items():
        for name in report['selected_builds']:
            build=report['builds'][name]
            cmd=['taskset','-c','0',build['path'],*ARGS,data['original']]
            run=timed_run(cmd,ROOT/RAW/f'{label}-{name}-original',env=clean_env(),timeout=3600)
            run.update(dataset=label,build=name,kind='original');report['runs'].append(run);save(REPORT,report)
            print(label,name,'original',round(run['wall_seconds'],2),flush=True)
            start=time.perf_counter()
            def fit(sample):
                i=sample['index'];cmd=[build['path'],*ARGS,sample['path']]
                r=timed_run(cmd,ROOT/RAW/f'{label}-{name}-{i:02}',env=clean_env(),timeout=3600)
                r.update(dataset=label,build=name,kind='bootstrap',index=i);return r
            with cf.ThreadPoolExecutor(max_workers=16) as pool:
                for r in pool.map(fit,data['samples']):
                    report['runs'].append(r);save(REPORT,report)
            print(label,name,'30 bootstraps',round(time.perf_counter()-start,2),flush=True)
    report['status']='completed' if all(r['exit_code']==0 for r in report['runs']) else 'failed';save(REPORT,report)
if __name__=='__main__':main()

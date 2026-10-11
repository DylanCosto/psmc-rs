#!/usr/bin/env python3
"""Bounded sequential C/strict/equivalent HG001 whole-autosome comparison."""
import argparse
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import shutil
import signal
import subprocess
import sys
import threading
import time

import known_truth as p
import known_truth_200mb as metrics
from known_truth_genome import sha,save,available,disk_bytes,GIB

SOURCES=['docs/hg001-genome-protocol.md','bench/hg001_genome_run.py',
         'bench/hg001_genome_prepare.py','bench/cpu_next_hg002.py','bench/common.py',
         'bench/known_truth.py','bench/known_truth_200mb.py','bench/known_truth_genome.py']


def child():
    ceiling=int(sys.argv[2])*GIB
    resource.setrlimit(resource.RLIMIT_AS,(ceiling,ceiling))
    resource.setrlimit(resource.RLIMIT_FSIZE,(512*1024**2,512*1024**2))
    os.nice(10);os.execv(sys.argv[3],sys.argv[3:])


class Run:
    def __init__(self,root):
        self.root=root;self.process=None;self.stage_name=None;self.reason=None
        self.stop=threading.Event();self.finished=threading.Event()
        self.monitor=threading.Thread(target=self.watch,daemon=True);self.monitor.start()

    def abort(self,reason):
        self.reason=self.reason or reason;self.stop.set()
        save(self.root/'stop.json',{'reason':self.reason,'time':time.time()})
        process=self.process
        if process and process.poll() is None:
            try:os.killpg(process.pid,signal.SIGTERM)
            except ProcessLookupError:pass

    def watch(self):
        try:
            with (self.root/'resources.jsonl').open('a',buffering=1) as f:
                while not self.finished.is_set():
                    ram=available();free=shutil.disk_usage(self.root).free;size=disk_bytes(self.root)
                    process=self.process;rss=0
                    if process and process.poll() is None:
                        for proc in Path('/proc').iterdir():
                            if not proc.name.isdigit():continue
                            try:
                                fields=(proc/'stat').read_text().rsplit(')',1)[1].split()
                                if int(fields[2])==process.pid:rss+=int((proc/'statm').read_text().split()[1])*os.sysconf('SC_PAGE_SIZE')
                            except (OSError,ValueError,IndexError):pass
                    f.write(json.dumps({'time':time.time(),'stage':self.stage_name,
                        'pid':process.pid if process and process.poll() is None else None,
                        'rss_bytes':rss,'available_ram':ram,'free_disk':free,'campaign_bytes':size})+'\n')
                    if ram<4*GIB or free<25*GIB or size>4*GIB:self.abort('resource floor reached')
                    self.finished.wait(2)
        except BaseException as e:self.abort('monitor failed: '+repr(e))

    def stage(self,name,command,ceiling=10,min_ram=14):
        base=self.root/name;done=self.root/f'{name}.done.json';out=self.root/f'{name}.out'
        if done.exists():
            result=json.loads(done.read_text());assert result['command']==list(map(str,command))
            assert sha(out)==result['output_sha256'];return result
        stamp=time.time_ns()
        for suffix in ['out','stderr','time']:
            path=self.root/f'{name}.{suffix}'
            if path.exists():path.rename(self.root/f'{name}.partial-{stamp}.{suffix}')
        while available()<min_ram*GIB or shutil.disk_usage(self.root).free<30*GIB:
            if self.stop.wait(2):raise RuntimeError(self.reason)
        if self.stop.is_set():raise RuntimeError(self.reason)
        self.stage_name=name;started=time.time()
        wrapper=[sys.executable,str(Path(__file__).resolve()),'--child',str(ceiling),
            '/usr/bin/time','-v','-o',str(self.root/f'{name}.time'),*map(str,command)]
        with out.open('wb') as output,(self.root/f'{name}.stderr').open('wb') as err:
            self.process=subprocess.Popen(wrapper,cwd=self.root,stdout=output,stderr=err,start_new_session=True)
            save(self.root/f'{name}.attempt-{stamp}.json',{'started':started,'pid':self.process.pid,'command':list(map(str,command))})
            while self.process.poll() is None:
                if self.stop.wait(1) or time.time()-started>6*3600:
                    self.abort('six-hour stage timeout' if not self.stop.is_set() else self.reason)
                    try:os.killpg(self.process.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                    break
            code=self.process.wait()
        result={'command':list(map(str,command)),'started':started,'seconds':time.time()-started,
            'exit_code':code,'ceiling_gib':ceiling,'output_sha256':sha(out)}
        save(self.root/f'{name}.attempt-{stamp}.json',result)
        self.process=None;self.stage_name=None
        if code or self.stop.is_set():raise RuntimeError(f'{name} failed: {code}; {self.reason}')
        save(done,result);print('completed',name,round(result['seconds'],2),'seconds',flush=True)
        return result

    def close(self):self.finished.set();self.monitor.join()


def freeze(root):
    sources={name:sha(p.ROOT/name) for name in SOURCES}
    paths={'c':p.ROOT/'work/vanilla/psmc','rust':p.ROOT/'bin/psmc-rs',
           'fq2psmcfa':p.ROOT/'work/vanilla/utils/fq2psmcfa',
           'ridge':p.ROOT/'target/release/examples/equivalent_ridge'}
    if (root/'frozen.json').exists():
        frozen=json.loads((root/'frozen.json').read_text());assert frozen['source_hashes']==sources
        for name,digest in frozen['binary_hashes'].items():assert sha(root/'binaries'/name)==digest
    else:
        (root/'binaries').mkdir(exist_ok=True)
        for name,source in paths.items():shutil.copy2(source,root/'binaries'/name)
        frozen={'source_hashes':sources,'binary_hashes':{n:sha(v) for n,v in paths.items()},
            'commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=p.ROOT,text=True).strip(),
            'diff_sha256':hashlib.sha256(subprocess.check_output(['git','diff'],cwd=p.ROOT)).hexdigest(),
            'created':time.time(),'sources':json.loads((root/'sources/downloads.json').read_text())}
        save(root/'frozen.json',frozen)
    return frozen,{n:root/'binaries'/n for n in paths}


def timing(path):
    result={}
    for line in path.read_text().splitlines():
        line=line.strip()
        for prefix,key in [('User time (seconds):','user_seconds'),('System time (seconds):','system_seconds'),
                           ('Maximum resident set size (kbytes):','peak_rss_kib')]:
            if line.startswith(prefix):result[key]=float(line[len(prefix):])
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,required=True)
    args=parser.parse_args();root=args.root.resolve();root.mkdir(exist_ok=True,parents=True)
    with (root/'run.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);lock.seek(0);lock.truncate();lock.write(str(os.getpid()));lock.flush()
        frozen,binaries=freeze(root);run=Run(root)
        signal.signal(signal.SIGTERM,lambda *_:run.abort('user or external SIGTERM'))
        signal.signal(signal.SIGINT,lambda *_:run.abort('user or external SIGINT'))
        try:
            preparation=run.stage('prepare',[sys.executable,str(p.ROOT/'bench/hg001_genome_prepare.py'),
                                           '--root',str(root)],ceiling=3,min_ram=10)
            source=json.loads((root/'input.json').read_text());input_path=root/'HG001_GRCh38_autosomes.psmcfa'
            assert sha(input_path)==source['input_sha256']
            runs={};texts={};params={};curves={}
            for mode in ['c','strict','equivalent']:
                command=[str(binaries['c']),*p.FIT] if mode=='c' else [str(binaries['rust']),
                    '--mode',mode,'--record-workers','16' if mode=='strict' else '8',
                    '--stats',str(root/f'{mode}.stats.json'),
                    *(['--memory-mib','8192'] if mode=='strict' else []),*p.FIT]
                runs[mode]=run.stage(mode,[*command,str(input_path)])
                runs[mode]['timing']=timing(root/f'{mode}.time')
                texts[mode]=(root/f'{mode}.out').read_text();curves[mode],params[mode]=p.curve(texts[mode])
            exact=p.numerical(texts['c'])==p.numerical(texts['strict'])
            bands={}
            for band,(a,b) in metrics.BANDS.items():
                times=metrics.grid(a,b)
                logs={m:[metrics.at(v,t) for t in times] for m,v in params.items()}
                errors=[abs(s-e) for s,e in zip(logs['strict'],logs['equivalent'])]
                bands[band]={'rms_log_difference':math.sqrt(sum(x*x for x in errors)/128),
                             'max_log_difference':max(errors),'log_curves':logs}
            legacy_ll={m:float([line.split()[1] for line in text.splitlines() if line.startswith('LK\t')][-1]) for m,text in texts.items()}
            assert all(math.isfinite(v) for v in legacy_ll.values())
            difference={field:abs(params['equivalent'][field]/params['strict'][field]-1) for field in ['theta','rho']}
            difference['legacy_ll_absolute']=abs(legacy_ll['equivalent']-legacy_ll['strict'])
            difference['legacy_ll_per_bin']=difference['legacy_ll_absolute']/source['bins']
            difference['full_grid_rms_log']=p.rmse(curves['strict'],curves['equivalent'])
            difference['full_grid_max_log']=max(abs(s-e) for s,e in zip(curves['strict'],curves['equivalent']))
            screen=all(bands[b]['rms_log_difference']<=.01 for b in ['primary_early','primary_late']) and all(difference[f]<=.001 for f in ['theta','rho']) and difference['legacy_ll_per_bin']<=1e-6
            diagnostic=None
            if not screen or any(b['rms_log_difference']>.01 for b in bands.values()):
                run.stage('ridge',[str(binaries['ridge']),str(input_path),str(root/'strict.out'),str(root/'equivalent.out')])
                diagnostic=[json.loads(line) for line in (root/'ridge.out').read_text().splitlines()]
            report={'metadata':frozen,'input':source,'preparation':preparation,'runs':runs,
                'strict_c_exact':exact,'finite_complete_fits':True,'equivalent_screen_passed':screen,
                'parameters':params,'legacy_ll':legacy_ll,'bands':bands,'differences':difference,
                'diagnostic':diagnostic,'stats':{m:json.loads((root/f'{m}.stats.json').read_text()) for m in ['strict','equivalent']},
                'scope':'Whole autosomes of public HG001; single observations of runtime. No truth/CI/bootstrap qualification claim.'}
            save(root/'report.json',metrics.relative(report))
            print(json.dumps({'strict_c_exact':exact,'equivalent_screen_passed':screen,'differences':difference},indent=2),flush=True)
        finally:run.close()


if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--child':child()
    else:main()

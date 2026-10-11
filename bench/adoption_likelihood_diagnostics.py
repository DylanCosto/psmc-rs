#!/usr/bin/env python3
"""Fresh observed likelihood at flagged final printed vectors; no optimizer refit.
See the frozen qualification protocol and adoption-likelihood-diagnostic-notes.md.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import shutil
import signal
import subprocess
import time
from pilot_decimal_model import model, parse
from audit_adoption_qualification import sequences

ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN = ROOT / 'work/adoption-qualification'
OUT = ROOT / 'work/adoption-likelihood'
GIB = 1024**3


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path): return json.loads(Path(path).read_text())
def save(path, value): Path(path).write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')
def available(): return int(next(l.split()[1] for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:')))*1024


def limits():
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    os.nice(10)
    resource.setrlimit(resource.RLIMIT_AS, (3*GIB, 3*GIB))
    resource.setrlimit(resource.RLIMIT_FSIZE, (512*1024**2, 512*1024**2))


def run(name, command):
    assert available() >= 4*GIB and shutil.disk_usage(ROOT).free >= 25*GIB
    started = time.monotonic()
    with (OUT/(name+'.out')).open('x') as output, (OUT/(name+'.stderr')).open('x') as error:
        args=['/usr/bin/time', '-v', '-o', str(OUT/(name+'.time')), *map(str,command)]
        process=subprocess.Popen(args,cwd=ROOT,stdout=output,stderr=error,preexec_fn=limits,start_new_session=True)
        try:
            with (OUT/(name+'.resources.jsonl')).open('x') as samples:
                while process.poll() is None:
                    ram=available();disk=shutil.disk_usage(ROOT).free
                    size=sum(p.stat().st_size for p in OUT.rglob('*') if p.is_file())
                    samples.write(json.dumps(dict(time=time.time(),available_ram=ram,free_disk=disk,bytes=size))+'\n');samples.flush()
                    if ram<4*GIB or disk<25*GIB or size>2*GIB: raise RuntimeError('diagnostic resource guard')
                    if time.monotonic()-started>3600: raise RuntimeError('one-hour diagnostic timeout')
                    time.sleep(2)
            if process.wait()!=0: raise RuntimeError('diagnostic process failed; inspect retained stderr')
        except BaseException:
            if process.poll() is None:
                os.killpg(process.pid,signal.SIGTERM)
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
            raise
    return dict(command=[str(p).replace(str(ROOT)+'/', '') for p in command], wall_seconds=time.monotonic()-started,
                time_sha256=sha(OUT/(name+'.time')),output_sha256=sha(OUT/(name+'.out')),
                stderr_sha256=sha(OUT/(name+'.stderr')),resources_sha256=sha(OUT/(name+'.resources.jsonl')))


def main():
    def interrupted(*_): raise RuntimeError('diagnostic interrupted by SIGTERM')
    signal.signal(signal.SIGTERM, interrupted)
    report=read(CAMPAIGN/'report.json');audit=read(ROOT/'bench/adoption-qualification-audit.json')
    assert audit['integrity_passed'] and audit['raw_report_sha256']==sha(CAMPAIGN/'report.json')
    OUT.mkdir(exist_ok=False)
    shutil.copy2(ROOT/'target/release/examples/adoption_likelihood', OUT/'evaluator')
    meta=dict(source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
              evaluator_sha256=sha(OUT/'evaluator'),evaluator_source_sha256=sha(ROOT/'crates/psmc-cpu/examples/adoption_likelihood.rs'),
              runner_sha256=sha(__file__),oracle_sha256=sha(ROOT/'bench/pilot_decimal_model.py'),
              campaign_report_sha256=sha(CAMPAIGN/'report.json'), pairs=[],
              cpu_affinity=[min(os.sched_getaffinity(0))],child_address_space_gib=3,child_file_limit_mib=512,nice_increment=10,
              scope='Fresh LL at printed final parameters; not a convergence test or new acceptance threshold',
              slice_rule='If absolute log first-lambda ratio >0.1, sample five log-spaced points between endpoints at each endpoint background')
    save(OUT/'frozen.json',meta)
    blocks=sequences(CAMPAIGN/'blocks.psmcfa')
    manifest=read(CAMPAIGN/'strict/manifest.json')
    for index in report['diagnostic_required']:
        name=f'pair-{index:02}'
        paths={mode:CAMPAIGN/mode/f'replicate-{index:02}.psmc' for mode in ['strict','equivalent']}
        params={mode:parse(path)[0] for mode,path in paths.items()};groups=parse(paths['strict'])[1]
        assert groups==parse(paths['equivalent'])[1]
        points=[(mode,values) for mode,values in params.items()]
        log_ratio=abs(math.log(params['equivalent'][3]/params['strict'][3]))
        if log_ratio>.1:
            for mode,base in params.items():
                for k in range(5):
                    values=base.copy();f=k/4
                    values[3]=math.exp((1-f)*math.log(params['strict'][3])+f*math.log(params['equivalent'][3]))
                    points.append((f'{mode}-lambda0-{k}',values))
        matrix_path=OUT/(name+'.matrices');matrix_lines=[]
        for label,values in points:
            low=model(values,groups,50);high=model(values,groups,80)
            assert low==high, 'Decimal 50/80 rounded matrices disagree'
            matrix_lines.append(label+' '+' '.join(map(repr,values+high)))
        matrix_path.write_text('\n'.join(matrix_lines)+'\n')
        sample=OUT/(name+'.psmcfa')
        selected=manifest['replicates'][index]['source_indices']
        with sample.open('x') as output:
            for occurrence,source in enumerate(selected):
                sequence=blocks[source][1];output.write(f'>block-{source}-occurrence-{occurrence}\n')
                for j in range(0,len(sequence),60):output.write(sequence[j:j+60]+'\n')
        input_sha=sha(sample)
        record=run(name,[OUT/'evaluator',sample,paths['strict'],matrix_path])
        rows=[json.loads(line) for line in (OUT/(name+'.out')).read_text().splitlines()]
        assert [r['label'] for r in rows]==[p[0] for p in points]
        endpoints={r['label']:r for r in rows[:2]}
        literal_valid=all(r['literal_ll'] is not None for r in endpoints.values())
        field='literal_ll' if literal_valid else 'll'
        delta=endpoints['equivalent'][field]-endpoints['strict'][field]
        meta['pairs'].append(dict(index=index,rows=rows,run=record,common_evaluation='literal' if literal_valid else 'Decimal-80 rounded to f64',
                                 ll_delta_equivalent_minus_strict=delta,decimal_ll_delta=endpoints['equivalent']['ll']-endpoints['strict']['ll'],
                                 parameters=params,first_lambda_abs_log_ratio=log_ratio,decimal_50_80_identical=True,
                                 sampled_input_sha256=input_sha,source_indices=selected,
                                 source_blocks_sha256=sha(CAMPAIGN/'blocks.psmcfa'),matrix_sha256=sha(matrix_path),
                                 fit_sha256={m:sha(p) for m,p in paths.items()}))
        # Only this generated, exactly reconstructible duplicate is removed.
        # Original block input, manifest, model points and every result are retained.
        sample.unlink()
        save(OUT/'progress.json',meta)
        print(name,'fresh LL delta',delta,'using',meta['pairs'][-1]['common_evaluation'],flush=True)
    save(ROOT/'bench/adoption-likelihood-diagnostics.json',meta)
    print('diagnostics complete',len(meta['pairs']),flush=True)


if __name__=='__main__':
    try: main()
    except BaseException as error:
        if OUT.exists(): save(OUT/'failure.json',dict(error=repr(error),time=time.time()))
        raise

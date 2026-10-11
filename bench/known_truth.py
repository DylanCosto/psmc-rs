#!/usr/bin/env python3
"""Run the fixed prospective known-truth pilot; preserve every fit and failure."""
import argparse
from bisect import bisect_right
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import shlex
import statistics
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
MU, BIN, LENGTH, RECORDS, REPLICATES = 2.5e-8, 100, 1_000_000, 20, 10
FIT = ['-p', '4+25*2+4+6', '-N', '30', '-t', '15', '-r', '5', '-I', '0']
GRID = [1000 * math.exp(math.log(200) * i / 255) for i in range(256)]
HISTORIES = {
    'constant': [(0, 10000)],
    'bottleneck': [(0, 10000), (2000, 2000), (6000, 10000)],
    'expansion': [(0, 20000), (4000, 10000)],
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, data):
    Path(path).write_text(json.dumps(data, indent=2, allow_nan=False) + '\n')


def convert_ms(text, length=LENGTH, bin_size=BIN, expected=RECORDS):
    """Standard ms, exactly two haplotypes, decimal positions without float bin drift."""
    chunks = text.split('\n//\n')[1:]
    if len(chunks) != expected:
        raise ValueError(f'expected {expected} ms replicates, got {len(chunks)}')
    result = []
    for i, chunk in enumerate(chunks):
        lines = [line.strip() for line in chunk.splitlines() if line.strip()]
        if not lines or not lines[0].startswith('segsites: '):
            raise ValueError('missing segregating-site count')
        sites = int(lines[0].split(':')[1])
        bins = bytearray(b'T' * ((length + bin_size - 1) // bin_size))
        if sites:
            if len(lines) != 4 or not lines[1].startswith('positions: '):
                raise ValueError('expected positions and exactly two haplotypes')
            positions = [Decimal(p) for p in lines[1].split()[1:]]
            hap1, hap2 = lines[2:]
            if len(positions) != sites or len(hap1) != sites or len(hap2) != sites:
                raise ValueError('site/haplotype length mismatch')
            if set(hap1 + hap2) - {'0', '1'} or positions != sorted(positions):
                raise ValueError('invalid haplotypes or unsorted positions')
            for pos, a, b in zip(positions, hap1, hap2):
                if not pos.is_finite() or not 0 <= pos <= 1:
                    raise ValueError('position outside sequence')
                if a != b:
                    base = min(length - 1, int(pos * length))
                    bins[base // bin_size] = ord('K')
        elif len(lines) != 1:
            raise ValueError('unexpected zero-site payload')
        result.append(f'>ms-{i+1}\n' + '\n'.join(bins[j:j+60].decode() for j in range(0,len(bins),60)) + '\n')
    return ''.join(result)


def curve(text):
    rounds = [int(l.split()[1]) for l in text.splitlines() if l.startswith('RD\t')]
    if rounds != list(range(31)):
        raise ValueError('expected complete N30 output')
    pa = [l.split()[1:] for l in text.splitlines() if l.startswith('PA\t')][-1]
    pattern, *values = pa
    theta, rho, max_t, *lambdas = map(float, values)
    if any(not math.isfinite(x) or x <= 0 for x in [theta,rho,max_t,*lambdas]):
        raise ValueError('nonfinite/nonpositive final parameters')
    groups = []
    for part in pattern.split('+'):
        n, width = map(int, part.split('*')) if '*' in part else (1,int(part))
        groups.extend([width]*n)
    if len(groups) != len(lambdas):
        raise ValueError('PA group mismatch')
    n0 = theta / (4*MU*BIN)
    beta = math.log1p(max_t / .1) / (sum(groups)-1)
    starts, count = [], 0
    for width in groups:
        starts.append(.1 * math.expm1(beta * count) * 2*n0)
        count += width
    logs = [math.log(n0*lambdas[max(0,bisect_right(starts,t)-1)]) for t in GRID]
    return logs, {'theta': theta, 'rho': rho, 'n0': n0, 'max_t': max_t,
                  'group_starts_generations': starts, 'lambdas': lambdas}


def numerical(text):
    return ''.join(l for l in text.splitlines(keepends=True) if not l.startswith('MM\tVersion:'))


def rmse(a,b):
    return math.sqrt(statistics.mean((x-y)**2 for x,y in zip(a,b)))


def run(command, base):
    start = time.monotonic()
    with base.with_suffix('.out').open('w') as out, base.with_suffix('.stderr').open('w') as err:
        subprocess.run(command, cwd=base.parent, stdout=out, stderr=err, check=True, timeout=600)
    return {'command': list(map(str,command)), 'seconds': time.monotonic()-start,
            'output_sha256': sha(base.with_suffix('.out'))}


def case(name, index, out, ms, reference, rust, history_script):
    folder = out / f'{name}-{index:02}'
    folder.mkdir()
    try:
        history = HISTORIES[name]
        history_file = folder / 'truth.history'
        history_file.write_text('T 0.1\nR 0.02\n' + ''.join(f'H {t/20000:.12g} {n/10000:.12g}\n' for t,n in history))
        emitted = subprocess.check_output(['perl',str(history_script),'-L',str(LENGTH),'-r',str(RECORDS),'-u',str(MU),str(history_file)],text=True).strip()
        parts = shlex.split(emitted)
        if parts[0] != 'msHOT-lite' or parts.count('-l') != 1:
            raise ValueError('unexpected history2ms command')
        parts = [str(ms)] + [p for p in parts[1:] if p != '-l']
        # Disjoint deterministic 16-bit seed triples; no implicit seedms file.
        offset = list(HISTORIES).index(name)*REPLICATES+index
        seeds = [1201+offset*73, 2309+offset*137, 3407+offset*193]
        parts += ['-p','12','-seeds',*map(str,seeds)]
        simulation = run(parts, folder/'simulation')
        encoded = folder / 'input.psmcfa'
        encoded.write_text(convert_ms((folder/'simulation.out').read_text()))
        fitted, runs = {}, {}
        for mode in ['c','strict','equivalent']:
            cmd = [str(reference),*FIT] if mode == 'c' else [str(rust),'--mode',mode,'--record-workers','1',*FIT]
            runs[mode] = run([*cmd,str(encoded)], folder/mode)
            fitted[mode] = (folder/f'{mode}.out').read_text()
        curves, params = {}, {}
        for mode, text in fitted.items():
            curves[mode], params[mode] = curve(text)
        true_logs = [math.log(history[max(0,bisect_right([x[0] for x in history],t)-1)][1]) for t in GRID]
        record = {'history':name,'index':index,'status':'complete','history2ms_command':emitted,
                  'seeds':seeds,'simulation':simulation,'input_sha256':sha(encoded),'runs':runs,
                  'strict_c_exact':numerical(fitted['strict']) == numerical(fitted['c']),
                  'rmse':{m:rmse(v,true_logs) for m,v in curves.items()},
                  'mode_curve_rmse':rmse(curves['strict'],curves['equivalent']),
                  'parameters':params,'log_curves':curves,'truth_log_curve':true_logs}
    except Exception as e:
        record = {'history':name,'index':index,'status':'failed','error':str(e)}
    save(folder/'result.json',record)
    return record


def summarize(records):
    summaries = {}
    for name in HISTORIES:
        selected = [r for r in records if r['history']==name]
        good = [r for r in selected if r['status']=='complete']
        if len(good) != REPLICATES:
            summaries[name] = {'passed':False,'complete':len(good),'planned':REPLICATES}
            continue
        differences = [r['rmse']['equivalent']-r['rmse']['strict'] for r in good]
        upper = statistics.mean(differences) + 1.833112933*statistics.stdev(differences)/math.sqrt(REPLICATES)
        pooled_error = math.sqrt(statistics.mean(r['rmse']['strict']**2 for r in good))
        pooled_difference = math.sqrt(statistics.mean(r['mode_curve_rmse']**2 for r in good))
        summaries[name] = {'complete':len(good),'mean_rmse':{m:statistics.mean(r['rmse'][m] for r in good) for m in ['c','strict','equivalent']},
                           'mean_paired_rmse_difference':statistics.mean(differences),
                           'upper_95_paired_rmse_difference':upper,
                           'pooled_mode_difference_over_truth_error':pooled_difference/pooled_error,
                           'strict_c_exact':all(r['strict_c_exact'] for r in good),
                           'passed':upper < .05 and pooled_difference <= .1*pooled_error and all(r['strict_c_exact'] for r in good)}
    return summaries


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ms',required=True,type=Path)
    p.add_argument('--reference',required=True,type=Path)
    p.add_argument('--rust',default=ROOT/'target/release/psmc-rs',type=Path)
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--jobs',type=int,default=4)
    args=p.parse_args()
    out=args.output.resolve()
    out.mkdir(parents=True,exist_ok=False)
    ms,reference,rust = [x.resolve() for x in [args.ms,args.reference,args.rust]]
    history_script=ROOT/'work/vanilla/utils/history2ms.pl'
    metadata={'protocol_sha256':sha(ROOT/'docs/known-truth-protocol.md'),
              'runner_sha256':sha(Path(__file__)), 'binaries':{str(x.relative_to(ROOT)):sha(x) for x in [ms,reference,rust]},
              'history_script_sha256':sha(history_script),'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
              'working_diff_sha256':hashlib.sha256(subprocess.check_output(['git','diff'],cwd=ROOT)).hexdigest(),
              'grid_generations':GRID,'histories':HISTORIES,'jobs':args.jobs,
              'fit_args':FIT,'length':LENGTH,'records':RECORDS,'replicates':REPLICATES}
    save(out/'frozen.json',metadata)
    records=[]
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures=[pool.submit(case,name,i,out,ms,reference,rust,history_script) for name in HISTORIES for i in range(REPLICATES)]
        for future in as_completed(futures):
            r=future.result(); records.append(r)
            print(r['history'],r['index'],r['status'],r.get('error',''),flush=True)
    records.sort(key=lambda r:(r['history'],r['index']))
    summary=summarize(records)
    report={'metadata':metadata,'summary':summary,'passed':all(s['passed'] for s in summary.values()),'cases':records,
            'scope':'20 Mb idealized independent-sequence pilot; actual whole-genome qualification not_run'}
    save(out/'report.json',report)
    print(json.dumps(summary,indent=2),flush=True)
    raise SystemExit(0 if report['passed'] else 1)


if __name__=='__main__':
    main()

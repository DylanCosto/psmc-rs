#!/usr/bin/env python3
"""Predeclared length/state/missingness coverage; never select inputs by timing."""
import datetime as dt
import json
import os
from pathlib import Path
import random
import subprocess
from common import ROOT, draw_bootstrap, nonfinite_records, read_fasta, save, sha256, write_fasta
from phase1_differential import compare_output
from phase2_common import clean_env, verify_binaries
from phase3_common import resource_policy


def main():
    os.chdir(ROOT)
    policy = resource_policy()
    directory = Path('tests/fixtures/cpu-campaign')
    directory.mkdir(exist_ok=True)
    rng = random.Random(20261010)
    records = []
    for index, length in enumerate([12000, 16373, 21627]):
        seq = ''.join('N' if 450 <= i % 1600 < 520 else
                      'K' if rng.random() < (0.025 if (i // 500) % 2 else 0.08) else 'T'
                      for i in range(length))
        records.append((f'campaign_{index}', seq))
    input_path = directory / 'mixed-50000.psmcfa'
    write_fasta(input_path, records)
    split_command = ['work/vanilla/utils/splitfa', str(input_path), '4000']
    split = subprocess.run(split_command, capture_output=True, check=True)
    blocks_path = directory / 'blocks-4000.psmcfa'
    blocks_path.write_bytes(split.stdout)
    blocks = read_fasta(blocks_path)
    # Dense missingness and long records broaden coverage without changing inference settings.
    masked = [(name + '_masked', ''.join('N' if 1000 <= i % 2000 < 1700 else c for i, c in enumerate(seq))) for name, seq in records]
    masked_path = directory / 'masked-50000.psmcfa'
    write_fasta(masked_path, masked)
    long_path = directory / 'long-200000.psmcfa'
    write_fasta(long_path, [('one_long_record', ''.join(seq for _, seq in records) * 4)])
    reps = []
    for index in range(30):
        seed = 20261010 + index
        indices, draws = draw_bootstrap(blocks, seed)
        path = directory / f'bootstrap-{index:02}.psmcfa'
        write_fasta(path, [blocks[i] for i in indices])
        reps.append(dict(id=index, seed=seed, indices=indices, draws=draws, file=str(path), sha256=sha256(path)))
    manifest = dict(schema_version=1, source='synthetic only, no biological input',
        generator_seed=20261010, generator_sha256=sha256(__file__), rng='Python random.Random; stored bytes/hashes canonical',
        design='50,000 bins, three unequal records, alternating heterozygosity and contiguous masks; 4,000-bin upstream splitting; 30 consecutive fixed seeds. Chosen before timing or fit results. All outcomes retained.',
        records=[dict(name=n, bins=len(s), heterozygous=s.count('K'), missing=s.count('N')) for n,s in records],
        split_command=split_command, blocks=[dict(name=n,bins=len(s)) for n,s in blocks],
        inputs={str(p):sha256(p) for p in [input_path, blocks_path, masked_path, long_path]}, replicates=reps)
    save(directory / 'manifest.json', manifest)
    profile = json.loads(Path('bench/cpu-campaign-profile.json').read_text())
    provenance = profile['provenance']
    verify_binaries(provenance)
    raw = Path('bench/cpu-campaign-fixtures') / dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    raw.mkdir(parents=True)
    patterns = [('k4', '2+2'), ('k23', '4+5*3+4'), ('k64', '4+25*2+4+6')]
    cases = [dict(id=f'{label}-mixed-n30', input=str(input_path), pattern=p, rounds=30) for label,p in patterns]
    cases += [dict(id='k23-masked-n30', input=str(masked_path), pattern=patterns[1][1], rounds=30),
              dict(id='k64-long-n1', input=str(long_path), pattern=patterns[2][1], rounds=1)]
    cases += [dict(id=f'bootstrap-{r["id"]:02}-k23-n30', input=r['file'], pattern=patterns[1][1], rounds=30) for r in reps]
    results = []
    for case in cases:
        runs = []
        expected = None
        for label in ['vanilla', 'phase3a']:
            output = raw / f'{case["id"]}-{label}.psmc'
            binary = provenance['binaries'][label]['path']
            extra = ['--backend', 'cpu', '--simd', 'auto', '--seed', '42'] if label == 'phase3a' else []
            command = [binary, *extra, '-o', str(output), '-p', case['pattern'], '-N', str(case['rounds']), '-t', '15', '-r', '4', '-I', '0', case['input']]
            result = subprocess.run(command, capture_output=True, env=clean_env())
            (raw / f'{case["id"]}-{label}.stderr').write_bytes(result.stderr)
            assert result.returncode == 0, case['id']
            data = output.read_bytes()
            if expected is None: expected = data
            else: compare_output(expected, data)
            runs.append(dict(label=label, command=command, output=str(output), sha256=sha256(output),
                             nonfinite=nonfinite_records(data.decode())))
        results.append(dict(**case, input_sha256=sha256(case['input']), runs=runs, exact_output_match=True,
                            finite=not runs[0]['nonfinite']))
        print(json.dumps(dict(case=case['id'], finite=results[-1]['finite'], exact_output_match=True)), flush=True)
    verify_binaries(provenance)
    save('bench/cpu-campaign-fixtures.json', dict(status='passed', resource_policy=policy, provenance=provenance,
         manifest=str(directory / 'manifest.json'), manifest_sha256=sha256(directory / 'manifest.json'),
         raw_directory=str(raw), cases=results, finite_cases=sum(r['finite'] for r in results),
         finite_bootstraps=sum(r['finite'] for r in results if r['id'].startswith('bootstrap')),
         limitations=['Synthetic correctness coverage only; no speedup measurement.', 'Any nonfinite cases remain recorded and are not scientific inference validation.', 'Long K64 case is one iteration, not complete convergence; other cases use all 30 rounds.']))


if __name__ == '__main__':
    main()

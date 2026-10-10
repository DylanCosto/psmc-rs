#!/usr/bin/env python3
"""Generate a model-based synthetic cohort from pinned C probabilities, not timings."""
import bisect
import datetime as dt
import itertools
import json
import math
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
    directory = Path('tests/fixtures/cpu-campaign-hmm')
    directory.mkdir(exist_ok=True)
    parameter = directory / 'generating.par'
    parameter.write_text('4+5*3+4 0.06 0.015 15 1 0.75 1.25 2 1.5 0.8 1.1\n')
    snapshot = directory / 'generating-model.jsonl'
    binary = Path('work/instrumented/psmc')
    assert sha256(binary) == '2b4bd7dd369ee8fc226270b30bd414a031314fd70445bd5d7a83d4e5d2f2ed55'
    cmd = [str(binary), '-N','0','-i',str(parameter),'tests/fixtures/tiny.psmcfa']
    result = subprocess.run(cmd, env={**clean_env(),'PSMC_SEED':'42','PSMC_SNAPSHOT':str(snapshot)},capture_output=True,check=True)
    (directory / 'generating-model.psmc').write_bytes(result.stdout)
    model, = [json.loads(line) for line in snapshot.read_text().splitlines() if json.loads(line)['event']=='model']
    def cumulative(probabilities):
        assert all(math.isfinite(p) and p >= 0 for p in probabilities)
        values = list(itertools.accumulate(probabilities))
        assert abs(values[-1] - 1.0) < 1e-12, values[-1]
        return values
    initial = cumulative(model['initial'])
    transitions = [cumulative(row) for row in model['transition']]
    emissions = [cumulative([model['emission'][b][k] for b in range(2)]) for k in range(model['states'])]
    rng = random.Random(20261011)
    def draw(cdf):
        choice = bisect.bisect_left(cdf,rng.random())
        assert choice < len(cdf)
        return choice
    records = []
    for index,length in enumerate([24000,32746,43254]):
        state = draw(initial)
        symbols = []
        for i in range(length):
            # As in khmm.c::hmm_simulate: transition, then emission at every site.
            state = draw(transitions[state])
            symbol = 'TK'[draw(emissions[state])]
            symbols.append('N' if 450 <= i % 1600 < 520 else symbol)
        records.append((f'psmc_model_synthetic_{index}', ''.join(symbols)))
    input_path = directory / 'model-100000.psmcfa'
    write_fasta(input_path,records)
    split_command = ['work/vanilla/utils/splitfa',str(input_path),'4000']
    split = subprocess.run(split_command,capture_output=True,check=True)
    blocks_path = directory / 'blocks-4000.psmcfa'
    blocks_path.write_bytes(split.stdout)
    blocks = read_fasta(blocks_path)
    reps = []
    for index in range(30):
        seed = 20261011 + index
        indices,draws = draw_bootstrap(blocks,seed)
        path = directory / f'bootstrap-{index:02}.psmcfa'
        write_fasta(path,[blocks[i] for i in indices])
        reps.append(dict(id=index,seed=seed,indices=indices,draws=draws,file=str(path),sha256=sha256(path)))
    manifest = dict(schema_version=1, source='Model-based synthetic only; no biological samples',
        reason='Separate coverage after heterogeneous Bernoulli fixtures reproduced frequent vanilla nonfinite fits; all earlier fixtures retained.',
        generator_seed=20261011, generator_sha256=sha256(__file__), rng='Python random.Random, stored bytes/hashes canonical',
        design='100,000 bins in three unequal independent records; fixed seven-group generating demography; mask spans imposed after sampling; all 30 consecutive bootstrap seeds retained regardless of outcome; no timing-based selection.',
        model_command=cmd, model_binary_sha256=sha256(binary), model_sha256=sha256(snapshot),
        parameters_sha256=sha256(parameter), model_note='Probabilities from pinned instrumented C at zero EM rounds; simulation loop follows transition-before-emission semantics of C hmm_simulate, with independently specified RNG.',
        records=[dict(name=n,bins=len(s),heterozygous=s.count('K'),missing=s.count('N')) for n,s in records],
        input=str(input_path), input_sha256=sha256(input_path), split_command=split_command,
        blocks_sha256=sha256(blocks_path), replicates=reps)
    save(directory/'manifest.json',manifest)
    provenance = json.loads(Path('bench/cpu-campaign-profile.json').read_text())['provenance']
    verify_binaries(provenance)
    raw = Path('bench/cpu-campaign-fixtures') / ('hmm-' + dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    raw.mkdir(parents=True)
    cases = [dict(id='hmm-unsplit-k23-n30',input=str(input_path))]
    cases += [dict(id=f'hmm-bootstrap-{r["id"]:02}-k23-n30',input=r['file']) for r in reps]
    results = []
    for case in cases:
        runs = []
        expected = None
        for label in ['vanilla','phase3a']:
            output = raw/f'{case["id"]}-{label}.psmc'
            extra = ['--backend','cpu','--simd','auto','--seed','42'] if label=='phase3a' else []
            command = [provenance['binaries'][label]['path'],*extra,'-o',str(output),'-p','4+5*3+4','-N','30','-t','15','-r','4','-I','0',case['input']]
            run = subprocess.run(command,env=clean_env(),capture_output=True)
            (raw/f'{case["id"]}-{label}.stderr').write_bytes(run.stderr)
            assert run.returncode==0
            data = output.read_bytes()
            if expected is None: expected=data
            else: compare_output(expected,data)
            runs.append(dict(label=label,command=command,output=str(output),sha256=sha256(output),nonfinite=nonfinite_records(data.decode())))
        results.append(dict(**case,input_sha256=sha256(case['input']),runs=runs,exact_output_match=True,finite=not runs[0]['nonfinite']))
        print(json.dumps(dict(case=case['id'],finite=results[-1]['finite'],exact_output_match=True)),flush=True)
    verify_binaries(provenance)
    save('bench/cpu-campaign-hmm-fixtures.json',dict(status='passed',resource_policy=policy,provenance=provenance,
         raw_directory=str(raw),manifest=str(directory/'manifest.json'),manifest_sha256=sha256(directory/'manifest.json'),
         cases=results,finite_cases=sum(r['finite'] for r in results),finite_bootstraps=sum(r['finite'] for r in results[1:]),
         limitations=['Synthetic finite/pathological counts reported separately; no speed or real-workload validation claim.']))


if __name__=='__main__': main()

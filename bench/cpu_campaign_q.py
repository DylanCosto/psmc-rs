#!/usr/bin/env python3
"""Screen strict Q candidates in disposable trees, sequentially on one CPU."""
import datetime as dt
import json
import os
from pathlib import Path
import resource
import shutil
import statistics
import subprocess
import time
from common import ROOT, save, sha256
from phase1_differential import compare_output
from phase2_common import clean_env, source_hashes, verify_binaries
from phase3_common import resource_policy


def main():
    os.chdir(ROOT)
    policy = resource_policy()
    before = source_hashes()
    profile = json.loads(Path('bench/cpu-campaign-profile.json').read_text())
    provenance = profile['provenance']
    verify_binaries(provenance)
    stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    raw = Path('bench/cpu-campaign-q') / stamp
    raw.mkdir(parents=True)
    env = clean_env()
    env.update(CARGO_BUILD_JOBS='1', RUST_TEST_THREADS='1', CARGO_NET_OFFLINE='true')
    assert not any(env.get(k) for k in ['RUSTFLAGS', 'CARGO_ENCODED_RUSTFLAGS', 'CARGO_TARGET_DIR', 'RUSTC_WRAPPER'])
    assert not any(k.startswith('CARGO_PROFILE_') and v for k,v in env.items())
    binaries = {'phase3a': provenance['binaries']['phase3a']}
    for label, mode in [('flat', 0), ('last', 1), ('direct', 2)]:
        scratch = ROOT / 'work' / f'cpu-q-{stamp}-{label}'
        scratch.mkdir()
        for name in ['Cargo.toml', 'Cargo.lock', 'rust-toolchain.toml']:
            shutil.copy2(name, scratch / name)
        shutil.copytree('crates', scratch / 'crates')
        if Path('.cargo').exists(): shutil.copytree('.cargo', scratch / '.cargo')
        path = scratch / 'crates/psmc-cpu/src/q_candidate.rs'
        path.write_text(Path('bench/cpu_campaign_q.rs').read_text().replace('const MODE: usize = 0;', f'const MODE: usize = {mode};'))
        path = scratch / 'crates/psmc-cpu/src/lib.rs'
        path.write_text(path.read_text() + '\nmod q_candidate;\n')
        path = scratch / 'crates/psmc-cpu/src/engine.rs'
        text = path.read_text()
        patches = [
            ('    workspace: Workspace,', '    workspace: Workspace,\n    q_cache: std::cell::RefCell<crate::q_candidate::QCache>,'),
            ('            workspace: Workspace::with_simd(states, mode)?,', '            workspace: Workspace::with_simd(states, mode)?,\n            q_cache: std::cell::RefCell::new(crate::q_candidate::QCache::new(states)),'),
            ('    fn stats(&self) -> BackendStats {', '    fn q(&self, counts: &Counts, model: &Model) -> f64 {\n        self.q_cache.borrow_mut().q(counts, model)\n    }\n    fn stats(&self) -> BackendStats {'),
        ]
        for old,new in patches:
            assert text.count(old) == 1
            text = text.replace(old,new)
        path.write_text(text)
        command = ['cargo', 'build', '--release', '--locked', '--offline', '--jobs', '1']
        build = subprocess.run(command, cwd=scratch, env=env, capture_output=True, text=True)
        (raw / f'{label}.build.log').write_text((build.stdout + build.stderr).replace(str(ROOT), '${PROJECT}'))
        assert build.returncode == 0, label
        test = subprocess.run(['cargo','test','--release','--locked','--offline','--jobs','1','-p','psmc-cpu','q_candidate::tests','--','--test-threads=1'], cwd=scratch, env=env, capture_output=True, text=True)
        (raw / f'{label}.test.log').write_text((test.stdout + test.stderr).replace(str(ROOT), '${PROJECT}'))
        assert test.returncode == 0, label
        dest = raw / label
        shutil.copy2(scratch / 'target/release/psmc-rs', dest)
        dest.chmod(0o555)
        binaries[label] = dict(path=str(dest), sha256=sha256(dest), changes=patches,
                              source_hashes={str(p.relative_to(scratch)):sha256(p) for p in sorted((scratch/'crates').rglob('*.rs'))})
    cases = [
        dict(id='k23-n30', input='tests/fixtures/workload.psmcfa', pattern='4+5*3+4', rounds=30),
        dict(id='k64-n5', input='tests/fixtures/profile.psmcfa', pattern='4+25*2+4+6', rounds=5),
        dict(id='bootstrap-00-k23-n30', input='tests/fixtures/bootstrap/replicate-00.psmcfa', pattern='4+5*3+4', rounds=30),
    ]
    results = []
    for case in cases:
        runs = []
        expected = None
        for rep in range(6):
            labels = list(binaries)
            labels = labels[rep % len(labels):] + labels[:rep % len(labels)]
            for label in labels:
                output = raw / f'{case["id"]}-{rep}-{label}.psmc'
                command = [binaries[label]['path'], '--backend','cpu','--simd','auto','--seed','42','-o',str(output),'-p',case['pattern'],'-N',str(case['rounds']),'-t','15','-r','4','-I','0',case['input']]
                usage0 = resource.getrusage(resource.RUSAGE_CHILDREN)
                start = time.perf_counter()
                result = subprocess.run(command, env=env, capture_output=True)
                wall = time.perf_counter() - start
                usage1 = resource.getrusage(resource.RUSAGE_CHILDREN)
                cpu = (usage1.ru_utime-usage0.ru_utime) + (usage1.ru_stime-usage0.ru_stime)
                (raw / f'{case["id"]}-{rep}-{label}.stderr').write_bytes(result.stderr)
                assert result.returncode == 0
                data = output.read_bytes()
                if expected is None: expected = data
                else: compare_output(expected,data)
                runs.append(dict(label=label, rep=rep, warmup=rep==0, command=command,
                                 cpu_seconds=cpu, wall_seconds=wall, output_sha256=sha256(output)))
        summary = {}
        for label in binaries:
            measured = [r for r in runs if r['label']==label and not r['warmup']]
            summary[label] = {kind:dict(median=statistics.median(r[kind] for r in measured), minimum=min(r[kind] for r in measured), maximum=max(r[kind] for r in measured)) for kind in ['cpu_seconds','wall_seconds']}
        results.append(dict(**case, input_sha256=sha256(case['input']), runs=runs, summary=summary, exact_output_match=True))
        print(json.dumps(dict(id=case['id'], summary=summary)), flush=True)
    assert source_hashes() == before
    verify_binaries(provenance)
    for item in binaries.values(): assert sha256(item['path']) == item['sha256']
    shutil.copy2(__file__,raw/'runner.py')
    save('bench/cpu-campaign-q.json', dict(status='screened_not_promoted', resource_policy=policy,
         raw_directory=str(raw), provenance=provenance, binaries=binaries, cases=results,
         runner_sha256=sha256(__file__), candidate_source_sha256=sha256('bench/cpu_campaign_q.rs'),
         limitations=['Exploratory three-case output gate only; full isolated/internal/CLI/30-bootstrap gates required before promotion.',
                     'Shared-host repeated screening; CPU time reduces waiting sensitivity but not cache/frequency contention.',
                     'No peak RSS comparison in this screen; final benchmark must include RSS.']))


if __name__ == '__main__': main()

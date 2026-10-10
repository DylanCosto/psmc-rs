#!/usr/bin/env python3
"""Exact-output-checked CPU attribution in a disposable instrumented source copy."""
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess
from common import ROOT, save, sha256
from phase2_common import clean_env, freeze, source_hashes, verify_binaries
from phase3_common import resource_policy
from phase1_differential import compare_output


def main():
    os.chdir(ROOT)
    policy = resource_policy()
    before = source_hashes()
    stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    raw = Path('bench/cpu-campaign-profile') / stamp
    raw.mkdir(parents=True)
    scratch = ROOT / 'work' / ('cpu-profile-' + stamp)
    scratch.mkdir()
    for name in ['Cargo.toml', 'Cargo.lock', 'rust-toolchain.toml']:
        shutil.copy2(ROOT / name, scratch / name)
    shutil.copytree(ROOT / 'crates', scratch / 'crates')
    if (ROOT / '.cargo').exists():
        shutil.copytree(ROOT / '.cargo', scratch / '.cargo')
    provenance = freeze(raw / 'bin', {'phase3a': 'bin/psmc-rs-phase3a', 'vanilla': 'work/vanilla/psmc'})
    assert provenance['binaries']['phase3a']['sha256'] == '8e417125208343026d56bae1b540b058371e4a0e949ca148a73c696b217f637b'
    changes = []
    def inject(file, old, new):
        path = scratch / file
        text = path.read_text()
        assert text.count(old) == 1, (file, old)
        path.write_text(text.replace(old, new))
        changes.append(dict(file=file, old=old, new=new))
    module = 'crates/psmc-core/src/diagnostic_profile.rs'
    shutil.copy2(ROOT / 'bench/cpu_campaign_profile.rs', scratch / module)
    core = 'crates/psmc-core/src/lib.rs'
    inject(core, 'pub mod em;', 'pub mod diagnostic_profile;\npub mod em;')
    timer = 'psmc_core::diagnostic_profile'
    engine = 'crates/psmc-cpu/src/engine.rs'
    inject(engine, '        let prepared = self.workspace.prepare(model);', f'        let _timer = {timer}::Guard::new(0);\n        let prepared = self.workspace.prepare(model);')
    inject(engine, '        self.model_workspace.update(model, settings);', f'        let _timer = {timer}::Guard::new(2);\n        self.model_workspace.update(model, settings);')
    hmm = 'crates/psmc-core/src/hmm.rs'
    inject(hmm, '    pub fn q(&self, model: &Model) -> f64 {', '    pub fn q(&self, model: &Model) -> f64 {\n        let _timer = crate::diagnostic_profile::Guard::new(3);')
    inject(hmm, '    pub fn normalizer(&mut self) -> f64 {', '    pub fn normalizer(&mut self) -> f64 {\n        let _timer = crate::diagnostic_profile::Guard::new(4);')
    cpu = 'crates/psmc-cpu/src/lib.rs'
    inject(cpu, '    fn with_avx_layout(model: &\'a Model, avx: bool) -> Self {', f'    fn with_avx_layout(model: &\'a Model, avx: bool) -> Self {{\n        let _timer = {timer}::Guard::new(1);')
    inject(cpu, '    ) -> (&Messages, &Counts) {', f'    ) -> (&Messages, &Counts) {{\n        let diagnostic_start = {timer}::now();')
    checkpoints = [
        ('        let first_emission = &model.emission', 5),
        ('        for target in &mut messages.backward[length * n..] {', 6),
        ('        let mut backward_check = 0.0;', 7),
        ('        let counts = &mut self.counts;', 8),
    ]
    for token, section in checkpoints:
        inject(cpu, token, f'        {timer}::record({section}, diagnostic_start);\n        let diagnostic_start = {timer}::now();\n' + token)
    inject(cpu, '        (messages, counts)', f'        {timer}::record(9, diagnostic_start);\n        (messages, counts)')
    em = 'crates/psmc-core/src/em.rs'
    inject(em, '        let n = self.model.n;', '        let _timer = crate::diagnostic_profile::Guard::new(11);\n        let n = self.model.n;')
    # Do not count inside scalar libm wrappers: that perturbs the hot Q loop.
    # The earlier counted experiment is retained separately with its runner.
    cli = 'crates/psmc-cli/src/main.rs'
    inject(cli, 'fn main() {', f'fn main() {{\n    let timer = {timer}::Guard::new(10);\n    diagnostic_main();\n    drop(timer);\n    {timer}::dump();\n}}\n\nfn diagnostic_main() {{')
    save(raw / 'instrumentation.json', dict(injections=changes, module=module,
         module_sha256=sha256(scratch / module), note='Only disposable source copy modified.'))
    env = clean_env()
    env.update(CARGO_BUILD_JOBS='1', RUST_TEST_THREADS='1', CARGO_NET_OFFLINE='true')
    rejected = [k for k in env if env[k] and (k in ['RUSTFLAGS', 'CARGO_ENCODED_RUSTFLAGS', 'CARGO_TARGET_DIR', 'RUSTC_WRAPPER'] or k.startswith('CARGO_PROFILE_'))]
    assert not rejected, rejected
    command = ['cargo', 'build', '--release', '--locked', '--offline', '--jobs', '1']
    build = subprocess.run(command, cwd=scratch, env=env, capture_output=True, text=True)
    (raw / 'build.log').write_text((build.stdout + build.stderr).replace(str(ROOT), '${PROJECT}'))
    assert build.returncode == 0, 'See build.log'
    instrumented = scratch / 'target/release/psmc-rs'
    frozen = raw / 'bin/diagnostic'
    shutil.copy2(instrumented, frozen)
    frozen.chmod(0o555)
    cases = [
        dict(id='k23-n30', input='tests/fixtures/workload.psmcfa', args=['-p', '4+5*3+4', '-N', '30', '-t', '15', '-r', '4', '-I', '0']),
        dict(id='k64-n5', input='tests/fixtures/profile.psmcfa', args=['-p', '4+25*2+4+6', '-N', '5', '-t', '15', '-r', '4', '-I', '0']),
        dict(id='mixed-k64-n30', input='tests/fixtures/cpu-campaign/mixed-50000.psmcfa', args=['-p', '4+25*2+4+6', '-N', '30', '-t', '15', '-r', '4', '-I', '0']),
        dict(id='bootstrap-00-k23-n30', input='tests/fixtures/bootstrap/replicate-00.psmcfa', args=['-p', '4+5*3+4', '-N', '30', '-t', '15', '-r', '4', '-I', '0']),
    ]
    results = []
    for case in cases:
        outputs = []
        for label in ['vanilla', 'phase3a']:
            output = raw / f'{case["id"]}-{label}.psmc'
            binary = provenance['binaries'][label]['path']
            extra = ['--backend', 'cpu', '--simd', 'auto', '--seed', '42'] if label == 'phase3a' else []
            cmd = [binary, *extra, '-o', str(output), *case['args'], case['input']]
            result = subprocess.run(cmd, env=env, capture_output=True, text=True)
            (raw / f'{case["id"]}-{label}.stderr').write_text(result.stderr)
            assert result.returncode == 0
            outputs.append(output.read_bytes())
        compare_output(*outputs)
        runs = []
        for rep in range(3):
            base = raw / f'{case["id"]}-{rep}'
            profile = base.with_suffix('.cpu.json')
            output = base.with_suffix('.psmc')
            cmd = [str(frozen), '--backend', 'cpu', '--simd', 'auto', '--seed', '42', '-o', str(output), *case['args'], case['input']]
            result = subprocess.run(cmd, env={**env, 'PSMC_CPU_DIAGNOSTIC': str(profile)}, capture_output=True, text=True)
            base.with_suffix('.stderr').write_text(result.stderr)
            assert result.returncode == 0
            compare_output(outputs[0], output.read_bytes())
            data = json.loads(profile.read_text())
            runs.append(dict(command=cmd, profile=data, output_sha256=sha256(output)))
        medians = {key: statistics.median(r['profile']['sections'][key]['nanoseconds'] / 1e9 for r in runs) for key in runs[0]['profile']['sections']}
        results.append(dict(**case, input_sha256=sha256(case['input']), runs=runs, cpu_seconds_medians=medians, exact_output_match=True))
        print(json.dumps(dict(id=case['id'], cpu_seconds_medians=medians)), flush=True)
    assert source_hashes() == before
    verify_binaries(provenance)
    report = dict(status='passed', resource_policy=policy, provenance=provenance,
        instrumented_binary_sha256=sha256(frozen), raw_directory=str(raw), cases=results,
        runner_sha256=sha256(__file__), module_sha256=sha256('bench/cpu_campaign_profile.rs'),
        limitations=['Diagnostic instrumentation overhead is included; not a release speed benchmark.',
                    'Nested expectation/iteration/main scopes overlap; do not add inclusive and child scopes.',
                    'Workspace setup includes observation validation and resize/zeroing; preparation includes layout allocation.',
                    'Expectation residual includes hashing/cache, aggregation, observer and instrumentation; main residual includes parsing/output/startup inside main.',
                    'Log/exp counts include model, Q, likelihood and normalizer; no per-log timing claimed.',
                    'Hardware counters unavailable: perf_event_paranoid=4; no system settings changed.',
                    'Shared host; CPU time avoids descheduling time but not cache/frequency contention.'])
    report['math_calls_instrumented'] = False
    shutil.copy2(__file__, raw / 'runner.py')
    save('bench/cpu-campaign-final-profile.json', report)


if __name__ == '__main__':
    main()

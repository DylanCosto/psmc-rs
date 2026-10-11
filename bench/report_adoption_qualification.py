#!/usr/bin/env python3
"""Summarize independently audited qualification; never convert missing checks to passes."""
import hashlib
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text())


def distribution(values):
    values = sorted(values)
    if not values:
        return dict(n=0, median=None, p95=None, maximum=None, values=[])
    h = (len(values) - 1) * .95
    lo = int(h)
    hi = min(lo + 1, len(values) - 1)
    return dict(n=len(values), median=statistics.median(values),
                p95=values[lo] + (values[hi] - values[lo]) * (h - lo),
                maximum=max(values), values=values)


def main():
    result_path = ROOT / 'bench/adoption-qualification-results.json'
    audit_path = ROOT / 'bench/adoption-qualification-audit.json'
    results, audit = read(result_path), read(audit_path)
    assert audit['integrity_passed'] and audit['independent_screens_verified']
    assert len(results['bootstrap_pairs']) == 30
    distributions = {}
    pairs = results['bootstrap_pairs']
    for band in ['recent', 'primary_early', 'primary_late', 'ancient']:
        for field in ['rms', 'max']:
            distributions[f'{band}_{field}_log_ne'] = distribution([
                pair['comparison']['bands'][band][field] for pair in pairs])
        distributions[f'{band}_maximum_fraction_of_sd'] = distribution([
            pair['uncertainty_max_ratio'][band] for pair in pairs
            if pair['uncertainty_max_ratio'][band] is not None])
    for field in ['theta_relative', 'rho_relative', 'legacy_lk_per_bin']:
        distributions[field] = distribution([pair['comparison'][field] for pair in pairs])
    summary = dict(source_commit=results['frozen']['commit'],
                   results_sha256=hashlib.sha256(result_path.read_bytes()).hexdigest(),
                   audit_sha256=hashlib.sha256(audit_path.read_bytes()).hexdigest(),
                   percentile_method='linear interpolation at (n-1)*0.95; medians use middle pair mean',
                   distributions=distributions,
                   exploratory_screen_passes=sum(p['comparison']['exploratory_screen'] for p in pairs),
                   diagnostics_required=results['diagnostic_required'],
                   historical_failures_retained=True)
    diagnostic_path = ROOT / 'bench/adoption-likelihood-diagnostics.json'
    diagnostics = read(diagnostic_path) if diagnostic_path.exists() else None
    required = set(results['diagnostic_required'])
    completed = set(d['index'] for d in diagnostics['pairs']) if diagnostics else set()
    summary['diagnostics_complete'] = required <= completed
    if diagnostics:
        assert diagnostics['campaign_report_sha256'] == audit['raw_report_sha256']
        summary['diagnostics_sha256'] = hashlib.sha256(diagnostic_path.read_bytes()).hexdigest()
    (ROOT / 'bench/adoption-qualification-summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False) + '\n')
    f = results['frozen']
    lines = [
        '# Broader production qualification — v0.8.0 candidate', '',
        'This is an implementation comparison and empirical bootstrap-uncertainty screen,',
        'not demographic ground truth or a controlled speed benchmark. Earlier pilot and',
        'whole-autosome scientific screen failures remain visible in their original reports.', '',
        f"Frozen source: `{f['commit']}`. Protocol SHA-256: `{f['protocol_sha256']}`.",
        f"Rust executable SHA-256: `{f['binary_hashes']['rust']}`.",
        'The stable-model prototype is excluded. The campaign ran locally on x86-64 Linux;',
        'native ARM CI regression success does not extend these scientific results to ARM.', '',
        '## Inputs, sampling and integrity', '',
        'HG001 comprises 22 autosomes, 28,750,027 bins at 100 bp/bin (2.875 Gb).',
        'Chromosome-preserving splitting produced 575 blocks under the pinned splitfa',
        '50,000-bin/short-tail rule. Thirty strict and thirty equivalent fits used matched',
        'seeds 20261011–20261040, 64 states (`4+25*2+4+6`), 30 iterations, t15/r5/I0.',
        'The independent audit reconstructs all block contents and all RNG draws, checks',
        'matching traces and completed-output hashes, and independently recomputes curves,',
        'screens and sample SDs. Input preparation has the original VCF-plus-callability',
        'ascertainment limitations; it is not a recommended demographic preparation pipeline.', '',
        '## Additional patterns and compiler controls', '',
        'The same exploratory screen was applied to C-FMA/C-O2 before interpreting',
        'equivalent/strict. A failed C control means that screen is not specific to a',
        'Rust implementation error for that case. No per-fit compiler-envelope gate is used.', '',
        '| Input | States | Strict/C exact | C compiler screen | Equivalent screen |',
        '|---|---:|---|---|---|',
    ]
    word = lambda flag: 'pass' if flag else '**fail**'
    for panel in results['additional_patterns']:
        states = 23 if panel['pattern'] == '4+5*3+4' else 32
        lines.append(f"| {panel['dataset']} | {states} | {word(panel['strict_c_exact'])} | {word(panel['compiler_control']['exploratory_screen'])} | {word(panel['equivalent_comparison']['exploratory_screen'])} |")
    lines += ['', 'Strict/C equality excludes only the version header and covers all rounds 0–30.',
              'There are only four C compiler controls. They do not measure a whole-genome',
              'bootstrap distribution of C compiler noise. Detailed metrics are retained in JSON.', '',
              '## Whole-genome differences across 30 bootstrap pairs', '',
              'Curves use fixed log-spaced grids (128 points per band), mutation rate 2.5e-8',
              'and 100 bp bins, with no time or height alignment. Values below are RMS natural-',
              'log Ne differences. The p95 interpolates linearly at index (n−1)×0.95.', '',
              '| Time band (generations) | Median RMS | p95 RMS | Maximum RMS | Maximum difference / strict bootstrap SD |',
              '|---|---:|---:|---:|---:|']
    for band, label in [('recent','1k–5k'),('primary_early','5k–20k (primary)'),('primary_late','20k–80k (primary)'),('ancient','80k–200k')]:
        d = distributions[f'{band}_rms_log_ne']
        ratio = results['uncertainty'][band]['max_ratio']
        ratio_text = f'{ratio:.6g}' if ratio is not None else 'undefined'
        lines.append(f"| {label} | {d['median']:.6g} | {d['p95']:.6g} | {d['maximum']:.6g} | {ratio_text} |")
    lines += ['', '| Scalar difference | Median | p95 | Maximum |', '|---|---:|---:|---:|']
    for key in ['theta_relative','rho_relative','legacy_lk_per_bin']:
        d=distributions[key]
        lines.append(f"| {key} | {d['median']:.6g} | {d['p95']:.6g} | {d['maximum']:.6g} |")
    lines += ['', f"Exploratory numerical screen: **{summary['exploratory_screen_passes']}/30 pass**.",
              'The fixed screen requires primary-band RMS ≤0.01, theta/rho relative differences',
              '≤0.001, finite trajectories and absolute printed LK difference/bin ≤1e-6.',
              'Printed LK is the legacy E-step likelihood, not a fresh evaluation at the final',
              'M-step parameters. The separate uncertainty bound is ≤10% of the strict sample',
              'bootstrap SD at every primary-band grid point. These are descriptive bounds,',
              'not hypothesis tests, confidence intervals or proof of demographic equivalence.', '']
    for band, values in results['uncertainty'].items():
        lines.append(f"- {band}: {values['undefined_ratios']} undefined difference/SD ratios (zero SD).")
    lines += ['', '## Flagged-fit diagnostics', '', f"Required pair indices: {results['diagnostic_required']}."]
    if summary['diagnostics_complete'] and not required:
        lines.append('No pair triggered the prospectively declared diagnostic rule.')
    elif summary['diagnostics_complete']:
        lines.append('Fresh final-parameter likelihood results are in [diagnostic evidence](../bench/adoption-likelihood-diagnostics.json); interpretations and any first-group slices require explicit review.')
    else:
        lines.append('**Pending:** fresh final-parameter likelihood diagnostics remain required. This report does not close the qualification gate.')
    lines += ['', '## Resources and fallback behavior', '',
              'Stages were sequential, low priority, under a 12 GiB address-space ceiling and',
              '512 MiB per-file limit. Bootstrap admission was 8192 MiB with up to 16 workers;',
              'both manifests admitted 16 pool workers (fit/helper roles are distinct).',
              'Additional Rust fits used at most four record workers and 4096 MiB admission.',
              'C additional-pattern fits had single-CPU affinity. Shared-host runtimes below',
              'are resource evidence, not a new speed comparison.', '',
              '| Stage | Elapsed seconds | Peak RSS MiB |', '|---|---:|---:|']
    stage_order = ['split', 'bootstrap-strict', 'bootstrap-equivalent'] + [
        f'{dataset}-{pattern}-{mode}' for dataset in ['hg001-chr22', 'hg002-chr1']
        for pattern in ['4+5x3+4', '8+8+8+8'] for mode in ['c-o2', 'c-fma', 'strict', 'equivalent']]
    for name in stage_order:
        run = results['runs'][name]
        lines.append(f"| {name} | {run['wall_seconds']:.2f} | {run['timing']['peak_rss_kib']/1024:.2f} |")
    if audit.get('preserved_preflight_pause'):
        lines += ['', 'The initial runner stopped after all 30 strict fits when available RAM failed',
                  'the next-stage 14 GiB preflight requirement. The original failure and strict',
                  'artifacts were preserved. An explicit continuation waited for the unchanged',
                  'floor and ran only the missing stages; no completed strict fit was rerun.',
                  'The audit checks the continuation source, preserved hashes and every recorded',
                  'continuation preflight. This interruption is part of the evidence.']
    lines += ['', f"Observed minimum available RAM: {audit['min_available_ram_gib']:.3f} GiB; minimum free disk: {audit['min_free_disk_gib']:.3f} GiB; maximum campaign size: {audit['max_campaign_gib']:.3f} GiB.",
              'The 4 GiB RAM / 25 GiB disk runtime floors and 2 GiB campaign cap were checked',
              'against all resource samples; 14 GiB available RAM was required before stages.', '']
    for mode,counters in audit['stats_totals'].items():
        lines.append(f"- Bootstrap {mode}: {counters['structured_fallbacks']} structured fallbacks / {counters['model_updates']} model updates.")
    equivalent = audit['stats_totals']['equivalent']
    lines += ['', f"Equivalent bootstrap fallbacks represent {100*equivalent['structured_fallbacks']/equivalent['model_updates']:.4f}% of model updates."]
    lines += ['', 'Additional-pattern per-fit counters, exact commands, output/timing hashes and',
              'source/binary identities are retained in the [results](../bench/adoption-qualification-results.json),',
              '[independent audit](../bench/adoption-qualification-audit.json) and',
              '[distribution summary](../bench/adoption-qualification-summary.json).',
              'Raw inputs and run artifacts remain local in ignored `work/adoption-qualification`.', '',
              '## Remaining limits', '',
              'Known-truth qualification is still limited to the earlier 64-state panel; these',
              '23/32-state comparisons do not establish demographic recovery for every pattern.',
              'There is no user-specific input pipeline validation, whole-genome ARM qualification',
              'or independent external-lab endorsement. The original 20 Mb pilot outliers and',
              'legacy cancellation/nonfinite behavior are not repaired or erased by this campaign.',
              'See the [frozen protocol](adoption-qualification-protocol.md) and',
              '[validation overview](validation-overview.md) for their distinct scopes.', '']
    (ROOT / 'docs/adoption-qualification-report.md').write_text('\n'.join(lines))
    print('Report written; diagnostics complete:', summary['diagnostics_complete'])


if __name__ == '__main__':
    main()

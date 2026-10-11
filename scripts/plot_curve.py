#!/usr/bin/env python3
"""Plot CSVs exported by psmc-rs. Requires matplotlib; no genomic upload."""
import argparse
import csv
import math
from pathlib import Path


def read_curve(path):
    with path.open(newline='') as source:
        rows = list(csv.DictReader(source))
    if not rows:
        raise ValueError(f'{path}: empty curve')
    units = {(row['mutation_rate'], row['bin_bp'], row['generation_years']) for row in rows}
    if len(units) != 1:
        raise ValueError(f'{path}: inconsistent scaling within a curve')
    times = [float(row['time_years']) for row in rows]
    sizes = [float(row['ne']) for row in rows]
    if any(not math.isfinite(v) or v < 0 for v in times) or any(not math.isfinite(v) or v <= 0 for v in sizes):
        raise ValueError(f'{path}: invalid curve')
    if any(b < a for a, b in zip(times, times[1:])):
        raise ValueError(f'{path}: unordered times')
    # Zero cannot appear on a logarithmic axis. The first interval starts at
    # the explicit positive display floor; do not discard its Ne estimate.
    return times, sizes, next(iter(units))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('main', type=Path)
    parser.add_argument('--bootstrap', type=Path, nargs='*', default=[])
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--min-years', required=True, type=float)
    parser.add_argument('--max-years', required=True, type=float)
    parser.add_argument('--title', default='PSMC population history')
    args = parser.parse_args()
    if not (math.isfinite(args.min_years) and math.isfinite(args.max_years) and 0 < args.min_years < args.max_years):
        parser.error('positive finite display limits required, min < max')
    if args.output.suffix.lower() not in {'.png', '.pdf', '.svg'}:
        parser.error('output must be PNG, PDF or SVG')
    if args.output.exists():
        parser.error('output already exists')
    main = read_curve(args.main)
    bootstraps = [read_curve(path) for path in args.bootstrap]
    if any(curve[2] != main[2] for curve in bootstraps):
        parser.error('main and bootstrap scaling must agree')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(8, 5), layout='constrained')
    def draw(curve, **kwargs):
        times, sizes, _ = curve
        # Include the last open interval to the stated display maximum. This
        # is a plotting boundary, not an inferred endpoint or new time grid.
        x = times + [max(times[-1], args.max_years)]
        ax.step(x, sizes + [sizes[-1]], where='post', **kwargs)
    for i, curve in enumerate(bootstraps):
        draw(curve, color='#8996a8', linewidth=0.8, alpha=0.55,
             label='Bootstrap fits' if i == 0 else None)
    draw(main, color='#175d91', linewidth=2, label='Main fit')
    ax.set(xscale='log', yscale='log', xlim=(args.min_years, args.max_years),
           xlabel='Years before present', ylabel='Effective population size (Ne)', title=args.title)
    ax.grid(True, which='major', alpha=0.2)
    ax.legend(frameon=False)
    fig.savefig(args.output, dpi=180)
    plt.close(fig)


if __name__ == '__main__':
    main()

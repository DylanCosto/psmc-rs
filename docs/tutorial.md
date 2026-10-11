# Five-minute local tutorial

Use a release archive's extracted directory, containing `psmc-rs`, `examples/`,
`scripts/` and this document. In a source checkout, build with `cargo build
--release --locked --offline`; use `target/release/psmc-rs` as `PSMC` and
`tests/fixtures/workload.psmcfa` as `INPUT` below.

This tiny synthetic fixture teaches the workflow, **not demographic recovery**.
Five iterations and three bootstrap replicates are for a quick demonstration,
not a recommended research analysis. No input is sent to an external service.

```sh
PSMC=./psmc-rs
INPUT=examples/synthetic.psmcfa
mkdir tutorial-run
"$PSMC" inspect "$INPUT"
"$PSMC" --seed 42 -N 5 --record-workers 2 --memory-mib 256 --progress \
  -o tutorial-run/main.psmc "$INPUT"
"$PSMC" split --block-bins 1000 --output tutorial-run/blocks.psmcfa "$INPUT"
"$PSMC" bootstrap --seed 42 -N 5 --replicates 3 --workers 2 \
  --memory-mib 256 --progress --output-dir tutorial-run/bootstrap \
  tutorial-run/blocks.psmcfa
```

Inspection reports encoded homozygous, heterozygous and missing bins. Input parsing
retains legacy PSMC aliases: unknown printable symbols become missing; inspection
is not a substitute for checking your upstream callable-site preparation.
Splitting uses **bins, not base pairs**. A 1,000-bin block at 100 bp/bin spans
100 kb. The pinned `splitfa` tail rule merges a remainder shorter than half a block,
without crossing original sequence boundaries. Output uses canonical T/K/N symbols.
For a research analysis choose the pattern, block length, iterations and bootstrap
count prospectively; preserve upstream input/callability provenance.

To resume an interrupted bootstrap, rerun its command with `--resume`. Use the
same binary, input, seed, model and fit options. Worker count, memory budget and
execution order may change. The runner verifies SHA-256 identities before reusing
completed fits. It starts unfinished fits from round zero and preserves their
partial files in `incomplete-*` directories. It does not resume midway through EM.
An exclusive Linux file lock prevents two writers; termination releases the lock.
Do not edit completion markers. A mismatch fails closed; use the original files
or a new output directory. See [resume contract](bootstrap-resume.md).

## Export and plot

The example assumes 100 bp per input bin, mutation rate 1.25e-8 per base per
generation and 25 years per generation. These are illustrative assumptions,
**not values estimated by PSMC**. Supply appropriate values for your data.

```sh
"$PSMC" export --mutation-rate 1.25e-8 --generation-years 25 --bin-bp 100 \
  --output tutorial-run/main.csv tutorial-run/main.psmc
for fit in tutorial-run/bootstrap/replicate-*.psmc; do
  "$PSMC" export --mutation-rate 1.25e-8 --generation-years 25 --bin-bp 100 \
    --output "${fit%.psmc}.csv" "$fit"
done
python3 -m venv tutorial-run/plot-env
tutorial-run/plot-env/bin/pip install matplotlib
tutorial-run/plot-env/bin/python scripts/plot_curve.py tutorial-run/main.csv \
  --bootstrap tutorial-run/bootstrap/replicate-*.csv \
  --min-years 100 --max-years 10000000 \
  --title 'Synthetic workflow demonstration' --output tutorial-run/curve.png
```

Python and Matplotlib are needed only for plotting. You can also plot the CSV
with your existing tools. Export selects the last complete round and warns if it
ignores a trailing incomplete round. It uses printed RS precision and upstream
scaling, including MM `skip` and DT; the CSV repeats the supplied units, round, source mode/version and source-file SHA-256.
Foreign or missing mode headers are labeled unspecified rather than guessed.
The figure displays individual bootstrap fits, not a confidence interval. It
extends the final open time interval to the requested display limit. The display
limits do not define a scientifically resolvable time range.

CPU inference defaults to equivalent f64 and emits QU rather than QD. Use
`--mode strict` on both fits and bootstrap for pinned-build C reproduction.
Report the version, mode, pattern, input preparation, and scaling in methods.

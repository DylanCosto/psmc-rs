# Four 20 Mb pilot outliers: shallow paths, not stationary ridges

2026-10-11. Base source ff46c7d; installed 0.7.0 engine unchanged. This post-hoc
investigation follows [the diagnostic protocol](pilot-ridge-protocol.md) and
preserves the original pilot failures. It does not revise a qualification gate.

The two modes occupy very similar observed-likelihood levels in all four cases.
After independently reconstructing the model in higher precision, the entire
33-point log-parameter path between each pair stays between its endpoint LLs:
there is no sampled likelihood barrier. That supports a weakly constrained
between-mode direction. It does **not** show that either endpoint has converged
to a stationary ridge: all four have independently confirmed improving directions.

| Original pilot case | Equivalent − strict LL | LL range along full path | LL gain after reducing strict lambda0 by factor e | Best selected strict coordinate gain |
|---|---:|---:|---:|---:|
| bottleneck-01 | +0.002101054 | 0.002101054 | +0.971088150 | +0.971088150 |
| bottleneck-03 | +0.000778861 | 0.000778861 | −0.000000561 | +0.054956569 |
| bottleneck-09 | −0.000614722 | 0.000614722 | +0.000000074 | +0.067810036 |
| expansion-09 | +0.004177858 | 0.004177858 | −0.000003350 | +0.087751295 |

These are observed LL, not Q values from different posteriors. The table uses
50-digit model construction rounded to f64 probabilities and the retained dense
f64 HMM. Increasing construction precision to 80 digits changes none of the eight
endpoint LLs at printed f64 precision. No universal significance cutoff is assumed.

## What the four cases show

Bottleneck-01 is different from the others. Its lambda0 is about 93, whereas
lambda1–lambda3 are approximately 0.5–5.8 million across the two fits. Reducing
lambda0 by factor e improves LL by about 0.971 in **both** modes. The between-mode
path is shallow, but the first-interval direction is not flat. Treating this case
as an unconstrained lambda0 plateau was incorrect.

Bottleneck-03, bottleneck-09 and expansion-09 have a pronounced lambda0 plateau:
multiplying or dividing lambda0 by e changes LL by no more than 3.35e-6 in any
of their six endpoint checks. This directly supports weak identification of that
parameter. However, reducing respectively lambda15, lambda2 and lambda5 by
exp(−0.1) improves strict LL by 0.0550, 0.0678 and 0.0878; equivalent endpoints
show similar gains. (Parameter-vector indices are 18, 5 and 8; lambda numbering
starts at zero.) These N30 fits are not stationary in all directions.

A bounded search over theta, rho and maximum time also improves literal LL along
each path: about 0.0138–0.0156, 0.0136–0.0139, 0.00462–0.00471 and
0.0682–0.0683 for the four cases. This is only a three-nuisance-parameter search,
with a nominal 128-call budget, not a converged full profile. Its results are
secondary because the literal model surface has numerical problems described below.
The search records actual calls, accepted offsets and explicit accepted-vector LL.

## An additional numerical problem in the legacy model equations

The initial literal-f64 screen produced 14, 1, 0 and 1 nonfinite LL values,
respectively. Two were interior path points in bottleneck-01. Finite LL alone
also did not guarantee valid probabilities: 11, 22, 19 and 24 of the 41 repeated
model constructions per case contained probabilities outside [0,1] or nonfinite
values under the literal formulas. These are **diagnostic perturbations**, not
counts of failed production fits or structured fallbacks.

The same equations contain differences of nearly equal quantities at large
lambda. Reconstructing them with Python Decimal at 50 digits removed the invalid
probabilities at all 164 checked points, without clipping or regularization.
The largest finite probability discrepancy was 0.00853. Nevertheless, endpoint
LL shifts from this correction were at most 4.12e-6, and the original small
between-mode differences persisted. This supports numerical cancellation in
model construction as an additional complication, not evidence that equivalent
inference is systematically worse.

The independent transcription agrees with the literal implementation on an
ordinary 64-state all-lambda=1 model to 3.33e-16 maximum probability error.
Probability normalization, stationary distribution and emission complements are
tested on ordinary and extreme synthetic parameters. Fifty- and eighty-digit
constructions round identically on those tests and all eight pilot endpoints.
The HMM remains f64; this is not an arbitrary-precision likelihood calculation.
No production model formulas or optimizer were changed.

## Evidence, resource use and reproducibility

[Compact evidence](../bench/pilot-surface-results.json) retains all 1,296 literal
screen records and 164 high-precision construction records, endpoint/input/binary
hashes, source hashes, commands, timing hashes, peak memory, nuisance offsets and
invalid-value counts. Nonfinite values are explicitly represented as JSON null;
raw local output hashes preserve the original records. Inputs and fit files were
checked against the original per-case manifests before use.

The four literal screens took 89.1–94.5 seconds each. The dense evaluations of
high-precision matrices took 3.62–3.78 seconds per case, excluding Python matrix
construction. Every evaluation process used one CPU and one record's message
history. Maximum measured child peak RSS was 17,204 KiB (16.8 MiB); this excludes
the Python controller/construction process. No simulations or whole-genome fits
were restarted. All 61 workspace tests pass, plus the diagnostic Rust test and
Python oracle test; four GPU hardware tests remain ignored. Hosted CI is pending
first GitHub publication.

Commands, from the repository root (use a fresh work/pilot-surface destination;
the runner refuses to overwrite its raw outputs):

```sh
cargo build --release -p psmc-cpu --example pilot_surface --example pilot_matrix_likelihood
python3 bench/pilot_surface.py
python3 bench/pilot_surface.py --decimal
python3 bench/pilot_surface_report.py
cargo test --release --locked --offline --workspace
cargo test --release --locked --offline -p psmc-cpu --example pilot_surface
python3 -m unittest discover -s bench -p 'test_pilot*.py'
```

Original raw inputs/results remain local under work/qualification/panel. The
initial literal run used the equivalent local runner saved in work/pilot-surface;
its original absolute commands are normalized to repository-relative paths in
the compact evidence. The committed runner adds the Decimal stage and documents
reproduction. This is not a new speed benchmark.

## Remaining limits and next permitted work

The original pilot's failed screens and poor recent-time truth recovery remain
visible. A finite sampled path does not prove continuity between sampled points,
full-profile flatness, global optimality, statistical equivalence or convergence.
Printed PA vectors are rounded; only these four selected 20 Mb datasets and the
64-state pattern were investigated, on x86-64 Linux. No new bootstrap uncertainty,
whole-genome qualification, ARM or GPU result is claimed.

The outliers now have direct evidence for shallow between-mode directions and,
in three cases, a lambda0 plateau. All four also show incomplete stationarity.
A stable equivalent-mode model-construction investigation is warranted separately,
with strict arithmetic preserved and fresh validation before adoption. A full
nuisance profile or longer diagnostic fits could assess convergence further;
neither is needed to label the present evidence honestly, and neither was run.

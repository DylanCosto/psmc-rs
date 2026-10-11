# Prospective 200 Mb known-truth panel

This protocol is frozen before any new panel simulation or fit. It follows the
20 Mb pilot and its post-hoc time-band review; it does not retroactively change
that pilot's gates. This is a 200 Mb panel, not a whole-human-genome claim.

## Fixed data and fitting design

Use the same pinned unmodified Hudson ms archive, compiler and standard-ms
converter as docs/known-truth-protocol.md. Each dataset now comprises twenty
independently simulated **10 Mb** diploid sequences: **200 Mb per dataset**,
100-base bins, no further splitting. Simulate ten datasets per history, thirty
datasets total, with disjoint deterministic seeds [11001+73*j, 22009+137*j,
33007+193*j] for j=0..29. Mutation rate is 2.5e-8/base/generation and recombination
rate is 5e-9/base/generation. No masks, errors, structure or selection.

- Constant: Ne 10,000 at all times.
- Bottleneck: Ne 10,000 until 10,000 generations ago, Ne 2,000 between
  10,000 and 30,000 generations ago, then Ne 10,000.
- Expansion: Ne 20,000 until 20,000 generations ago, then Ne 10,000.

Events sit inside the pilot's better-resolved 5,000–80,000-generation range.
This is an evidence-informed design choice, not a guarantee of identifiability.
Pinned PSMC history2ms.pl generates parameters; change only msHOT-lite's executable
and output switch as before. Preserve all seeds, commands, inputs and outputs.

Run vanilla C, Rust strict and equivalent on every dataset, with pattern
4+25*2+4+6, 30 iterations, max time 15, theta/rho 5, alpha 0.1 and initialization
amplitude zero. Same observations, model, optimizer and iteration count. Use
single-worker fits and up to eight independent processes; this panel measures
accuracy, not throughput. No fewer iterations or coarser states for C or strict.
All fitting outputs must match C exactly in strict mode except the version line.

## Time-band metrics and fixed gates

Reconstruct absolute Ne/time curves from the final PA fields exactly as in the
pilot. Each band has its own 128-point log-spaced grid, left-inclusive and
right-exclusive, avoiding double weighting boundaries:

| Band (generations) | Role |
|---|---|
| 1,000–5,000 | Recent diagnostic; explicitly not a qualification gate |
| 5,000–20,000 | Primary accuracy band |
| 20,000–80,000 | Primary accuracy band |
| 80,000–200,000 | Ancient diagnostic; explicitly not a qualification gate |

For each dataset, mode and band report RMS natural-log error versus true Ne,
mode-to-mode RMS log difference and maximum log difference. Also retain the
original full 1,000–200,000-generation pilot-grid metric for continuity. Never
omit poorly recovered windows from reporting.

For EACH history and EACH primary band:

1. Every final parameter vector must be finite and every strict/C output exact.
2. The upper one-sided 95% paired Student-t bound for the mean difference in
   error (equivalent minus strict) must be <0.05 natural-log units. Ten pairs,
   df=9, t critical 1.833112933. This relies on approximate normality and is not
   a simultaneous confidence statement across all bands/histories.
3. Pooled RMS mode difference must be <=10% of strict's pooled RMS truth error.
4. Mean truth-error RMSE must be <=0.5 log units in BOTH modes. This additional
   prospective descriptive accuracy budget prevents shared poor recovery from
   passing qualification solely through agreement. It is not a universal PSMC
   scientific accuracy standard.

Event recovery is a separate required qualitative check in both modes. Evaluate
128 left-inclusive/right-exclusive log points in each window; average log Ne
within a dataset and then take the median ratio across datasets:

- Bottleneck: Ne(12k–24k) / Ne(50k–80k) <0.75.
- Expansion: Ne(5k–10k) / Ne(40k–60k) >1.25.

These budgets and windows are fixed before simulation. Any failure stays a
failure; do not change windows, fit options, cases or tolerances to obtain a pass.
A global panel pass requires all primary-band and event checks. Report failures
and investigate them rather than silently selecting successful histories.

## Diagnostics and scope

For any dataset whose mode-to-mode RMS difference exceeds 0.01 in any band,
recompute fresh endpoint likelihoods and both common-count Q differences with
the strict engine. Retain lambda0-only slices as diagnostics, never as profile
likelihoods. Report absolute and per-bin differences; do not apply the prior
HG-panel common-Q budget as a new truth gate, and do not use a universal ΔLL=1
significance rule for these non-nested fitted curves. Small endpoint differences
are useful evidence about fit quality but do not by themselves identify a ridge.

Record finite failures, source/binary/protocol/runner hashes and commands. Process
failures remain explicit. Resume interrupted work only with unchanged frozen
inputs/configuration, retaining interrupted attempts. No speed claim from this
panel. Cgroup-aware strict admission remains active; an explicit memory override
cannot bypass it. Runtime sampling is diagnostic only.

Passing this panel supports these idealized histories, data volume, time bands
and execution stack. Whole-genome sequence dependence, real masks and the user's
input/splitting/command remain untested. Hosted CI still requires a remote URL.
Equivalent remains opt-in regardless of this panel's result.

# Four pilot outliers: likelihood geometry diagnostic

Written 2026-10-11 before the new surface evaluations. This is a post-hoc
investigation of bottleneck-01, bottleneck-03, bottleneck-09 and expansion-09,
selected by the existing 20 Mb pilot screen. It changes no qualification gate.

Use the original input and last printed PA vectors, with their saved hashes.
Evaluate observed log likelihood using the retained dense CPU messages in f64,
independently of the equivalent arithmetic. Check both endpoints with SIMD off.
Retain the original chromosome boundaries. Production inference is unchanged.

1. Evaluate the full log-parameter interpolation at t=-0.5 to 1.5 in 1/32 steps,
   preserving the exact original endpoint vectors at t=0 and t=1. Report interior
   maximum/minimum and the largest likelihood loss below the lower endpoint.
2. At each endpoint, vary every positive parameter separately by +/-0.01 and
   +/-0.1 in log space. Report improving directions and parameter sensitivities.
   Repeat the first lambda at +/-1 log unit to probe the large-lambda plateau.
3. On the same interpolation family, optimize nuisance log offsets for theta,
   rho and maximum time with the existing Hooke-Jeeves implementation at
   t=0,0.25,0.5,0.75,1. Start offsets at zero, radius 0.01, epsilon 1e-5,
   nominal maximum 128 calls; bound offsets to +/-0.25. Re-evaluate the accepted
   vector explicitly. Record actual calls and final offsets. This is a limited
   nuisance optimization, NOT a full profile likelihood or proof of convergence.
4. Compare the surface variation with floating-point repeatability and endpoint
   improvement. A connected shallow path supports a weakly constrained direction;
   it does not prove a stationary ridge or a global maximum. A barrier or sizeable
   endpoint improvements must be reported, not relabeled as success. Report
   absolute LL differences without inventing a universal significance threshold.

One process, one CPU worker, one chromosome message history at a time. Retain
only compact JSON and report in Git; inputs and raw outputs stay local. No new
simulations, bootstrap campaign, production optimization or acceptance relaxation.
A subsequent full nuisance profile is a separate study if this bounded diagnostic
cannot settle the interpretation. Record timings, memory, source and hashes.

## Diagnostic extension after initial evaluation

The first case has nonfinite dense LL at two interior path points and several
coordinate perturbations despite finite, positive parameters. This prevents a
literal-f64 surface from establishing continuous ridge geometry. Preserve all
failures. Before interpreting the remaining surfaces, independently reconstruct
the pinned model equations using Python Decimal at 50 significant digits, round
the resulting probabilities to f64, and evaluate with the SAME dense CPU HMM.
This is a diagnostic oracle, not a production change. Check 50 versus 80 digits
at both endpoints; validate ordinary synthetic parameters against Model::update.

Repeat the 33 interior path points, lambda0 +/-1, and each endpoint's strongest
finite improving coordinate from the original screen. Record probability validity
and deviations from literal construction. Do not silently replace the original
results. Higher-precision model construction still uses f64 HMM messages, and
these slices still do not constitute a full nuisance profile or convergence proof.

# Stable model construction: diagnostic protocol and derivation

Prospective protocol, 2026-10-11; production base 2092668. Strict and equivalent
production equations remain frozen. This milestone investigates an isolated Rust
example, not a new default arithmetic policy. All original failed screens remain.

## Algebra

Read against pinned core.c and crates/psmc-core/src/{model,structured}.rs.
For a nonterminal interval let a=alpha[k], x=tau/lambda, r=exp(-x), d=1-r,
and B=a*beta[k]. Instead of differences of inverse survivals, carry
`B_next = r*B + lambda*d`. The original quantities become:

- `q_aux = d*B + lambda*h`, h=x−d.
- `cpik = a*c`, c=d*t + lambda*g, g=d−x*r.
- diagonal numerator `a*v`, v=d²*B + lambda*j, j=1−r²−2*x*r.
- c_pi = sum(lambda*a*d).
- D=d/rho+c/2; rate=c/D; lower=d/D; upper=q_aux/(a*D).
- diagonal = (1−rate)+v/D; sigma = a*(d+rho*c/2)/(1+rho*c_pi/2).
- mean-time fallback = t+lambda*g/d; ordinary mean uses `-log1p(-rate)/rho`.

For the terminal state, the original convention alpha[n]=0 means d=1, r=0,
c=t+lambda, v=B+lambda. It is not exp(-terminal_tau/lambda).
Emissions use exp(-theta*(avg+dt)) and -expm1(-theta*(avg+dt)). No clipping,
renormalization, altered optimizer or demographic model is authorized.
The same time grid and final callback semantics are retained; a stable expm1/log1p
grid is an algebraic candidate only, with explicit-time inputs copied exactly.

Compute d with -expm1(-x). For small x, use convergent Taylor series:
`h=sum_{m>=2} (-1)^m*x^m/m!`,
`g=sum_{m>=2} (-1)^m*(m-1)*x^m/m!`,
`j=2*exp(-x)*sum_{m>=1} x^(2m+1)/(2m+1)!`.
Use series below x=0.5 for h/g and x=1 for j, at most 32 terms, stopping only
when the next term no longer changes the f64 sum. Away from zero use expm1
expressions. All series are f64; no reduced precision or fast-math.
Products may still underflow at extreme survival values, and the literal model
can be invalid outside a physical parameter region. Report these cases; do not
silently turn them into valid distributions. Diagnostic fits count any fallback
to literal construction. No production fallback changes in this milestone.

## Fixed gates and evidence

1. Compare Rust candidate probabilities to the existing independent 50-digit
   Decimal transcription (80 digits for selected extremes). Cover ordinary and
   extreme supplied lambda vectors, 6/23/64-state patterns, the original 164
   pilot diagnostic points, and deterministic parameter sweeps. For representable
   valid oracle models require absolute error <=1e-14 plus relative error <=1e-12
   (combined: abs <=1e-14+1e-12*abs(oracle)). Require all probabilities finite/in
   [0,1], row/initial normalization within1e-12 and stationary residual <=1e-12.
   Oracle domain/underflow failures are reported exclusions, not passes.
2. Evaluate the eight pilot endpoints using the retained dense f64 HMM, with
   candidate and Decimal probabilities. Require LL difference <=1e-8; record all
   input/parameter/matrix hashes. These fixed-parameter checks are not refits.
3. Run ten-round synthetic diagnostic fits for 6/23/64 states with literal and
   candidate construction, retaining optimizer/CPU counts and comparing final
   parameters, full callback/fallback counts, and independently evaluated LL.
   This is a behavior screen with all differences reported, not a scientific
   equivalence claim or a tuning exercise. Time both complete fits; no speed claim
   from a standalone construction microbenchmark.
4. Production workspace/C golden tests must still pass. Candidate code lives only
   in examples/support. Even component/diagnostic success does not authorize a
   new default before a separate full-fit scientific qualification. This milestone
   may conclude with a promising isolated candidate and explicit adoption deferred;
   broader release qualification then tests the frozen production engine.

Resource bounds: existing local/synthetic inputs; no simulations/downloads. One
fit/evaluation CPU, one record message history at a time, 4 GiB available RAM and
25 GiB disk floors for larger checks. Raw evidence in work/stable-model, compact
results in bench. Do not rerun cancelled simulations or change old reports/gates.

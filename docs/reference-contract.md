# PSMC reference contract — Phase 0 source audit

Audit date: 2026-10-09 (user's local date). Status: **reference contract and synthetic test scope; no Rust numerical backend exists or is certified**.

The reference is [`lh3/psmc`](https://github.com/lh3/psmc) at commit [`82fa2ada83ee463fe1251b562ae3d60e82d7ad6a`](https://github.com/lh3/psmc/tree/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a). All source links below identify that immutable commit. The binary's hard-coded version is `0.6.5-r74-dirty`; the word `dirty` is in the source and does not itself indicate local modifications. [Version constant](https://github.com/lh3/psmc/blob/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a/cli.c#L12-L13)

The attached plans are planning context. They do not supply missing user commands, establish measured performance, or authorize later implementation phases. The user has clarified that the 30 bootstraps **already run in parallel**, and has invited a recommendation about output requirements. Our recommendation is to preserve legacy PSMC inference and develop an equivalent accelerated path only after a written tolerance policy and differential validation. Exact printed-output parity remains a useful oracle target, not an asserted user requirement.

## 1. Scope and evidence boundary

| Scope | Phase 0 disposition |
|---|---|
| Pinned original C executable | External legacy reference; preserve all upstream files and licenses. |
| Plain/gzip FASTA-like PSMC input; ordinary non-divergence fitting | Primary compatibility target, with synthetic differential fixtures only at this stage. |
| Independent record boundaries, masked observations, parameter groups, supplied parameters, full counts, normalized Q, optimizer side effects | Audited below; each remains part of the compatibility contract. |
| Bootstrap block selection and record order | Audited; deterministic instrumentation/materialized inputs must record every repeated occurrence. |
| Real 30-bootstrap workload | `not_run`: actual input, commands, worker cap, block splitting, and provenance remain unavailable. Existing parallel execution is known. |
| Rust CPU, structured CPU, CUDA, cross-platform strict parity | `not_run`; no implementation or certification is claimed. |
| Decoding, probability output, simulation, CpG-count decoding, divergence and unusual supplied-grid combinations | Source-audited inventory below; outside the initial accelerated fit promise unless separately tested and explicitly promoted. Original C remains available for these flags. |
| BAM/VCF/gVCF/BCF ingestion; calling, masks, phased-assembly conversion | No new input adapter in Phase 0. Existing upstream preprocessing is audited, not replaced. |
| PHLASH/other methods | Alternative-method feasibility and prior art only; Bayesian/posterior output is not a legacy bootstrap result. |
| Pathological or malformed input | Do not reproduce crashes, out-of-bounds access, nontermination, or undefined behavior as a feature. A later parser may reject such cases explicitly; this does not authorize changing answers on accepted valid inputs. |

The runnable `bench/differential.json` test report and `bench/workload.json` fixture manifest are the authority for **what actually ran**; the instrumentation design and capture locations are documented in `reference/instrumentation.md`. Source audit alone is not a passing test. Complete stdout equality can also reproduce the original program's NaNs: the harness separately classifies nonfinite records outside the expected round-zero `RI`, and such pathology-parity cases do not certify finite scientific inference. Tiny synthetic fixtures verify mechanics, not whole-genome performance or biological validity. The supplied `algebra_check_results.json` reports generic semiseparable-HMM algebra; it explicitly did not validate the original parameter-to-matrix mapping, C binary, Rust/CUDA, EM trajectory, or real workload. Its tolerances must not silently become production acceptance tolerances.

Four documents referenced by the attachments were not supplied: `MATH_AND_COMPATIBILITY.md`, `VALIDATION_AND_BENCHMARKS.md`, `LONG_READ_ROADMAP.md`, and `SOURCES.md`. The current source audit does not reconstruct their unseen contents. In particular, a numerical-equivalence tolerance policy, complete derivations, and real-workload protocol still require review before an accelerated backend can be promoted.

### Executed Phase 0 coverage

The reviewed `bench/differential.json` run reports 52 passing harness checks: 17 complete-stdout C/instrumented-C fixture pairs, an alias equivalence check, a boundary negative control, 400 exact libc RNG-draw comparisons, 30 materialized bootstrap replay comparisons, one independent path/count/Q suite, and one instrumented random-initialization replay check. Explicit flag coverage includes `-p/-N/-t/-r/-I=0`, ordinary and explicit-grid `-i`, `-l`, `-T`, `-d/-D/-s`, `-d -C`, and `-b`; `-I=0.1` is checked for deterministic instrumented replay, not unmodified-C seed equality. File output via `-o`, `-c`, `-S`, stdin/FASTQ, malformed-input behavior, option interactions not listed, and full preprocessing edge cases are not certified by this suite.

A 23-state, 30-iteration unsplit synthetic workload was required to be finite outside the expected round-zero `RI` and passed exact stdout comparison. Several smaller pathological fixtures and 15 of the 30 four-state/two-iteration replay pairs reproduce nonfinite original-C records; diagnostics label them as pathology parity. They do not demonstrate successful finite inference. The separate 23-state, 30-round bootstrap benchmark has its own unresolved numerical-failure evidence, which is not superseded by the unsplit finite case. See `docs/harness-review.md` for independent review and corrections.

## 2. Compatibility modes

| Mode | Contract | Current status |
|---|---|---|
| `strict` | Numerical records match at original printed precision on a pinned executable/compiler/library/hardware stack; any excluded metadata is listed explicitly. Preserve iteration count, original optimizer behavior, bootstrap samples, boundaries, and output meanings. | Original C is the external oracle. No independent strict backend is certified. Universal cross-architecture byte identity is not promised. |
| `equivalent` | Same model, observation encoding, time grid rules, fitted parameters, initialization, full-count EM, objective normalizer, optimizer procedure, iterations, bootstrap samples, and outputs, with prespecified numerical tolerances and deterministic reductions. | Recommended eventual acceleration target. Not yet implemented, validated, or approved. |
| `research` | Different statistical or numerical procedure, including posterior inference, alternate optimizer/EM, changed emissions, lower precision, or new long-read model. | Separate method and evaluation; cannot be reported as this project's legacy speedup. |

Changing summation order may alter floating-point values and optimizer branch decisions even when algebra is exact. A faster implementation must compare matrices, per-sequence messages/counts, aggregate statistics, objective evaluations, optimizer calls, final parameters, and full EM trajectories. Similar plotted population curves alone are insufficient evidence.

## 3. Build and execution contract

The upstream Makefile compiles C objects with `gcc -g -Wall -O2 -Wno-unused-function`, empty `DFLAGS`, and links `-lm -lz`. The link rule uses `CCFLAGS` rather than `CFLAGS`; log the actual command, not just the intended flag variable. No upstream fast-math flag is enabled. `FLOAT` defaults to C `double` in both headers; optimizer arrays and callbacks are explicitly `double`. [Main Makefile](https://github.com/lh3/psmc/blob/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a/Makefile#L1-L16), [HMM precision/constants](https://github.com/lh3/psmc/blob/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a/khmm.h#L25-L29), [PSMC precision](https://github.com/lh3/psmc/blob/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a/psmc.h#L8-L14)

The actual Phase 0 reference adds explicit `-ffp-contract=off` and a debug-prefix mapping to upstream `-O2`, and links the installed `libz.so.1`; the complete tested commands, GCC 13.3.0 identity, glibc 2.39 identity, executable/library hashes, and extracted zlib header hashes are in `reference/build-vanilla.json`. This is an explicitly pinned compilation, not a claim about the user's original compiler settings.

The reproducibility bundle must record source commit and source digest, compiler identity, flags, libc/libm/zlib, architecture, OS, executable digest, locale, full argument vector, input digest, ordered records, seed/bootstrap manifest, and whether the executable is instrumented. Use the unmodified executable for timing; separate snapshots, deterministic RNG controls, and sampling-profile builds must be identified as instrumented. Do not attribute instrumented times to unmodified-reference throughput.

The exact user invocation is **unknown**. The README example is not the user's command: its `-N25 -t15 -r5 -p '4+25*2+4+6'` differs from several program defaults. [README example](https://github.com/lh3/psmc/blob/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a/README#L9-L14)

## 4. Complete `psmc` flag inventory

The literal getopt option string is `i:t:l:r:N:p:o:dI:c:bSDT:sC:`. There are **16 short options**, including hidden `-l` and `-I`. No explicit `-h`, `--help`, `--version`, seed option, worker option, or long-option parser exists. Unknown options or a missing positional input invoke usage and exit 1. The first remaining positional input is read; additional positional arguments are not consumed. [Parser and usage](https://github.com/lh3/psmc/blob/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a/cli.c#L34-L60), [option dispatch](https://github.com/lh3/psmc/blob/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a/cli.c#L172-L226)

| Flag | Default | Actual behavior | Initial accelerated fit scope |
|---|---|---|---|
| `-p STR` | `4+5*3+4` | Parse grouped atomic intervals; overridden by `-i` file's pattern. | Target. |
| `-t FLOAT` | `15` | Initial maximum-time parameter; this parameter is included in numerical optimization. Supplied parameters override it. | Target. |
| `-N INT` | `30` | Run exactly this many EM calls with loop `i != n_iters`; zero prints initial model. Negative values are unsafe/nonterminating and should be rejected later. | Target for nonnegative values. |
| `-r FLOAT` | `4` | Initial theta/rho ratio; sets initial rho from empirical theta. Supplied parameters override ratio. | Target for valid positive values. |
| `-l FLOAT` | `0.1` | Hidden option: log-grid offset `alpha`. Not a sequence-skipping option, despite obsolete comments. | Target if validated. |
| `-I FLOAT` | `0` | Hidden option: random initial lambda amplitude; each lambda is `1+(2U-1)*I`, floored at `0.1`. | Requires exact RNG replay; no silent nondeterministic parity promise. |
| `-i FILE` | none | Read raw pattern and parameter numbers; not an entire `.psmc` report. Optional explicit grid if third parameter is negative; optional divergence value has parser caveats. | Ordinary non-divergence parameter files targeted; other combinations separately gated. |
| `-o FILE` | stdout | Open/truncate output before reading input. Failure asserts. | Target; avoid overwriting inputs. |
| `-b` | off | Resample existing records with replacement to approach original total raw length; detailed stopping rule below. | Target through explicit ordered bootstrap manifests. |
| `-d` | off | After fitting, posterior decode each site and print constant-state segments; not Viterbi. | Audited; separate gate. |
| `-D` | off | Also enables `-d`; emit all posterior state probabilities per site. | Audited; separate gate. |
| `-s` | off | After fitting, print forward scale factors (`PR`), which take priority over `DC`/`DF` output. | Audited; separate gate. |
| `-c FILE` | none | Read native binary counts and run decoding to emit posterior-weighted `CT` counts even without `-d`. | Audited; excluded initially. |
| `-C INT` | `-1` | Only applied before decoding/probability/count pass, only if `0<C<n`; collapse each transition row's destinations `C..n` into destination `C`. `C>=n` prints error and disables cap; `C<=0` does nothing. | Audited; excluded initially. |
| `-T FLOAT` | `-1` | For nonnegative value enable divergence and add a fitted final parameter. Repeated later negative `-T` does not clear an already-set flag. | Audited; excluded initially. |
| `-S` | off | Simulate after fitting and any decoding/capping, retaining each input record's length and missing mask. Reseeds RNG independently. | Audited; excluded initially. |

Defaults come from zero-initialized `psmc_par_t` plus explicit assignments. [Defaults](https://github.com/lh3/psmc/blob/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a/cli.c#L142-L153), [post-fit ordering](https://github.com/lh3/psmc/blob/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a/main.c#L11-L30)

A later Rust CLI must either implement and validate a flag or reject it clearly. Listing the original flag is not a claim that a Rust implementation already supports it.

## 5. Encoding, boundaries, grouping, and initialization

Input uses zlib `gzopen`, or stdin for path `-`, and kseq FASTA/FASTQ parsing. A record name ends at header whitespace; comments are ignored by PSMC. Within sequence text, printable non-space characters are retained, while `>`, `@`, and `+` have parser meaning. FASTQ qualities are parsed but **ignored by `psmc` itself**. Truncated quality causes the reader loop to end, without a special PSMC error. Valid ASCII fixtures are the portability baseline; signed-char indexing and locale behavior make arbitrary bytes unsuitable as an implicit input contract. [Reader](https://github.com/lh3/psmc/blob/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a/cli.c#L103-L138), [kseq parser](https://github.com/lh3/psmc/blob/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a/kseq.h#L167-L209)

The conversion table is exact:

| Encoded observation | Accepted sequence characters | Meaning |
|---|---|---|
| `0` | `0`, `A`, `C`, `G`, `T`, and lowercase forms | Homozygous/no heterozygosity observation. |
| `1` | `1`, `K`, `M`, `R`, `S`, `W`, `Y`, and lowercase forms | Heterozygosity observation. |
| `2` | All other characters that survive kseq parsing, including `N`, `n`, `2`, `B`, `D`, `H`, `V`, `X`, `-`, `.` | Missing observation. |

[Conversion table](https://github.com/lh3/psmc/blob/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a/cli.c#L15-L32)

Every retained input character is one HMM position, including missing characters. `L` counts all positions; `L_e` counts observations 0/1; `n_e` counts observations 1. The dataset totals `sum_L` and `sum_n` sum effective lengths and heterozygosity counts. Missing positions have emission 1 in every state and retain transition steps. They are neither deleted nor new independent sequences. Each FASTA/FASTQ record restarts the HMM from `a0`; there is no transition between records. Duplicate names do not merge records. [Counts](https://github.com/lh3/psmc/blob/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a/cli.c#L110-L137), [missing emission](https://github.com/lh3/psmc/blob/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a/khmm.c#L10-L22), [per-record EM](https://github.com/lh3/psmc/blob/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a/em.c#L33-L55)

Pattern `a+b*c+d` means groups of widths `a`, followed by `b` groups each width `c`, then one width `d`. The number of states is the sum of widths; `pp->n` is states minus one, while `hp->n` is states. Default `4+5*3+4` means 23 states and 7 free lambdas. The README example has 64 states and 28 free lambdas. Group parsing is assertion-based and accepts no spaces; malformed/zero/overflowing patterns are not a supported numerical domain. [Pattern implementation](https://github.com/lh3/psmc/blob/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a/cli.c#L62-L99)

The free parameter vector is `[theta, rho, max_t, lambda_group_0, ..., lambda_group_F-1, optional_divergence]`. Header comments that mention only two non-lambda parameters are stale: `PSMC_N_PARAMS` is **3**. Without `-i`, theta is `-log(1 - sum_n/sum_L)`, rho is theta divided by `-r`, and lambdas use the random formula above. Even when `-I=0`, one `drand48()` call is consumed per lambda. Entirely missing/all-homozygous/all-heterozygous datasets have invalid or degenerate empirical initialization; fixed valid parameters can still be used to test their HMM observations separately. [Parameter count/initialization](https://github.com/lh3/psmc/blob/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a/core.c#L21-L50), [constant](https://github.com/lh3/psmc/blob/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a/psmc.h#L12)

A parameter file begins with the pattern, then `F+3` numbers. With a negative third number, the reader next loads `n+1` explicit time boundaries. It then attempts an extra divergence number. The parser reuses loop index `k` for time boundaries and uses that same `k` as the optional parameter index, so supplied-grid/divergence combinations may address the wrong slot or exceed the allocated parameter range. The upstream code itself marks divergence loading with FIXME comments; do not infer a general supported serialization from the prose comments. An ordinary `PA` line must have its `PA` prefix removed before serving as input. [Parameter reader](https://github.com/lh3/psmc/blob/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a/aux.c#L84-L113)

## 6. Model construction

With `n+1` states, default time boundaries are `t[k]=alpha*(exp(k*log(1+max_t/alpha)/n)-1)` for `k<n`, `t[n]=max_t`, and `t[n+1]=1000`. An explicit grid copies `t[0..n]`, still appending 1000. The terminal value is a finite implementation constant, not IEEE infinity. `max_t` is optimized in the default-grid model. With an explicit grid, it remains in the parameter vector even though grid construction ignores it. [Time grid](https://github.com/lh3/psmc/blob/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a/core.c#L6-L19)

The dense model is constructed in the following actual order, with scalar double arithmetic:

1. Expand each grouped lambda and compute time widths `tau[k]=t[k+1]-t[k]`.
2. Set `alpha[0]=1`; multiply survival factors successively, then force `alpha[n+1]=0` regardless of finite terminal time.
3. Recursively construct `beta[k]` and `q_aux[k]`, then `C_pi=sum lambda[k]*(alpha[k]-alpha[k+1])` and `C_sigma=1/(C_pi*rho)+0.5`.
4. For each state, calculate `pi[k]`, `sigma[k]`, and the recombination-derived average time `-log(1-pi[k]/(C_sigma*sigma[k]))/rho`.
5. If this average is NaN or outside the interval, use the code's conditional-mean fallback. This is a branch of the model implementation and must be captured in validation.
6. Build distinct lower, diagonal, and upper formulas for `q[k,l]`; multiply by `pi[k]/(C_sigma*sigma[k])`, adding `1` minus that factor only on the diagonal. Set `a0[k]=sigma[k]`.
7. Set `e[0,k]=exp(-theta*(avg_t+max(divergence,0)))`, `e[1,k]=1-e[0,k]`; missing `e[2,k]=1` remains from allocation.

[Complete construction](https://github.com/lh3/psmc/blob/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a/core.c#L61-L133)

The mathematical derivation supplies the lower/diagonal/upper structure, but the C implementation is the numerical oracle. Notable differences from a literal transcription of prose: finite terminal time with forced zero survival; the explicit average-time fallback; `C_sigma` uses the truncated formula; and source emissions identify observation 0 as `exp(-theta*avg_t)` and observation 1 as its complement. `psmc.tex`'s mutation-probability text labels a power expression `e_k(1)` and contains a sign inconsistency between its displayed exponential and power. Do not use that text to reverse observations or change implemented emissions. [Discrete equations](https://github.com/lh3/psmc/blob/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a/psmc.tex#L407-L465), [mutation discussion](https://github.com/lh3/psmc/blob/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a/psmc.tex#L467-L478)

No generic clipping, transition-row renormalization, replacement of `log(1-x)` with `log1p(-x)`, or stabilization is present in these loops. Such changes may be useful later but must be classified and validated rather than silently inserted into strict emulation.

## 7. Forward, backward, likelihood, counts, and Q

Use one-based positions `u=1..L`; source arrays include an unused row 0. State indices are zero-based.

**Forward.** At site 1, form `a0[k]*e[x1,k]`, sum in increasing state order, divide each component by the sum, and store that sum in `s[1]`. At each later site, compute a dense matvec using a transposed transition matrix, summing source states in increasing order; multiply by the destination emission, sum destinations in increasing order, normalize, and retain `s[u]`. All forward rows are stored. [Forward](https://github.com/lh3/psmc/blob/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a/khmm.c#L145-L190)

**Backward.** Precompute `ae[symbol,source,destination]=e[symbol,destination]*a[source,destination]`, including missing observations. Initialize `b[L,k]=1/s[L]`; descend positions, summing destinations in increasing order and dividing by `s[u]`, **not** `s[u+1]`. The posterior is therefore `f[u,k]*b[u,k]*s[u]`. A final initial-distribution check prints a warning outside `1±1e-6`; it does not repair values. [Backward preparation and recursion](https://github.com/lh3/psmc/blob/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a/khmm.c#L194-L241), [posterior](https://github.com/lh3/psmc/blob/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a/khmm.c#L286-L293)

**Likelihood.** The original does not sum `log(s[u])` independently at each site. It multiplies scale factors sequentially, flushes `log(product)` when the product becomes `<1e-25` or `>=1e25`, resets product to 1, and finally adds the remaining log. Per-record likelihoods are added in input order. This grouping is observable in floating point. [Likelihood](https://github.com/lh3/psmc/blob/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a/khmm.c#L245-L260), [ordered aggregate](https://github.com/lh3/psmc/blob/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a/em.c#L36-L50)

**Expected counts.** Each individual record begins with `1e-25` in every transition cell and every emission cell, including the missing row. For `u=1..L-1`, add transition contribution `f[u,k]*ae[x[u+1],k,l]*b[u+1,l]` and emission contribution `f[u,k]*b[u,k]*s[u]` to the observed symbol's row. **The last site's emission contribution is omitted.** `A0[l]=a0[l]*e[x1,l]*b[1,l]` is computed separately with no tiny initialization. A length-one record has initial-state counts but only tiny transition/emission cells. Aggregate transition and initial-state counts in input order; aggregate only emission rows 0 and 1, so the per-record missing row is not copied into the aggregate. [Counts and aggregation](https://github.com/lh3/psmc/blob/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a/khmm.c#L297-L359)

Consequences: each repeated bootstrap record contributes another set of tiny initializers; an observation cache must preserve multiplicity and addition order. The full matrix of transition counts is part of the contract. A conventional Baum–Welch implementation that includes the final emission, uses a different backward scaling, or drops tiny counts is not a literal port.

**Q normalizer.** `hmm_Q0` calculates the sum of emission count times log row-normalized emission count (over observations 0 and 1 for each state), plus transition count times log row-normalized transition count. It excludes `A0` and missing emissions. Candidate `hmm_Q` adds count-weighted log emissions and log transitions, and **subtracts this fixed full-count normalizer**. It also excludes `A0`. Any tested emission or transition value `<=0` returns `-1e300`, not negative infinity; NaNs do not satisfy those comparisons and can propagate. There is no separate finite-value validation. Retaining only triangular margins cannot in general reconstruct the full-count entropy normalizer. [Q0](https://github.com/lh3/psmc/blob/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a/khmm.c#L326-L342), [Q](https://github.com/lh3/psmc/blob/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a/khmm.c#L363-L382)

## 8. Optimizer and iteration state are observable behavior

The M-step runs the bundled Hooke–Jeeves implementation with radius `0.5`, epsilon `1e-7`, and nominal call limit `50000`. Initial coordinate step is `abs(x[k])*radius`, or radius if zero. Coordinates are explored in increasing order; failed first directions reverse sign; improvements use strict `<`; extrapolation, direction sign updates, and radius reductions must follow the implementation. Call limits are checked between exploration blocks, so they are not an exact callback-count ceiling. [Constants](https://github.com/lh3/psmc/blob/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a/kmin.h#L4-L6), [optimizer](https://github.com/lh3/psmc/blob/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a/kmin.c#L48-L107)

Every objective callback increments a counter, writes `fabs(candidate[i])` directly into `pd->params`, rebuilds the entire HMM, and returns negative Q. This is reflection, not a positivity-constrained optimizer or a positive floor; zero remains possible. In supplied-grid cases it also reflects a negative maximum-time marker while the explicit grid remains active. Consequently, a later `PA` can contain a positive third parameter plus trailing explicit boundaries; blindly loading it again can interpret the first boundary as divergence instead of recognizing an explicit grid. Such reloads require a dedicated compatibility test and are not promised here. [Callback](https://github.com/lh3/psmc/blob/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a/em.c#L15-L25)

A crucial source-level behavior: `kmin_hj` returns `fx1`, and `psmc_em` frees the working parameter array without copying its accepted vector back or evaluating it one final time. The live parameters/HMM therefore retain the **last callback's side effects**, which need not be the optimizer's accepted vector. A port that restores a textbook optimum would change the reference. Snapshot the callback sequence, accepted working vector where practical, returned Q1, final live model, and Q evaluated at that live model; do not assume those quantities coincide. [Optimizer return](https://github.com/lh3/psmc/blob/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a/kmin.c#L79-L107), [M-step call and cleanup](https://github.com/lh3/psmc/blob/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a/em.c#L56-L77)

`post_sigma` is normalized aggregate E[0]+E[1], reflecting the pre-M-step expectation and its final-site omission. `pd->lk` likewise comes from the pre-M-step model, while printed model parameters and `sigma` reflect the live post-callback state. Round zero prints initialized parameters and zero-initialized likelihood/Q/posterior fields; `RI` may be infinite because `post_sigma` is zero. There is no likelihood convergence stop: the main loop uses the requested number of iterations. [EM state update](https://github.com/lh3/psmc/blob/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a/em.c#L59-L74), [main rounds](https://github.com/lh3/psmc/blob/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a/main.c#L14-L20)

## 9. Bootstrap and RNG contract

The main program seeds POSIX `drand48` through `srand48(time(0) ^ getpid())` **before** parsing and reading input. There is no CLI seed. Bootstrap draws occur before lambda initialization, so exact replay needs RNG state and call order, not merely a list of initial lambdas. Simulation later reseeds with `time(0)` alone. [Initial seed](https://github.com/lh3/psmc/blob/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a/main.c#L11), [bootstrap placement](https://github.com/lh3/psmc/blob/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a/cli.c#L222-L224), [simulation reseed](https://github.com/lh3/psmc/blob/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a/aux.c#L234-L244)

For valid nonempty records, `psmc_resamp` does this:

1. Let target length `L_ori` be the sum of **raw** record lengths, including missing observations. Set sampled total `L=0`.
2. Draw a record uniformly by index `floor(n_seqs*drand48())`. Draw probability does not depend on its length.
3. Calculate deficit `tmp1=L_ori-L` and proposed overshoot `tmp2=L+record_length-L_ori` from the **pre-addition** total.
4. Add a full copy if the proposed total does not exceed the target, or if overshoot is positive and **strictly smaller** than deficit. Equal-distance overshoot is rejected.
5. Stop on this proposal whenever `tmp1>=0 && tmp2>=0`, whether the proposed block was accepted or rejected. Otherwise draw again.
6. Recompute effective-length/heterozygosity totals from the selected records, retaining sampled order and duplicate names.

It is not “draw the original number of blocks,” not fixed-length sampling, and not repeated rejection until exact length. The selected total can undershoot or overshoot. There is a final rejected proposal in some draws; preserve it in RNG audit records. The implementation stores totals in 64 bits but deficit/overshoot temporaries in `int`, so gigantic inputs can exceed the safe replay domain. [Exact algorithm](https://github.com/lh3/psmc/blob/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a/aux.c#L8-L47)

A reproducible comparison should save source input digest, splitting command and units, source record ordinals/digests, seed/RNG identity, ordered selected ordinals, every repeated occurrence, actual total lengths, and ideally all proposals through stopping. Materialized paired reference inputs avoid requiring an unmodified binary to expose a seed flag. A sampled occurrence remains an independent HMM record with its own initial distribution; concatenating sampled records into one continuous HMM changes the likelihood.

The user already runs bootstraps in parallel. Report end-to-end acceleration against the actual bounded-parallel workflow when obtained, and against a tuned but explicitly bounded original-C parallel baseline. Serial timings are useful diagnostics only; switching from serial to parallel earns no claimed improvement over the user's known workflow.

## 10. Preprocessing contract

### `fq2psmcfa`

This is a **separate program**. Its lowercase semantics differ from `psmc`: lowercase bases are treated as missing here. Defaults are 100-base blocks, minimum base quality 10, minimum 10,000 good bases per record, and missing threshold `0.9`. Quality is Phred+33. Low-quality bases are lowercased. A nucleotide encoded with exactly two alleles marks a heterozygote; blocks with any retained heterozygote emit `K`, otherwise `T`, unless the missing fraction exceeds the threshold and emits `N`. [Defaults/options](https://github.com/lh3/psmc/blob/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a/utils/fq2psmcfa.c#L8-L11), [conversion](https://github.com/lh3/psmc/blob/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a/utils/fq2psmcfa.c#L59-L142)

| Flag | Meaning |
|---|---|
| `-q INT` | Minimum base quality; default 10. |
| `-g INT` | Minimum retained good bases in a sequence; default 10000. |
| `-s INT` | Block length in input nucleotide characters; default 100. |
| `-x` | Mask fixed b36 pseudoautosomal coordinate ranges on exactly `X` or `chrX`; assembly-specific, not generic PAR detection. |
| `-v` | Mask transition heterozygotes (transversion-only heterozygosity). |
| `-n` | Mask transversion heterozygotes and CpG-like contexts (non-CpG transition treatment). |
| `-c` | Retain the implementation's CpG-transition heterozygosity selection. |
| `-C` | Exclude CpG-like contexts. |

At most one of `-v/-n/-c/-C` is allowed. The nucleotide-context implementation, including its order and neighboring-base edits, is the source contract, not the one-line labels above. The `-C` option is accepted even though omitted from the short usage option cluster. [Flag dispatch](https://github.com/lh3/psmc/blob/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a/utils/fq2psmcfa.c#L38-L57), [masking rules](https://github.com/lh3/psmc/blob/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a/utils/fq2psmcfa.c#L65-L112)

Missing fraction is `(float)nN/BLOCK_LEN > 0.9`, strictly greater; exactly 90% missing is retained under the ordinary default. The final partial block also divides by **full** `BLOCK_LEN`, not its actual shorter length. The record is emitted only if good bases/record length is at least 0.2 and good bases meet `-g`. Those thresholds and the terminal-block denominator must not be silently modernized during compatibility conversion. [Binning and filtering](https://github.com/lh3/psmc/blob/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a/utils/fq2psmcfa.c#L114-L137)

### `splitfa`

Arguments are `splitfa <in.fa> [trunk_size]`; there are no flag options. Default chunk size is **500000 input characters**, not base pairs. On 100-base PSMC bins this corresponds to 50 million bases, but bin size cannot be inferred from `.psmcfa` text alone. For each record, emit full chunks unless the remaining length is strictly less than `trunk_size*3/2` using integer arithmetic; then emit the full remainder as one terminal chunk. The last chunk can therefore be larger than the nominal size, and at the exact threshold it is split. Names are original name plus `_1`, `_2`, etc., restarting per record; output wraps at 60 characters. It opens a named file with zlib and does not special-case `-` as stdin. [Splitter](https://github.com/lh3/psmc/blob/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a/utils/splitfa.c#L8-L48)

The usage prose's `split_psmcfa` is an internal function name, while the built executable is `splitfa`. The theoretical text mentions 30-million-base segments; neither that text nor the README replaces the actual splitting command. [Utility build targets](https://github.com/lh3/psmc/blob/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a/utils/Makefile#L1-L19), [theoretical bootstrap example](https://github.com/lh3/psmc/blob/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a/psmc.tex#L543-L551)

### CpG counts and modern data

`cntcpg` accepts `-s` bin size (100), `-n` missing threshold (0.9), and `-b` to binarize selected mutation counts. It writes native 4-byte integer records: count-column number 5, then each sequence's binned length and five counts per bin. `psmc -c` consumes this order without matching names and only warns on length mismatch. The format has no explicit endian/version header; portability and pairing are not established by a passing fit test. [Count producer](https://github.com/lh3/psmc/blob/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a/utils/cntcpg.c#L34-L97), [count consumer](https://github.com/lh3/psmc/blob/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a/aux.c#L144-L148), [weighted accumulation](https://github.com/lh3/psmc/blob/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a/aux.c#L202-L231)

The README already documents a dipcall route with reference FASTA, SNP conversion, and a callable BED mask; it is not a new long-read inference model. `vcf2snp.pl` takes the first sample field and assumes its first subfield is genotype, ignores phasing distinctions, filters to representable SNP allele pairs, and parses a `-q` option that is never used. It is not a general validated VCF/gVCF adapter. Missing VCF entries must not be interpreted as callable homozygous reference without an explicit reference/callability contract. External `samtools`, `bcftools`, `seqtk`, and dipcall invocations in the README are historical examples, not tested modern dependency instructions. [README input routes](https://github.com/lh3/psmc/blob/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a/README#L16-L31), [SNP converter](https://github.com/lh3/psmc/blob/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a/utils/vcf2snp.pl#L7-L27)

## 11. Output semantics and deferred output flags

Ordinary output begins with `CC` and `MM` descriptions, followed by round-zero state, then `IT` and each `RD` round. Some initial descriptions are stale: the real likelihood tag is **`LK`**, although the header describes `LL`; actual `RS` meanings differ from the initial header's old labels. [Header text](https://github.com/lh3/psmc/blob/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a/cli.c#L200-L210), [actual records](https://github.com/lh3/psmc/blob/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a/aux.c#L49-L81)

| Record | Actual fields/meaning |
|---|---|
| `RD` | Round index, starting at 0. |
| `IT` | Number of objective callbacks during the preceding M-step. |
| `LK` | Total pre-M-step natural log likelihood, `%lf` (six decimals). |
| `QD` | Q before and optimizer-return Q after, six decimals with literal ` -> `. |
| `RI` | `sum sigma[k]*log(sigma[k]/post_sigma[k])`, ten decimals; round-zero nonfinite value is expected from zero posterior allocation. |
| `TR` | Live theta and rho, six decimals. |
| `MT` | Live maximum-time parameter, six decimals. |
| `DT` | Divergence parameter when enabled, six decimals. |
| `MM C_pi, n_recomb` | Model `C_pi`; `n_recomb=sum_L/C_sigma` uses effective observed length. |
| `RS` | State index, boundary `t[k]`, expanded lambda, `n_recomb*a0[k]`, `sigma[k]`, `post_sigma[k]`, each float at six decimals. |
| `PA` | Pattern, all live parameters at nine decimals, then explicit grid if present. |
| `//` | End of round. |

`-d` chooses the maximum posterior state with increasing-state tie preference. Coordinates are **one-based inclusive input bins**. `DC` reports each state segment and its maximum per-site posterior; the final segment has different formatting precision (time three decimals/probability two) from preceding segments (time six/probability three). `-D` prints `DF` with position, an off-diagonal-transition posterior-derived quantity, and each state probability at four decimals; it does not include sequence names on DF lines. `-s` prints `PR name length` followed by scale factors at three decimals and suppresses the DC/DF branches. All decoding paths first emit `TC`; CpG counts can be accumulated in addition. [Decoding implementation](https://github.com/lh3/psmc/blob/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a/aux.c#L129-L231), [posterior tie rule](https://github.com/lh3/psmc/blob/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a/khmm.c#L264-L281)

`-C` changes the transition matrix only, after fitting; it does not recompute initial probabilities or other model diagnostics. If simulation follows, it uses this potentially capped matrix. Simulation draws an initial state from `a0`, then transitions **before** generating the first observation, and emits `FA`-prefixed FASTA text with the original missing mask reinstated. [Cap](https://github.com/lh3/psmc/blob/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a/aux.c#L115-L127), [simulation](https://github.com/lh3/psmc/blob/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a/khmm.c#L386-L423), [output/masking](https://github.com/lh3/psmc/blob/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a/aux.c#L234-L254)

The HMM library contains a Viterbi implementation, but `psmc -d` does not call it; it uses posterior decoding. Plotting/conversion acceptance still requires actual round-trip tests with upstream utilities. Such compatibility cannot be claimed solely because the output has familiar tags.

## 12. Required remaining evidence

Before numerical work beyond Phase 0: review the chosen compatibility tier, define tolerances before examining accelerated results, and supply or explicitly replace the missing numerical design documents. Before a performance claim: obtain the user's full commands, current worker/process cap, real `.psmcfa` hashes and record lengths, bin size, split command, assembly/mask provenance, hardware/VM restrictions, and whether reported time includes preprocessing/plotting. Record the same 30 ordered bootstrap draws on both paths.

The baseline must separately report unmodified C total time/RSS, serial diagnostic fits, bounded-parallel replicate throughput, and sampling-profiler attribution. Model construction, forward, backward, expected counts, Q evaluation/optimizer callback counts, allocations, and I/O need distinguishable evidence; missing phase attribution stays `not_run` or incomplete. A later equivalent backend must publish failures and fallbacks, preserve full-count Q and all observation occurrences, and demonstrate end-to-end benefit on the already-parallel workload. No timing in this Phase 0 contract establishes a 10× speedup.

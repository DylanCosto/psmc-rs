# Structured transition experiment and strict arithmetic boundary

This isolated experiment derives the triangular factors from the actual pinned
`core.c::psmc_update_hmm`; it does not reuse a generic HMM as the PSMC model.
`bench/cpu_campaign_algebra.py` reconstructs the literal matrix first and requires
every binary64 value to match the saved C snapshot before testing a rewrite.

Use the implementation's `alpha`, `beta`, `q_aux`, `cpik`, `pik`, `sigma` and
`C_sigma` values. Define `delta[k] = alpha[k] - alpha[k+1]` and
`R[k] = pik / (C_sigma * sigma[k])`. The original code computes:

```
l < k: A[k,l] = R[k] * ((delta[k] / cpik) * q_aux[l])
l > k: A[k,l] = R[k] * (delta[l] * (q_aux[k] / cpik))
l = k: retain the original separately calculated diagonal, including 1 - R[k].
```

In real arithmetic, set `L[k] = R[k] * (delta[k] / cpik)`,
`U[k] = R[k] * (q_aux[k] / cpik)` and `D[k] = A[k,k]`. Lower entries factor as
`L[k] * q_aux[l]`, upper entries as `U[k] * delta[l]`. Thus an unnormalized
forward destination k is:

```
emission[k] * (delta[k] * sum(j<k, f[j]*U[j])
             + f[k]*D[k]
             + q_aux[k] * sum(j>k, f[j]*L[j]))
```

Exclusive prefix and suffix scans compute these sums in linear state-count work;
the unused final `q_aux` term is zero because its suffix is empty. This is an
identity over real numbers. It changes both matrix-product rounding and the
order/grouping of the forward dot product in binary64. Backward also has the
original emission-times-transition product rounding to preserve. Reconstructing a
close matrix alone therefore cannot establish strict message compatibility.

For the objective, triangular row/column count margins multiply logarithms of
the factors, with diagonal count/log terms retained individually. Keep the full
original entropy normalizer. `log(a*b)` need not equal `log(a)+log(b)` after
binary64 rounding, and grouping weighted counts changes addition order. A
same-model mathematical identity does not imply the same Hooke–Jeeves decisions.

The experiment uses the saved valid 23-state C generating model and three positive
forward vectors, plus an arbitrary positive complete transition-count matrix and
two positive emission-count rows. It computes the full entropy normalizer in
the original order. It records exact mismatch counts and error magnitudes for
factor reconstruction, forward vectors and factored Q. One genuine strict
counterexample is sufficient to reject this formulation for the strict release;
it does not prove all possible strict algorithms impossible.

No timing win, fitted curve equivalence, optimizer-trajectory preservation or
production-ready equivalent backend can be inferred from this experiment. An
equivalent numerical contract remains a separately reviewed decision. Until then,
retain the literal dense oracle and optimize independent operations whose per-cell
rounding order can be preserved.

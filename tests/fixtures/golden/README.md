# Pinned C golden outputs

Generated 2026-10-10 by the unmodified vanilla build of `lh3/psmc` at
`82fa2ada83ee463fe1251b562ae3d60e82d7ad6a` (`work/vanilla/psmc`, see
`README_PHASE0.md`) on x86-64 Linux/glibc 2.39. Run from the repository root:

```bash
psmc -p '4+5*3+4'    -N 10 -t 15 -r 4    -o workload-k22.psmc       tests/fixtures/workload.psmcfa
psmc -p '4+25*2+4+6' -N 3  -t 15 -r 5    -o profile-k64.psmc        tests/fixtures/profile.psmcfa
psmc -p '2+2+2'      -N 5  -t 5  -r 4    -o repeated-k6.psmc        tests/fixtures/repeated.psmcfa
psmc -p '1+2'        -N 4  -t 15 -r 4 -d -o workload-k3-decode.psmc tests/fixtures/workload.psmcfa
```

Each case is finite apart from the expected round-zero `RI inf`. Together they
cover the 64-state wide AVX kernels, generic AVX with scalar tails, the
repeated-record count cache, sub-four-state scalar dispatch, and decoding.
`crates/psmc-cli/tests/golden.rs` compares every byte except the `MM Version`
line. Regenerate only from the pinned C build, and never to make a test pass.

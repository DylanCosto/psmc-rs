# Launch announcement draft

PSMC-rs brings accelerated CPU inference and a reproducible local workflow to
PSMC: native Linux binaries, a synthetic tutorial, input inspection, block
splitting, bootstrap resume and curve export/plotting.

It offers two explicit arithmetic contracts. Strict mode reproduces the pinned C
build on tested inputs, excluding the version header. CPU fits default to equivalent
f64 mode, which changes floating-point grouping and uses QU instead of QD. The
repository documents both guarantees and their limits.

A controlled public HG001 whole-autosome benchmark measured 17.66× single-core
speedup for equivalent mode over vanilla C. The full-affinity result was 26.24 s
on the tested i5-12600K. Those numbers are from v0.6.3, three measured runs per
configuration, with a shared host; they are not a universal speed claim or a new
v0.8.0 benchmark. Scientific agreement and performance evidence are reported
separately, including failed pilot screens.

Code, installation, methods and evidence: https://github.com/DylanCosto/psmc-rs

Independent reproduction and feedback are welcome, especially installation issues,
legacy-script compatibility and difficult numerical cases. Please use synthetic
reproducers rather than posting genomes or restricted input. Built on the model
and original PSMC implementation by Heng Li and Richard Durbin; see citation and
license notices in the repository.

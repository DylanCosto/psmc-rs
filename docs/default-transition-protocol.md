# Equivalent-default release protocol — 2026-10-11

User authorizes release candidate, compatibility checks, then promotion of
equivalent to default while preserving strict and memory safeguards. This is a
CLI/release change, not a new numerical optimization or new equivalence tolerance.

Build 0.7.0-rc.1 first. Default CPU fits and bootstrap select equivalent. An omitted
mode with dense/CUDA backend or snapshot selects strict for compatibility; explicit
equivalent with those features remains an error. Selection is independent of
argument order, including PSMC_SNAPSHOT. Report selected mode in existing output
metadata/stats and stderr. Strict golden checks must explicitly select strict.

Extend single CPU fit memory admission to equivalent rather than ignore/reject
--memory-mib. Keep the strict estimate unchanged. Equivalent reserves checkpoint
scratch per admitted worker, loaded/frozen/queued observations, counts and a
retained serial dense history for ineligible-model evaluation, plus another dense
history for decoding. Default remains half available RAM/cgroup headroom. Reject
an insufficient budget before opening output files. Preserve batch admission.
Admission is an estimate, not an OS-enforced RSS limit; input loading precedes it.

Candidate gates: workspace release tests and formatting; live pinned C goldens;
implicit/explicit mode parity; prior v0.6.3 strict/equivalent output parity excluding
only version; dense and snapshot selection; conflicting explicit requests;
decoding (-d/-D/-s/-C), initialized parameters, gzip/stdin, deterministic bootstrap
and selected-mode metadata; low-budget rejection and bounded worker admission.
Exercise upstream psmc2history, avg, psmc_trunc and psmc_plot data/script generation
on equivalent outputs. If gnuplot is absent, report rendering not_run and test its
input generation without pretending a renderer ran. Do not download dependencies.

Run a bounded allocation check including equivalent's dense-fallback reserve and
decoding, under hard process limits. Reuse public HG001 for one N30 default fit,
with 8 GiB admission/10 GiB process limit, comparing against the previously audited
v0.6.3 equivalent output. Retain resource/command/output hashes. No new simulation
or expensive C rerun; previously frozen C comparison remains supporting evidence.

Only after candidate checks pass, bump to 0.7.0, repeat release checks, compare
candidate/final numerical output, install versioned and current local binaries
without replacing earlier versions, and update README/help/release documentation.
Preserve strict as a supported mode and CI goldens. No remote publication or hosted
CI claim without a configured remote; do not change historical evidence/protocols.

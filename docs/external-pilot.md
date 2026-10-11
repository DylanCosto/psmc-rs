# Independent reproduction pilot

Status: materials prepared; no independent user has been recruited or endorsed
PSMC-rs through this project yet. The owner chooses recipients. No invitation is
sent merely because a template exists.

## What to ask a participating lab to try

1. Install a tagged Linux binary, verify checksums and run the synthetic tutorial.
2. On an already approved local dataset, reproduce an existing vanilla PSMC
   command with `--mode strict`, then equivalent with identical scientific options.
3. Keep input preparation, state pattern, iterations, boundaries and scaling fixed.
   Compare numerical output with the documented mode contracts; inspect nonfinite
   warnings and fallback counts. Run their normal bootstrap workflow if feasible.
4. Record elapsed/CPU time and peak memory with a complete command and environment.
   Separate single-core from parallel results; report repetitions and warmups.
5. Report installation friction, unclear messages, output/tool incompatibilities,
   interruptions/resume behavior and numerical surprises. An unexpected difference
   is useful feedback; publication does not depend on reporting a favorable result.

## Minimal feedback form

- Release/tag, executable checksum, mode and complete command:
- OS/architecture, CPU, RAM, worker/memory settings:
- Data type, bin size, record count/lengths and mask/callability preparation:
- Pattern, iterations, theta/rho setting and biological scaling:
- Vanilla comparison build/flags; comparison method and observed differences:
- Nonfinite warnings, structured fallbacks and failed/resumed jobs:
- Warmup/repetition count, wall/CPU time and peak RSS:
- Existing scripts that worked or broke (especially QD/QU parsing):
- Time to first successful result and the hardest step:
- Permission to quote feedback or name the lab (optional, explicitly opt-in):

Do not send raw genomes, sample identifiers, credentials or restricted files.
A tiny synthetic reproducer is preferred for issues. Use a private channel for
sensitive security reports. Aggregate statistics may still be sensitive under a
lab's policy; the participant controls what to share.

## Invitation draft — owner to address and send

I'm preparing PSMC-rs, a Rust implementation of PSMC with accelerated CPU fits,
strict reproduction checks and an equivalent arithmetic mode. Would someone in
your group be willing to try a short local installation/tutorial and, if useful,
one existing PSMC workload? I'm especially interested in installation problems,
script compatibility and numerical differences. No genomic data needs to leave
your environment, and candid negative results are welcome.

The repository includes mode guarantees, limitations, validation reports and Linux
binaries: https://github.com/DylanCosto/psmc-rs . There is no expectation of
endorsement or authorship. If interested, I can send the reproducibility checklist.

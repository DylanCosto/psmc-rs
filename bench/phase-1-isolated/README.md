# Isolated Phase 1 model and optimizer comparisons

Reproduce these checks from the project root:

```sh
python3 bench/check_phase1_isolated.py
```

The runner requires GCC, the project's Rust 1.90.0 toolchain, and the pinned C
source in `work/vanilla` plus the source archive produced by `reference/build.py`.
It verifies the archive's recorded SHA-256 and checks every compiled reference
source/header against that archive. It rebuilds all four executables, runs them, compares
the binary floating-point streams, and writes `results.json`. The report records
compiler commands, toolchain identities, source/binary/output SHA-256 digests,
system libraries, and comparison results. Paths recorded for this project are
relative or `${PROJECT}` placeholders. `bin/` retains the current x86-64 Linux
executables; rebuild them on a compatible system instead of assuming portability.

## Fixtures

- `model-check.c` and `model-check.rs` compare 60 snapshots: 1, 2, 4, 23, and 64
  states; six combinations of generated/explicit grids, divergence, and random
  initialization; and initial/updated parameter vectors. C and Rust both replay
  seed 42. The stream includes parameters, every time boundary, sigma, both
  normalization constants, initial distribution, every transition/emission cell,
  and interval average times. There are 64,446 f64 values. The one-state case is a
  library boundary probe, not a promise that the CLI accepts that pattern.
- `optimizer-check.c` and `optimizer-check.rs` compare 16 runs: quadratic,
  constant, NaN-producing, and monotonic objectives, each with nominal call limits
  of 1, 10, 100, and 1,000. Every callback vector is recorded, followed by the final
  accepted vector and optimizer return value. There are 5,962 f64 values. This
  checks branch order, nominal-call-limit overshoot, and final callback behavior.

Raw streams in `raw/` use native-endian binary doubles; the report records
endianness. Byte-exact comparison includes sign bits. NaN pairing is counted
separately and does not certify finite inference. These isolated checks are
supplementary: full parsing, HMM/EM integration, output compatibility, performance,
and real workloads require their separate gates.

## Source and licensing

The C fixtures call the unchanged original routines from
[`lh3/psmc` at 82fa2ada83ee463fe1251b562ae3d60e82d7ad6a](https://github.com/lh3/psmc/tree/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a):
[`core.c`](https://github.com/lh3/psmc/blob/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a/core.c),
[`khmm.c`](https://github.com/lh3/psmc/blob/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a/khmm.c),
and [`kmin.c`](https://github.com/lh3/psmc/blob/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a/kmin.c).
PSMC carries the MIT license, copyright Genome Research Ltd (2007–2009) and Broad
Institute (2009–2015); `kmin.c` additionally retains Heng Li's 2008 notice.
The complete notices are preserved in the upstream files, the translated Rust
files, and `reference/LICENSE.psmc.txt`. The fixture drivers are newly authored
synthetic checks and contain no private input data.

The initial run used the prebuilt reference objects; this durable runner compiles
the actual pinned C source with `-O2 -ffp-contract=off`. All displayed results
come from the durable rerun and not the superseded scratch executables.

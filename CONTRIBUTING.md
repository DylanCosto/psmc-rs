# Contributing

Start with an issue explaining the problem, platform, command and expected
behavior. A minimal synthetic example is best. Do not upload human genomic data,
patient identifiers, access tokens, or private paths in logs.

Build and test from the repository root:

```sh
cargo fmt --all -- --check
cargo test --release --locked --offline --workspace
python3 -m unittest discover -s bench -p 'test_known_truth*.py'
python3 -m unittest discover -s bench -p 'test_pilot*.py'
```

Use the pinned Rust toolchain. Numerical changes also need the mathematical
contract, an isolated differential test, unchanged strict C comparisons, full-fit
validation and measured performance evidence. See MATH_AND_COMPATIBILITY.md,
VALIDATION_AND_BENCHMARKS.md and AGENTS.md. Do not update golden outputs merely to
make tests pass. Hardware tests that were not run must remain labeled not_run.

Keep changes focused and explain observable behavior, test results and limitations
in pull requests. Include original license notices when translating upstream code.
Documentation, portability reports and reproducible bug reports are welcome.

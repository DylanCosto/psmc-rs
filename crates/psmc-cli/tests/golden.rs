//! Byte comparison against outputs from the pinned C reference
//! (lh3/psmc 82fa2ada83ee463fe1251b562ae3d60e82d7ad6a). See
//! tests/fixtures/golden/README.md for how they were generated. Only the
//! `MM\tVersion:` line is excluded.
use std::{fs, path::PathBuf, process::Command};

const CASES: &[(&str, &str, &[&str])] = &[
    (
        "workload-k22",
        "workload.psmcfa",
        &["-p", "4+5*3+4", "-N", "10", "-t", "15", "-r", "4"],
    ),
    (
        "profile-k64",
        "profile.psmcfa",
        &["-p", "4+25*2+4+6", "-N", "3", "-t", "15", "-r", "5"],
    ),
    (
        "repeated-k6",
        "repeated.psmcfa",
        &["-p", "2+2+2", "-N", "5", "-t", "5", "-r", "4"],
    ),
    (
        "workload-k3-decode",
        "workload.psmcfa",
        &["-p", "1+2", "-N", "4", "-t", "15", "-r", "4", "-d"],
    ),
];

const BACKENDS: &[&[&str]] = &[
    &[],
    &["--backend", "cpu", "--simd", "off"],
    &["--backend", "cpu", "--cache", "off"],
    &["--backend", "dense"],
];

fn fixtures() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../tests/fixtures")
}

fn without_version(text: &str) -> Vec<&str> {
    text.lines()
        .filter(|line| !line.starts_with("MM\tVersion:"))
        .collect()
}

#[test]
fn output_matches_pinned_c_reference() {
    let scratch = PathBuf::from(env!("CARGO_TARGET_TMPDIR")).join("golden");
    fs::create_dir_all(&scratch).unwrap();
    for (name, input, args) in CASES {
        let expected =
            fs::read_to_string(fixtures().join("golden").join(format!("{name}.psmc"))).unwrap();
        for (variant, backend) in BACKENDS.iter().enumerate() {
            let output = scratch.join(format!("{name}-{variant}.psmc"));
            let _ = fs::remove_file(&output);
            let status = Command::new(env!("CARGO_BIN_EXE_psmc-rs"))
                .args(*backend)
                .args(*args)
                .arg("-o")
                .arg(&output)
                .arg(fixtures().join(input))
                .status()
                .unwrap();
            assert!(status.success(), "{name} {backend:?} exited with {status}");
            let actual = fs::read_to_string(&output).unwrap();
            assert_eq!(
                without_version(&actual),
                without_version(&expected),
                "{name} with {backend:?} differs from the C reference"
            );
        }
    }
}

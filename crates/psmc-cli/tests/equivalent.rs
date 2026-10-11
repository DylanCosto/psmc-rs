//! Explicit mode selection and truthful artifact metadata.
use std::{path::PathBuf, process::Command};
fn fixture() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../tests/fixtures/repeated.psmcfa")
}
#[test]
fn equivalent_mode_is_explicit_and_incompatible_backends_are_rejected() {
    let binary = env!("CARGO_BIN_EXE_psmc-rs");
    for extra in [
        vec!["--backend", "dense"],
        vec!["--backend", "cuda"],
        vec!["--snapshot", "unused.jsonl"],
    ] {
        let out = Command::new(binary)
            .args(["--mode", "equivalent"])
            .args(extra)
            .arg(fixture())
            .output()
            .unwrap();
        assert!(!out.status.success());
        assert!(out.stdout.is_empty());
    }
    for mode in ["strict", "equivalent"] {
        let out = Command::new(binary)
            .args([
                "--mode", mode, "-p", "2+2+2", "-N", "2", "-t", "5", "-I", "0",
            ])
            .arg(fixture())
            .output()
            .unwrap();
        assert!(
            out.status.success(),
            "{}",
            String::from_utf8_lossy(&out.stderr)
        );
        let text = String::from_utf8(out.stdout).unwrap();
        assert!(text.contains(&format!("({mode} f64;")));
        assert!(text.contains("RD\t2\n"));
        assert!(text.lines().any(|l| l.starts_with(if mode == "equivalent" {
            "QU\t"
        } else {
            "QD\t"
        })));
        assert!(
            !text.lines().any(|l| l.starts_with(if mode == "equivalent" {
                "QD\t"
            } else {
                "QU\t"
            }))
        );
    }
}

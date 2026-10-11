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

#[test]
fn record_helpers_preserve_full_output_for_both_modes_and_cache_policies() {
    let binary = env!("CARGO_BIN_EXE_psmc-rs");
    for mode in ["strict", "equivalent"] {
        for cache in ["on", "off"] {
            let run = |workers: Option<&str>| {
                let mut cmd = Command::new(binary);
                if let Some(workers) = workers {
                    cmd.args(["--record-workers", workers]);
                }
                let out = cmd
                    .args([
                        "--mode", mode, "--cache", cache, "--seed", "42", "-p", "4+5*3+4", "-N",
                        "3", "-I", "0",
                    ])
                    .arg(fixture())
                    .output()
                    .unwrap();
                assert!(
                    out.status.success(),
                    "{}",
                    String::from_utf8_lossy(&out.stderr)
                );
                out.stdout
            };
            let serial = run(Some("1"));
            assert_eq!(serial, run(Some("4")), "{mode}/{cache}");
            assert_eq!(serial, run(None), "default {mode}/{cache}");
        }
    }
}

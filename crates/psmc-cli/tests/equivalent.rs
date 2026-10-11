//! Explicit mode selection and truthful artifact metadata.
use std::{path::PathBuf, process::Command};
fn fixture() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../tests/fixtures/repeated.psmcfa")
}
#[test]
fn explicit_modes_and_incompatible_backends_are_rejected() {
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

#[test]
fn strict_memory_budget_admits_workers_and_rejects_before_output() {
    let binary = env!("CARGO_BIN_EXE_psmc-rs");
    let dir = std::env::temp_dir().join(format!("psmc-memory-{}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    let output = dir.join("output.psmc");
    let stats = dir.join("stats.json");
    std::fs::write(&output, "preserve existing output").unwrap();
    let rejected = Command::new(binary)
        .args(["--mode", "strict", "--memory-mib", "1", "-o"])
        .arg(&output)
        .arg("--stats")
        .arg(&stats)
        .arg(fixture())
        .output()
        .unwrap();
    assert!(!rejected.status.success());
    assert!(String::from_utf8_lossy(&rejected.stderr).contains("cannot admit one record"));
    assert_eq!(
        std::fs::read_to_string(&output).unwrap(),
        "preserve existing output"
    );
    assert!(!stats.exists());
    let common = [
        "--mode", "strict", "-p", "2+2+2", "-N", "2", "-t", "5", "--seed", "42",
    ];
    let serial = Command::new(binary)
        .args(common)
        .args(["--record-workers", "1"])
        .arg(fixture())
        .output()
        .unwrap();
    let bounded = Command::new(binary)
        .args(common)
        .args(["--memory-mib", "35", "--record-workers", "8", "--stats"])
        .arg(&stats)
        .arg(fixture())
        .output()
        .unwrap();
    assert!(
        bounded.status.success(),
        "{}",
        String::from_utf8_lossy(&bounded.stderr)
    );
    assert_eq!(serial.stdout, bounded.stdout);
    let stats = std::fs::read_to_string(&stats).unwrap();
    assert!(stats.contains("\"budget_bytes\":36700160"));
    assert!(stats.contains("\"workers\":1,"));
    std::fs::remove_dir_all(dir).unwrap();
}

#[test]
fn default_selection_and_equivalent_budget_are_explicit_in_artifacts() {
    let binary = env!("CARGO_BIN_EXE_psmc-rs");
    let dir = std::env::temp_dir().join(format!("psmc-default-{}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    let run = |args: &[&str]| {
        Command::new(binary)
            .env_remove("PSMC_SNAPSHOT")
            .args(["-p", "2+2+2", "-N", "2", "-t", "5", "--seed", "42"])
            .args(args)
            .arg(fixture())
            .output()
            .unwrap()
    };
    let default = run(&[]);
    let explicit = run(&["--mode", "equivalent"]);
    assert!(default.status.success());
    assert_eq!(default.stdout, explicit.stdout);
    assert!(String::from_utf8_lossy(&default.stdout).contains("(equivalent f64;"));
    assert_eq!(
        run(&["--backend", "dense"]).stdout,
        run(&["--mode", "strict", "--backend", "dense"]).stdout
    );
    let snapshot = dir.join("snapshot.jsonl");
    let snap = run(&["--snapshot", snapshot.to_str().unwrap()]);
    assert!(snap.status.success());
    assert!(String::from_utf8_lossy(&snap.stdout).contains("(strict f64;"));
    let env_snap = Command::new(binary)
        .env("PSMC_SNAPSHOT", &snapshot)
        .args(["-p", "2+2+2", "-N", "0", "-t", "5"])
        .arg(fixture())
        .output()
        .unwrap();
    assert!(env_snap.status.success());
    assert!(String::from_utf8_lossy(&env_snap.stdout).contains("(strict f64;"));
    let stats = dir.join("stats.json");
    let admitted = run(&["--memory-mib", "35", "--stats", stats.to_str().unwrap()]);
    assert!(admitted.status.success());
    assert_eq!(default.stdout, admitted.stdout);
    let metadata = std::fs::read_to_string(&stats).unwrap();
    assert!(metadata.contains("\"mode\":\"equivalent\""));
    assert!(metadata.contains("\"budget_bytes\":36700160"));
    let output = dir.join("preserved.psmc");
    std::fs::write(&output, "keep").unwrap();
    let reject = run(&["--memory-mib", "1", "-o", output.to_str().unwrap()]);
    assert!(!reject.status.success());
    assert_eq!(std::fs::read_to_string(&output).unwrap(), "keep");
    std::fs::remove_dir_all(dir).unwrap();
}

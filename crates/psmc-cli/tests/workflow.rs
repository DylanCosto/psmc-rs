//! Exercise workflow safety at the executable boundary, including real SIGKILL.
use std::{
    fs,
    path::{Path, PathBuf},
    process::{Command, Stdio},
    time::{Duration, Instant},
};
fn binary() -> &'static str {
    env!("CARGO_BIN_EXE_psmc-rs")
}
fn fixture(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../tests/fixtures")
        .join(name)
}
struct Scratch(PathBuf);
impl Scratch {
    fn new(name: &str) -> Self {
        let path = PathBuf::from(env!("CARGO_TARGET_TMPDIR"))
            .join(format!("workflow-{name}-{}", std::process::id()));
        let _ = fs::remove_dir_all(&path);
        fs::create_dir_all(&path).unwrap();
        Self(path)
    }
}
impl Drop for Scratch {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}
fn batch(directory: &Path, input: &Path, mode: &str) -> Command {
    let mut cmd = Command::new(binary());
    cmd.args([
        "bootstrap",
        "--mode",
        mode,
        "--replicates",
        "8",
        "--workers",
        "1",
        "--memory-mib",
        "256",
        "--seed",
        "2026",
        "-N",
        "4",
        "-p",
        "4+5*3+4",
        "--output-dir",
    ])
    .arg(directory)
    .arg(input)
    .stdout(Stdio::null())
    .stderr(Stdio::null());
    cmd
}
#[test]
fn utilities_preserve_input_and_require_units() {
    let scratch = Scratch::new("utilities");
    let blocks = scratch.0.join("blocks.psmcfa");
    let inspected = Command::new(binary())
        .arg("inspect")
        .arg(fixture("workload.psmcfa"))
        .output()
        .unwrap();
    assert!(inspected.status.success());
    assert!(
        String::from_utf8(inspected.stdout)
            .unwrap()
            .contains("records\t3")
    );
    let status = Command::new(binary())
        .args(["split", "--block-bins", "1000", "--output"])
        .arg(&blocks)
        .arg(fixture("workload.psmcfa"))
        .status()
        .unwrap();
    assert!(status.success());
    let before = psmc_io::read_sequences(fixture("workload.psmcfa").to_str().unwrap()).unwrap();
    let after = psmc_io::read_sequences(blocks.to_str().unwrap()).unwrap();
    for s in before {
        let flattened: Vec<_> = after
            .iter()
            .filter(|b| b.name.starts_with(&format!("{}_", s.name)))
            .flat_map(|b| b.observations.clone())
            .collect();
        assert_eq!(flattened, s.observations);
    }
    let preserved = fs::read(&blocks).unwrap();
    assert!(
        !Command::new(binary())
            .args(["split", "--block-bins", "1000", "--output"])
            .arg(&blocks)
            .arg(fixture("workload.psmcfa"))
            .status()
            .unwrap()
            .success()
    );
    assert_eq!(preserved, fs::read(&blocks).unwrap());
    let csv = scratch.0.join("curve.csv");
    assert!(
        !Command::new(binary())
            .args(["export", "--output"])
            .arg(&csv)
            .arg(fixture("golden/workload-k22.psmc"))
            .status()
            .unwrap()
            .success()
    );
    assert!(!csv.exists());
    assert!(
        Command::new(binary())
            .args([
                "export",
                "--mutation-rate",
                "1.25e-8",
                "--generation-years",
                "25",
                "--bin-bp",
                "100",
                "--output"
            ])
            .arg(&csv)
            .arg(fixture("golden/workload-k22.psmc"))
            .status()
            .unwrap()
            .success()
    );
    assert_eq!(fs::read_to_string(csv).unwrap().lines().count(), 24);
}
#[test]
#[cfg(target_os = "linux")]
fn killed_bootstrap_resumes_exactly_and_rejects_tampering() {
    for mode in ["strict", "equivalent"] {
        let scratch = Scratch::new(mode);
        let baseline = scratch.0.join("baseline");
        let resumed = scratch.0.join("resumed");
        let input = scratch.0.join("input.psmcfa");
        fs::copy(fixture("profile.psmcfa"), &input).unwrap();
        assert!(batch(&baseline, &input, mode).status().unwrap().success());
        let mut child = batch(&resumed, &input, mode).spawn().unwrap();
        let deadline = Instant::now() + Duration::from_secs(90);
        while !resumed.join("replicate-00.complete").exists() {
            if child.try_wait().unwrap().is_some() || Instant::now() > deadline {
                let _ = child.kill();
                panic!("child did not produce a checkpoint");
            }
            std::thread::sleep(Duration::from_millis(1));
        }
        // A second process must refuse the kernel lock while the owner is alive.
        assert!(
            !batch(&resumed, &input, mode)
                .arg("--resume")
                .status()
                .unwrap()
                .success()
        );
        child.kill().unwrap();
        child.wait().unwrap();
        let complete_before = (0..8)
            .filter(|i| resumed.join(format!("replicate-{i:02}.complete")).exists())
            .count();
        assert!(
            (1..8).contains(&complete_before),
            "must actually interrupt unfinished work"
        );
        let kept = fs::read(resumed.join("replicate-00.psmc")).unwrap();
        assert!(
            !batch(&resumed, &input, mode)
                .args(["--resume", "-N", "5"])
                .status()
                .unwrap()
                .success()
        );
        let original_input = fs::read(&input).unwrap();
        let mut altered = original_input.clone();
        altered.extend_from_slice(b"\n>extra\nTK\n");
        fs::write(&input, altered).unwrap();
        assert!(
            !batch(&resumed, &input, mode)
                .arg("--resume")
                .status()
                .unwrap()
                .success()
        );
        fs::write(&input, original_input).unwrap();
        fs::write(resumed.join("replicate-00.psmc"), b"tampered").unwrap();
        assert!(
            !batch(&resumed, &input, mode)
                .arg("--resume")
                .status()
                .unwrap()
                .success()
        );
        fs::write(resumed.join("replicate-00.psmc"), &kept).unwrap();
        assert!(
            batch(&resumed, &input, mode)
                .args(["--resume", "--workers", "2", "--task-order", "reverse"])
                .status()
                .unwrap()
                .success()
        );
        for i in 0..8 {
            for suffix in ["psmc", "draws.jsonl"] {
                let name = format!("replicate-{i:02}.{suffix}");
                assert_eq!(
                    fs::read(baseline.join(&name)).unwrap(),
                    fs::read(resumed.join(&name)).unwrap(),
                    "{mode}: {name}"
                );
            }
        }
        assert_eq!(kept, fs::read(resumed.join("replicate-00.psmc")).unwrap());
        // A completed resume is safe and does not hang the helper pool.
        assert!(
            batch(&resumed, &input, mode)
                .arg("--resume")
                .status()
                .unwrap()
                .success()
        );
    }
}
#[test]
fn progress_does_not_change_output() {
    let run = |progress: bool| {
        let mut cmd = Command::new(binary());
        cmd.args([
            "--mode",
            "strict",
            "--record-workers",
            "1",
            "--seed",
            "42",
            "-N",
            "2",
        ]);
        if progress {
            cmd.arg("--progress");
        }
        cmd.arg(fixture("workload.psmcfa")).output().unwrap()
    };
    let plain = run(false);
    let progress = run(true);
    assert!(plain.status.success() && progress.status.success());
    assert_eq!(plain.stdout, progress.stdout);
    assert!(
        String::from_utf8(progress.stderr)
            .unwrap()
            .contains("completed iteration 2/2")
    );
}

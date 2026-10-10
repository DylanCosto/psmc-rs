#!/usr/bin/env python3
"""Bounded single-fit timing comparison; default prints the plan without running it."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import statistics

from common import ROOT, timed_run
from phase1_build import sha256, source_hashes

REPORT = Path("bench/phase-1-benchmark.json")
VERSION_PREFIX = b"MM\tVersion: "
ARGS23 = ["-p", "4+5*3+4", "-N", "30", "-t", "15", "-r", "4", "-I", "0"]


def plan() -> dict:
    workload = json.loads(Path("bench/workload.json").read_text())
    profile = json.loads(Path("bench/profile.json").read_text())
    return {
        "scope": "synthetic single-fit diagnostics only; no acceleration or real-workload claim",
        "build_record_required": "bench/phase-1-build.json",
        "warmups_per_backend_per_case": 1, "measured_repetitions_per_backend_per_case": 3,
        "execution": "one process at a time; alternate C/Rust ordering between measured repetitions",
        "timeout_seconds_per_process": 180,
        "cases": [
            {"id": "unsplit-k23-n30", "states": 23, "iterations": 30, "arguments": ARGS23,
             "input": workload["input"]["file"], "input_sha256": workload["input"]["sha256"]},
            {"id": "profile-k64-n5", "states": 64, "iterations": 5, "arguments": profile["arguments"],
             "input": profile["fixture"]["file"], "input_sha256": profile["fixture"]["sha256"]},
        ],
        "output_contract": "Byte equality after excluding exactly one MM\\tVersion: line; every other byte retained. Finite numerical records except initial RI inf.",
    }


def normalized(path: Path) -> bytes:
    lines = path.read_bytes().splitlines(keepends=True)
    version_lines = [line for line in lines if line.startswith(VERSION_PREFIX)]
    if len(version_lines) != 1:
        raise ValueError("Expected exactly one explicitly excluded program/version line")
    return b"".join(line for line in lines if not line.startswith(VERSION_PREFIX))


def save(report: dict) -> None:
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="execute after build and differential validation are ready")
    args = parser.parse_args()
    os.chdir(ROOT)
    protocol = plan()
    if not args.run:
        print(json.dumps({"status": "not_run", **protocol}, indent=2))
        return 0
    build_path = Path(protocol["build_record_required"])
    if not build_path.is_file():
        raise SystemExit("Run bench/phase1_build.py after source edits finish, before measuring.")
    build = json.loads(build_path.read_text())
    binaries = {"vanilla": build["reference_binary"], "rust": build["rust_binary"]}
    if build["source_sha256"] != source_hashes():
        raise SystemExit("Sources have changed since the recorded release build; rebuild first.")
    for binary in binaries.values():
        if sha256(Path(binary["file"])) != binary["sha256"]:
            raise SystemExit("An executable differs from the recorded release build; rebuild first.")
    for case in protocol["cases"]:
        if sha256(Path(case["input"])) != case["input_sha256"]:
            raise SystemExit(f"Input hash mismatch: {case['input']}")
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    raw = Path("bench/phase-1-benchmark/raw") / stamp
    raw.mkdir(parents=True)
    excluded_env = sorted(k for k in os.environ if k.startswith("PSMC_"))
    env = {k: v for k, v in os.environ.items() if not k.startswith("PSMC_")}
    env["LC_ALL"] = "C"
    report = {
        "schema_version": 1, "status": "running", "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "protocol": protocol, "build_record": str(build_path), "build_record_sha256": sha256(build_path),
        "binaries": binaries, "raw_directory": str(raw), "removed_environment_variable_names": excluded_env,
        "timer": {"wall": "time.perf_counter around process launch through blocking waitpid and output closure",
                  "cpu_and_memory": "/usr/bin/time: user/system seconds and Linux maximum RSS in KiB",
                  "warmups_included_in_summary": False, "instrumentation": "none in either inference executable"},
        "cases": [], "speedup_claim": None,
        "limitations": ["Synthetic inputs; no biological-validation or production-throughput claim.",
                        "The K64 profile runs only 5 iterations; it is not a full-fit runtime estimate.",
                        "One process at a time; the user's already-parallel 30-bootstrap workflow is not measured here.",
                        "Shared host, no CPU isolation or governor changes; load averages are recorded per run.",
                        "Whole-genome input, optimized CPU, CUDA, and tenfold acceleration remain not_run/unproven.",
                        "Three repetitions describe local variability but do not establish portable performance."],
        "runner": {"file": "bench/phase1_benchmark.py", "sha256": sha256(Path("bench/phase1_benchmark.py")),
                   "shared_timer_sha256": sha256(Path("bench/common.py"))},
    }
    save(report)
    for case in protocol["cases"]:
        entry = {**case, "runs": [], "status": "running"}
        report["cases"].append(entry)
        canonical = None
        sequence = [("warmup", 0, ["vanilla", "rust"])] + [
            ("measured", i + 1, ["vanilla", "rust"] if i % 2 == 0 else ["rust", "vanilla"])
            for i in range(3)]
        failed = False
        for kind, repetition, order in sequence:
            for backend in order:
                cmd = [binaries[backend]["file"], *case["arguments"], case["input"]]
                outbase = raw / f"{case['id']}-{kind}-{repetition}-{backend}"
                load = list(os.getloadavg())
                try:
                    result = timed_run(cmd, ROOT / outbase, env=env,
                                       timeout=protocol["timeout_seconds_per_process"])
                    content = normalized(Path(result["output"]))
                    if canonical is None:
                        canonical = content
                    result.update({"backend": backend, "kind": kind, "repetition": repetition,
                                   "load_average_before": load,
                                   "normalized_output_sha256": hashlib.sha256(content).hexdigest(),
                                   "matches_c_warmup_after_version_exclusion": content == canonical,
                                   "finite_after_expected_initial_RI": not result["nonfinite_records_beyond_initial_RI"],
                                   "iteration_count_matches": len(result["optimizer_evaluations"]) == case["iterations"]})
                    result["passed"] = (result["exit_code"] == 0 and content == canonical
                                        and result["finite_after_expected_initial_RI"] and result["iteration_count_matches"])
                except (TimeoutError, ValueError, OSError) as exc:
                    result = {"backend": backend, "kind": kind, "repetition": repetition,
                              "passed": False, "error": str(exc).replace(str(ROOT), "${PROJECT}"),
                              "command": cmd, "output_base": str(outbase), "load_average_before": load}
                entry["runs"].append(result)
                failed = failed or not result["passed"]
                save(report)
            if failed:
                # Keep every failed artifact; no timing summary is promoted for a failed pair.
                break
        entry["status"] = "failed" if failed else "passed"
        if not failed:
            entry["summary"] = {}
            for backend in binaries:
                runs = [r for r in entry["runs"] if r["backend"] == backend and r["kind"] == "measured"]
                entry["summary"][backend] = {
                    "measured_repetitions": len(runs),
                    "median_wall_seconds": statistics.median(r["wall_seconds"] for r in runs),
                    "min_wall_seconds": min(r["wall_seconds"] for r in runs),
                    "max_wall_seconds": max(r["wall_seconds"] for r in runs),
                    "median_user_seconds": statistics.median(r["user_seconds"] for r in runs),
                    "median_system_seconds": statistics.median(r["system_seconds"] for r in runs),
                    "median_peak_rss_kib": statistics.median(r["peak_rss_kib"] for r in runs),
                    "max_peak_rss_kib": max(r["peak_rss_kib"] for r in runs),
                }
        save(report)
    unchanged = (source_hashes() == build["source_sha256"] and all(
        sha256(Path(binary["file"])) == binary["sha256"] for binary in binaries.values()))
    report["sources_and_binaries_unchanged_after_runs"] = unchanged
    report["status"] = "passed_synthetic_single_fit_checks" if unchanged and all(
        case["status"] == "passed" for case in report["cases"]) else "failed"
    report["completed_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    save(report)
    print(json.dumps({"status": report["status"], "report": str(REPORT),
                      "summaries": {c["id"]: c.get("summary") for c in report["cases"]}}, indent=2))
    return 0 if report["status"] == "passed_synthetic_single_fit_checks" else 1


if __name__ == "__main__":
    raise SystemExit(main())

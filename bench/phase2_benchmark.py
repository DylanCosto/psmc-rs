#!/usr/bin/env python3
"""Frozen-binary single-fit and equal-worker batch timings; dry-run by default.

No rebuilding, profiling, snapshot output, or correctness suite may run concurrently.
The 30-fit batch has three known reference pathologies and is mechanics-only.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import statistics
import threading
import time

from common import ROOT, save, sha256, timed_run
from phase1_differential import compare_output, strict_output
from phase2_common import clean_env, relative, utc_stamp, verify_binaries

ARGS23 = ["-p", "4+5*3+4", "-N", "30", "-t", "15", "-r", "4", "-I", "0"]


class ChildMemory:
    """Sample summed resident memory of this runner's children, excluding itself.

    Linux /proc RSS, including the /usr/bin/time wrappers. Sampling is not a
    proof of the true peak; all child maximum-RSS measurements are retained too.
    """
    def __init__(self):
        self.stop = threading.Event()
        self.peak = 0
        self.samples = 0
        self.thread = threading.Thread(target=self.sample, daemon=True)

    def sample(self):
        while not self.stop.is_set():
            descendants, pending = [], [os.getpid()]
            while pending:
                pid = pending.pop()
                try:
                    children = sorted({int(value) for task in Path(f"/proc/{pid}/task").glob("*/children")
                                       for value in task.read_text().split()})
                except (FileNotFoundError, ProcessLookupError):
                    children = []
                descendants += children
                pending += children
            total = 0
            for pid in descendants:
                try:
                    for line in Path(f"/proc/{pid}/status").read_text().splitlines():
                        if line.startswith("VmRSS:"):
                            total += int(line.split()[1])
                            break
                except (FileNotFoundError, ProcessLookupError):
                    pass
            self.peak = max(self.peak, total)
            self.samples += 1
            self.stop.wait(0.01)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *unused):
        self.stop.set()
        self.thread.join()

    def record(self):
        return {"sampled_peak_sum_child_rss_kib": self.peak, "samples": self.samples,
                "sampling_interval_seconds": 0.01, "method": "Linux /proc sum of resident memory for live child process tree, including /usr/bin/time; runner excluded; sampled lower bound on true peak"}


def batch_exit_status(runs):
    """Any abnormal child exit fails a batch, including a negative signal code."""
    if not runs:
        return 1
    return next((run["exit_code"] for run in runs if run["exit_code"] != 0), 0)


def worker_comparison(manifest, requested, replicates):
    """A memory-admission reduction must not masquerade as an equal-worker run."""
    expected = min(requested, replicates)
    return {"requested_workers": requested, "expected_active_workers": expected,
            "manifest_requested_workers": manifest.get("requested_workers"),
            "admitted_workers": manifest.get("workers"),
            "equal_worker_budget": (manifest.get("requested_workers") == requested
                                    and manifest.get("workers") == expected)}


def summarize(runs):
    measured = [run for run in runs if run["kind"] == "measured"]
    return {"repetitions": len(measured),
            "median_wall_seconds": statistics.median(run["wall_seconds"] for run in measured),
            "min_wall_seconds": min(run["wall_seconds"] for run in measured),
            "max_wall_seconds": max(run["wall_seconds"] for run in measured),
            "median_sampled_peak_sum_child_rss_kib": statistics.median(run["memory"]["sampled_peak_sum_child_rss_kib"] for run in measured),
            "median_peak_rss_kib": statistics.median(run["peak_rss_kib"] for run in measured) if all("peak_rss_kib" in run for run in measured) else None}


def canonical_bootstraps(validation):
    return {rep: (ROOT / validation["run_directory"] / "cpu-raw" / f"K23_N30_bootstrap_{rep:02d}-oracle.psmc").read_bytes() for rep in range(30)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--validation", default="bench/phase-2-validation.json")
    parser.add_argument("--report", default="bench/phase-2-benchmark.json")
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--batch-repetitions", type=int, default=3)
    parser.add_argument("--workers", default="1,2,4")
    subset = parser.add_mutually_exclusive_group()
    subset.add_argument("--single-only", action="store_true")
    subset.add_argument("--batch-only", action="store_true")
    options = parser.parse_args()
    if options.repetitions < 1 or options.batch_repetitions < 1:
        parser.error("Repetition counts must be positive")
    os.chdir(ROOT)
    workers = [int(item) for item in options.workers.split(",")]
    if any(item < 1 for item in workers) or len(set(workers)) != len(workers):
        parser.error("Workers must be unique positive integers")
    profile = json.loads((ROOT / "bench/profile.json").read_text())
    cases = [{"id": "unsplit-k23-n30", "input": "tests/fixtures/workload.psmcfa", "arguments": ARGS23},
             {"id": "profile-k64-n5", "input": profile["fixture"]["file"], "arguments": profile["arguments"]}]
    protocol = {"scope": "Local synthetic CPU engineering diagnostics; no production or tenfold claim", "single_cases": cases,
                "single_implementations": ["vanilla", "phase1", "dense", "cpu"],
                "single_repetitions": options.repetitions, "batch_repetitions": options.batch_repetitions,
                "warmups_per_case_per_implementation": 1, "ordering": "Rotate implementation order between repetitions; every command uninstrumented",
                "batch_workers": workers, "batch": "Same 30 materialized-equivalent K23/N30 fits, same worker count for C processes and Rust threads; 27 finite and 3 retained pathologies, mechanics-only timing",
                "memory": "Per-process Linux maximum RSS and 10ms sampled summed child-tree RSS; sampled sum includes time wrappers and excludes Python harness",
                "single_only": options.single_only, "batch_only": options.batch_only}
    if not options.run:
        print(json.dumps({"status": "not_run", "protocol": protocol}, indent=2))
        return 0
    validation = json.loads((ROOT / options.validation).read_text())
    if validation["status"] != "passed":
        raise SystemExit("A completed passing Phase 2 validation is required before timing")
    provenance = validation["provenance"]
    verify_binaries(provenance)
    raw = ROOT / "bench/phase-2-benchmark" / utc_stamp()
    raw.mkdir(parents=True)
    report = {"schema_version": 1, "status": "running", "protocol": protocol, "provenance": provenance,
              "validation_report": options.validation, "validation_sha256": sha256(ROOT / options.validation),
              "raw_directory": relative(raw), "single_cases": [], "batches": [], "failures": [],
              "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "runner_sha256": sha256(Path(__file__)),
              "removed_environment_variable_names": sorted(key for key in os.environ if key.startswith("PSMC_")),
              "limitations": ["Shared host, no CPU isolation or governor changes; load averages recorded.", "Synthetic inputs and few repetitions do not establish portable performance.", "The user's real inputs, preprocessing, settings and worker budget remain unavailable.", "K64/N5 is a partial trajectory; the 30-fit batch contains three reference pathologies.", "Process parallelism is compared at equal worker counts and reported separately from single-fit improvement.", "No CUDA or equivalent-mode inference tested."]}
    save(ROOT / options.report, report)
    binaries = provenance["binaries"]
    commands = {"vanilla": [binaries["vanilla"]["path"]], "phase1": [binaries["phase1"]["path"]],
                "dense": [binaries["candidate"]["path"], *validation["backend_arguments"]["dense"]],
                "cpu": [binaries["candidate"]["path"], *validation["backend_arguments"]["cpu"]]}
    env = clean_env()
    if not options.batch_only:
        for case in cases:
            entry = {**case, "input_sha256": sha256(ROOT / case["input"]), "runs": []}
            report["single_cases"].append(entry)
            canonical = None
            names = list(commands)
            for repetition in range(options.repetitions + 1):
                kind = "warmup" if repetition == 0 else "measured"
                order = names[repetition % len(names):] + names[:repetition % len(names)]
                for name in order:
                    verify_binaries(provenance)
                    if sha256(ROOT / case["input"]) != entry["input_sha256"]:
                        raise RuntimeError("Single-fit input changed during measurement")
                    command = commands[name] + case["arguments"] + [case["input"]]
                    before = list(os.getloadavg())
                    with ChildMemory() as memory:
                        result = timed_run(command, raw / f"{case['id']}-{kind}-{repetition}-{name}", env=env)
                    output = (ROOT / result["output"]).read_bytes()
                    if canonical is None:
                        canonical = output
                    try:
                        equality = compare_output(canonical, output)
                        passed = (result["exit_code"] == 0 and not result["nonfinite_records_beyond_initial_RI"])
                    except AssertionError as error:
                        equality, passed = {"error": str(error)}, False
                    result.update({"implementation": name, "kind": kind, "repetition": repetition, "memory": memory.record(),
                                   "load_average_before": before, "comparison": equality, "passed": passed})
                    entry["runs"].append(result)
                    if not passed:
                        report["failures"].append({"case": case["id"], "implementation": name, "kind": kind, "repetition": repetition})
                    save(ROOT / options.report, report)
            entry["summary"] = {name: summarize([run for run in entry["runs"] if run["implementation"] == name]) for name in names}
            if not any(failure.get("case") == case["id"] for failure in report["failures"]):
                entry["wall_ratios"] = {"phase1_over_cpu": entry["summary"]["phase1"]["median_wall_seconds"] / entry["summary"]["cpu"]["median_wall_seconds"],
                                        "vanilla_over_cpu": entry["summary"]["vanilla"]["median_wall_seconds"] / entry["summary"]["cpu"]["median_wall_seconds"],
                                        "dense_over_cpu": entry["summary"]["dense"]["median_wall_seconds"] / entry["summary"]["cpu"]["median_wall_seconds"]}
            save(ROOT / options.report, report)
    if not options.single_only:
        canonical = canonical_bootstraps(validation)
        workload = json.loads((ROOT / "bench/workload.json").read_text())
        replicates = workload["bootstrap"]["replicates"]
        block_hash = sha256(ROOT / "tests/fixtures/blocks.psmcfa")
        report["batch_input_sha256"] = {rep["file"]: rep["sha256"] for rep in replicates}
        report["batch_input_sha256"]["tests/fixtures/blocks.psmcfa"] = block_hash
        for count in workers:
            entry = {"workers": count, "scope": "27 finite + 3 pathological reference trajectories; mechanics-only", "runs": []}
            report["batches"].append(entry)
            for repetition in range(options.batch_repetitions + 1):
                kind = "warmup" if repetition == 0 else "measured"
                order = ["vanilla", "cpu"] if repetition % 2 == 0 else ["cpu", "vanilla"]
                for name in order:
                    verify_binaries(provenance)
                    for file, expected in report["batch_input_sha256"].items():
                        if sha256(ROOT / file) != expected:
                            raise RuntimeError(f"Bootstrap input changed: {file}")
                    base = raw / f"batch-w{count}-{kind}-{repetition}-{name}"
                    before = list(os.getloadavg())
                    with ChildMemory() as memory:
                        if name == "vanilla":
                            start = time.perf_counter()
                            def run_rep(rep):
                                return timed_run(commands[name] + ARGS23 + [rep["file"]], base / f"replicate-{rep['id']:02d}", env=env)
                            with ThreadPoolExecutor(max_workers=count) as pool:
                                individual = list(pool.map(run_rep, replicates))
                            elapsed = time.perf_counter() - start
                            result = {"wall_seconds": elapsed, "exit_code": batch_exit_status(individual),
                                      "replicate_runs": individual, "command_policy": "Bounded independent vanilla processes over the exact materialized replicate files"}
                            outputs = [(ROOT / run["output"]).read_bytes() for run in individual]
                        else:
                            directory = Path(str(base) + "-outputs")
                            command = [binaries["candidate"]["path"], "bootstrap", "--replicates", "30", "--workers", str(count),
                                       "--seed", "20261009", "--output-dir", relative(directory), "--memory-mib", "2048",
                                       *validation["backend_arguments"]["cpu"], *ARGS23, "tests/fixtures/blocks.psmcfa"]
                            result = timed_run(command, base, env=env, timeout=600)
                            outputs = [(directory / f"replicate-{rep:02d}.psmc").read_bytes() for rep in range(30)] if result["exit_code"] == 0 else []
                            result["manifest"] = relative(directory / "manifest.json")
                            if result["exit_code"] == 0:
                                manifest = json.loads((directory / "manifest.json").read_text())
                                result["worker_comparison"] = worker_comparison(manifest, count, len(replicates))
                    differences = []
                    for rep, output in enumerate(outputs):
                        try:
                            compare_output(canonical[rep], output)
                        except AssertionError as error:
                            differences.append({"replicate": rep, "error": str(error)})
                    passed = (result["exit_code"] == 0 and len(outputs) == 30 and not differences
                              and (name == "vanilla" or result.get("worker_comparison", {}).get("equal_worker_budget", False)))
                    result.update({"implementation": name, "kind": kind, "repetition": repetition, "memory": memory.record(),
                                   "load_average_before": before, "outputs_compared": len(outputs), "differences": differences, "passed": passed})
                    entry["runs"].append(result)
                    if not passed:
                        report["failures"].append({"batch_workers": count, "implementation": name, "kind": kind, "repetition": repetition})
                    save(ROOT / options.report, report)
            entry["summary"] = {name: summarize([run for run in entry["runs"] if run["implementation"] == name]) for name in ("vanilla", "cpu")}
            if not any(failure.get("batch_workers") == count for failure in report["failures"]):
                entry["equal_worker_wall_ratio_vanilla_over_cpu"] = entry["summary"]["vanilla"]["median_wall_seconds"] / entry["summary"]["cpu"]["median_wall_seconds"]
            save(ROOT / options.report, report)
    verify_binaries(provenance)
    for case in report["single_cases"]:
        if sha256(ROOT / case["input"]) != case["input_sha256"]:
            report["failures"].append({"kind": "single_input_changed", "input": case["input"]})
    for file, expected in report.get("batch_input_sha256", {}).items():
        if sha256(ROOT / file) != expected:
            report["failures"].append({"kind": "batch_input_changed", "input": file})
    report["status"] = "failed" if report["failures"] else "passed_synthetic_timing_checks"
    report["completed_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    save(ROOT / options.report, report)
    print(json.dumps({"status": report["status"], "report": options.report,
                      "single": {case["id"]: case.get("wall_ratios") for case in report["single_cases"]},
                      "batches": {batch["workers"]: batch.get("equal_worker_wall_ratio_vanilla_over_cpu") for batch in report["batches"]}}, indent=2))
    return bool(report["failures"])


if __name__ == "__main__":
    raise SystemExit(main())

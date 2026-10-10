#!/usr/bin/env python3
"""Measure identical 30 materialized bootstraps under bounded vanilla concurrency."""
import concurrent.futures
import json
import os
import platform
import statistics
import subprocess
import time
from common import ROOT, save, sha256, timed_run

def info(command):
    try:
        r = subprocess.run(command, text=True, capture_output=True, timeout=15)
        return {"command": command, "exit_code": r.returncode, "stdout": r.stdout, "stderr": r.stderr}
    except Exception as error:
        return {"command": command, "error": str(error)}

def main():
    workload = json.loads((ROOT / "bench/workload.json").read_text())
    config = workload["benchmark"]
    iterations = int(config["arguments"][config["arguments"].index("-N")+1])
    reps = workload["bootstrap"]["replicates"]
    env = os.environ.copy()
    for key in list(env):
        if key.startswith("PSMC_"):
            del env[key]
    for rep in reps:
        assert sha256(ROOT / rep["file"]) == rep["sha256"], "Materialized input changed"
    hardware = {"platform": platform.platform(), "cpu_count_logical": os.cpu_count(),
                "cpu_affinity": sorted(os.sched_getaffinity(0)), "load_average_before": os.getloadavg(),
                "lscpu": info(["lscpu", "-J"]), "memory": info(["free", "-b"]),
                "gpu": info(["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv"]),
                "nvcc": info(["nvcc", "--version"]), "rust": info(["rustc", "--version"]),
                "perf_event_paranoid": open("/proc/sys/kernel/perf_event_paranoid").read().strip()}
    save(ROOT / "bench/environment.json", hardware)
    build = json.loads((ROOT / "reference/build-vanilla.json").read_text())
    assert sha256(ROOT / config["binary"]) == build["executables"]["psmc"]["sha256"]
    # One explicitly excluded warm-up; no tuned or accelerated binary exists.
    warmup = timed_run([config["binary"], *config["arguments"], reps[0]["file"]], ROOT/"bench/raw/baseline/warmup", env=env)
    assert warmup["exit_code"] == 0 and not warmup["nonfinite_records_beyond_initial_RI"], "Invalid warmup"
    batches = []
    # Rotate order across three rounds to reduce monotone time/order confounding.
    worker_orders = [[1,2,4], [4,1,2], [2,4,1]]
    expected = None
    for round_id, order in enumerate(worker_orders):
        for workers in order:
            start = time.perf_counter()
            def fit(rep):
                return timed_run([config["binary"], *config["arguments"], rep["file"]], ROOT/f"bench/raw/baseline/round-{round_id}-workers-{workers}/replicate-{rep['id']:02d}", env=env)
            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
                runs = list(pool.map(fit, reps)) # ordered by manifest; original processes remain independent
            elapsed = time.perf_counter()-start
            hashes = [x["output_sha256"] for x in runs]
            if expected is None:
                expected = hashes
            parity = hashes == expected
            passed = parity and all(x["exit_code"] == 0 and len(x["optimizer_evaluations"]) == iterations and not x["nonfinite_records_beyond_initial_RI"] for x in runs)
            batch = {"round": round_id, "workers": workers, "wall_seconds": elapsed,
                "status": "passed" if passed else "failed", "ordered_output_hashes_match": parity,
                "max_individual_peak_rss_kib": max(x["peak_rss_kib"] for x in runs),
                "conservative_concurrent_peak_rss_upper_bound_kib": workers*max(x["peak_rss_kib"] for x in runs),
                "runs": runs}
            batches.append(batch)
            save(ROOT / "bench/raw/baseline/progress.json", batches)
            print(json.dumps({key:batch[key] for key in ["round","workers","wall_seconds","status"]}), flush=True)
            if not passed:
                save(ROOT / "bench/baseline.json", {"status": "failed", "reason": "Invalid reference outputs or parity/iteration mismatch", "raw_runs": "bench/raw/baseline/progress.json", "performance_claim": None})
                raise RuntimeError("Benchmark gate failed; raw evidence saved. Investigate before rerun.")
    summaries = []
    for workers in [1,2,4]:
        subset = [x for x in batches if x["workers"] == workers]
        times = [x["wall_seconds"] for x in subset]
        summaries.append({"workers": workers, "batch_wall_seconds": times, "median_batch_wall_seconds": statistics.median(times),
             "min_batch_wall_seconds": min(times), "max_batch_wall_seconds": max(times),
             "max_individual_peak_rss_kib": max(x["max_individual_peak_rss_kib"] for x in subset)})
    single_runs = [timed_run([config["binary"], *config["arguments"], workload["input"]["file"]], ROOT/f"bench/raw/baseline/single-fit-{i}", env=env) for i in range(3)]
    assert all(x["exit_code"] == 0 and not x["nonfinite_records_beyond_initial_RI"] and len(x["optimizer_evaluations"]) == iterations for x in single_runs), "Invalid single-fit reference outputs"
    serial = summaries[0]["median_batch_wall_seconds"]
    for item in summaries:
        item["ordinary_parallelism_ratio_to_serial"] = serial/item["median_batch_wall_seconds"]
    save(ROOT / "bench/baseline.json", {
        "schema_version": 1, "scope": "five-iteration partial-trajectory synthetic smoke; full30 bootstrap reference FAILED; no accelerated engine exists",
        "status": "partial_trajectory_smoke_passed_full_gate_failed" if all(x["status"] == "passed" for x in batches) else "failed",
        "source_commit": build["source_commit"], "build_record": "reference/build-vanilla.json",
        "executable_sha256": sha256(ROOT/config["binary"]), "workload_manifest_sha256": sha256(ROOT/"bench/workload.json"),
        "protocol": {"replicates_per_batch": 30, "measured_batches": len(batches), "iterations_per_fit": iterations,
           "workers": [1,2,4], "repetitions_per_worker_count": 3, "worker_order": worker_orders,
           "warmups": 1, "clock": "Python time.perf_counter with blocking waitpid and separate deadline watchdog; /usr/bin/time for child elapsed, CPU and peak RSS",
           "scope": config["timed_scope"], "process_parallelism": "bounded independent vanilla processes",
           "affinity": "unconstrained within existing affinity mask", "reduction_changes": "none",
           "machine_isolation": "not exclusive; existing user processes may affect measurements",
           "bootstrap_materialization": "outside fit timer; inputs identical by digest in every run",
           "memory": "per-process peak RSS measured; concurrent peak not sampled; worker*max individual RSS is a conservative bound excluding Python scheduler",
           "raw_runs": "bench/raw/baseline/progress.json"},
        "summaries": summaries, "single_fit": {"runs": single_runs, "median_wall_seconds": statistics.median(x["wall_seconds"] for x in single_runs)},
        "determinism": {"all_270_output_hashes_match_their_replicate": all(x["ordered_output_hashes_match"] for x in batches),
                        "expected_iterations_per_fit": iterations,
                        "all_fits_executed_expected_iterations": all(len(r["optimizer_evaluations"]) == iterations for b in batches for r in b["runs"]),
                        "all_fits_finite_beyond_expected_initial_RI": all(not r["nonfinite_records_beyond_initial_RI"] for b in batches for r in b["runs"])},
        "real_workload": {"status": "not_run", "bootstrap_processes_already_parallel": True, "missing": workload["real_workload"]["missing"]},
        "accelerated_cpu": {"status": "not_run", "reason": "Phase 1+ not started"},
        "legacy_cuda": {"status": "not_run", "reason": "No legacy CUDA backend; physical GPU available"},
        "phlash": {"record": "bench/phlash.json", "output_equivalent": False},
        "performance_claim": None, "target_10x": "unproven",
        "prior_failed_fixture": "bench/failed-23state.json",
        "full_30_iteration_bootstrap_gate": {"status": "failed", "record": "bench/failed-23state.json", "reason": "Three vanilla reference replicates develop nonfinite values; shortened smoke does not resolve this"},
        "limitations": ["Five-iteration partial trajectory; prior30-iteration23-state reference failed with nonfinite values and is separately retained", "Synthetic data much smaller than a genome", "User's original concurrency and arguments unknown", "No claim of optimal original concurrency", "Serial ratio measures ordinary scheduling only; user's workflow already parallel", "No predictive real-workload or GPU speedup"]
    })
    print(json.dumps({"summaries": summaries}))

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Strict bootstrap scheduler order/worker and cache controls; no timing claims."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import subprocess

from common import ROOT, save, sha256
from phase1_differential import compare_output
from phase2_benchmark import ARGS23, canonical_bootstraps
from phase2_common import clean_env, relative, utc_stamp, verify_binaries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--validation", default="bench/phase-3-validation.json")
    parser.add_argument("--report", default="bench/phase-3-scheduler.json")
    parser.add_argument("--workers", default="1")
    options = parser.parse_args()
    os.chdir(ROOT)
    from phase3_common import resource_policy
    policy = resource_policy()
    workers = [int(item) for item in options.workers.split(",")]
    if workers != [1]:
        parser.error("Phase 3a resource policy permits only --workers 1")
    protocol = {"scope": "Deterministic scheduling of identical independent legacy bootstrap fits",
                "worker_counts": workers, "task_orders": ["forward", "reverse"], "replicates": 30,
                "arguments": ARGS23, "seed_base": 20261009, "memory_mib": 2048,
                "comparison": "All numerical output bytes and all non-version metadata equal to pinned vanilla materialized replicate; 27 finite, 3 retained reference pathologies",
                "cache_control": "Non-snapshot CPU fit must visit every occurrence, reuse exact repeated-block statistics, and count every repeated addition. Snapshot fit bypasses the counts cache to emit full messages.",
                "timing": "not a benchmark; timing suite runs separately"}
    if not options.run:
        print(json.dumps({"status": "not_run", "protocol": protocol}, indent=2))
        return 0
    validation = json.loads((ROOT / options.validation).read_text())
    if validation["status"] != "passed":
        raise SystemExit("Complete passing Phase 3a validation required")
    provenance = validation["provenance"]
    verify_binaries(provenance)
    canonical = canonical_bootstraps(validation)
    workload = json.loads((ROOT / "bench/workload.json").read_text())
    expected_replicates = workload["bootstrap"]["replicates"]
    raw = ROOT / "bench/phase-3-scheduler" / utc_stamp()
    raw.mkdir(parents=True)
    report = {"schema_version": 1, "status": "running", "resource_policy": policy, "protocol": protocol, "provenance": provenance,
              "validation_sha256": sha256(ROOT / options.validation), "run_directory": relative(raw),
              "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "runner_sha256": sha256(Path(__file__)),
              "runs": [], "cache_controls": [], "failures": []}
    save(ROOT / options.report, report)
    binary = provenance["binaries"]["candidate"]["path"]
    for count in workers:
        for order in protocol["task_orders"]:
            verify_binaries(provenance)
            directory = raw / f"workers-{count}-{order}"
            command = [binary, "bootstrap", "--replicates", "30", "--workers", str(count),
                       "--seed", "20261009", "--output-dir", relative(directory), "--memory-mib", "2048",
                       "--task-order", order, *validation["backend_arguments"]["cpu"], *ARGS23,
                       "tests/fixtures/blocks.psmcfa"]
            result = subprocess.run(command, cwd=ROOT, env=clean_env(), capture_output=True, timeout=600)
            (raw / f"workers-{count}-{order}.stdout").write_bytes(result.stdout)
            (raw / f"workers-{count}-{order}.stderr").write_bytes(result.stderr)
            entry = {"workers": count, "task_order": order, "command": command, "returncode": result.returncode,
                     "directory": relative(directory), "comparisons": [], "failures": []}
            if result.returncode:
                entry["failures"].append({"kind": "exit", "diagnostic": result.stderr.decode(errors="replace")})
            else:
                manifest_path = directory / "manifest.json"
                if manifest_path.is_file():
                    manifest = json.loads(manifest_path.read_text())
                    entry["manifest"] = {"path": relative(manifest_path), "sha256": sha256(manifest_path), "contents": manifest}
                    try:
                        assert manifest["backend"] == "cpu"
                        assert manifest["requested_workers"] == count
                        assert manifest["workers"] == count == 1
                        assert (manifest["input_bytes"] + manifest["estimated_metadata_bytes"]
                                + manifest["estimated_worker_bytes"] * manifest["workers"] <= manifest["memory_mib"] * 1024 * 1024)
                        assert manifest["seed"] == 20261009
                        assert len(manifest["replicates"]) == 30
                        for actual, expected in zip(manifest["replicates"], expected_replicates):
                            assert actual["index"] == expected["id"]
                            assert actual["seed"] == expected["seed"]
                            assert actual["source_indices"] == expected["ordered_block_indices"]
                            assert actual["length"] == expected["raw_length_bins"]
                            assert Path(actual["output"]).name == f"replicate-{expected['id']:02d}.psmc"
                            assert Path(actual["stats"]).name == f"replicate-{expected['id']:02d}.stats.json"
                        entry["manifest_sampling_and_budget_match"] = True
                    except (AssertionError, KeyError, TypeError) as error:
                        entry["failures"].append({"kind": "manifest_sampling_or_budget", "error": str(error)})
                else:
                    entry["failures"].append({"kind": "missing_manifest"})
                for rep in range(30):
                    path = directory / f"replicate-{rep:02d}.psmc"
                    try:
                        comparison = compare_output(canonical[rep], path.read_bytes())
                        entry["comparisons"].append({"replicate": rep, "output_sha256": sha256(path), **comparison})
                    except (AssertionError, OSError) as error:
                        entry["failures"].append({"replicate": rep, "error": str(error)})
                stats = sorted(directory.glob("*.json"))
                entry["stats_files"] = [{"path": relative(path), "sha256": sha256(path), "contents": json.loads(path.read_text())} for path in stats if path.name != "manifest.json"]
                try:
                    assert len(entry["stats_files"]) == 30, "Expected one stats record per replicate"
                    for record, expected in zip(entry["stats_files"], expected_replicates):
                        value = record["contents"]
                        visits = 30 * len(expected["ordered_block_indices"])
                        unique = 30 * len(set(expected["ordered_block_indices"]))
                        assert value["backend"] == "cpu"
                        assert value["simd_selected"] == "avx" and value["simd_requested"] == "auto"
                        assert value["sequence_visits"] == visits
                        assert value["sequence_evaluations"] == unique
                        assert value["cache_hits"] == visits - unique
                        assert not value["snapshot_cache_bypass"]
                    total_visits = sum(record["contents"]["sequence_visits"] for record in entry["stats_files"])
                    total_hits = sum(record["contents"]["cache_hits"] for record in entry["stats_files"])
                    entry["cache_summary"] = {"sequence_visits": total_visits, "cache_hits": total_hits,
                                              "hit_fraction": total_hits / total_visits}
                except (AssertionError, KeyError, TypeError) as error:
                    entry["failures"].append({"kind": "per_replicate_cache_accounting", "error": str(error)})
            entry["passed"] = not entry["failures"] and len(entry["comparisons"]) == 30
            report["runs"].append(entry)
            if not entry["passed"]:
                report["failures"].append({"workers": count, "task_order": order, "failures": entry["failures"]})
            save(ROOT / options.report, report)
            print(f"workers={count}, order={order}: {'passed' if entry['passed'] else 'failed'}", flush=True)
    # Explicit single-fit cache accounting over known duplicate blocks. Full snapshot
    # emission on this control must remain an optimized CPU workspace execution.
    for name, snapshot, cache in (("cache-normal", False, "on"), ("cache-off", False, "off"), ("cache-snapshot", True, "on")):
        stats_path = raw / f"{name}.stats.json"
        command = [binary, *validation["backend_arguments"]["cpu"], "--cache", cache, "--stats", relative(stats_path),
                   "-p", "4+5*3+4", "-N", "1", "-I", "0"]
        if snapshot:
            command += ["--snapshot", relative(raw / f"{name}.jsonl")]
        command += ["tests/fixtures/bootstrap/replicate-00.psmcfa"]
        result = subprocess.run(command, cwd=ROOT, env=clean_env(), capture_output=True, timeout=180)
        (raw / f"{name}.psmc").write_bytes(result.stdout)
        (raw / f"{name}.stderr").write_bytes(result.stderr)
        entry = {"snapshot": snapshot, "cache": cache, "command": command, "returncode": result.returncode,
                 "stats_path": relative(stats_path), "stats": json.loads(stats_path.read_text()) if stats_path.is_file() else None}
        report["cache_controls"].append(entry)
        if result.returncode or entry["stats"] is None:
            report["failures"].append({"kind": name, "diagnostic": result.stderr.decode(errors="replace")})
        save(ROOT / options.report, report)
    controls = report["cache_controls"]
    try:
        plain, disabled, snapshot = [entry["stats"] for entry in controls]
        compare_output((raw / "cache-normal.psmc").read_bytes(), (raw / "cache-snapshot.psmc").read_bytes())
        compare_output((raw / "cache-normal.psmc").read_bytes(), (raw / "cache-off.psmc").read_bytes())
        assert plain["backend"] == disabled["backend"] == snapshot["backend"] == "cpu", "Cache controls must use cpu"
        assert disabled["sequence_visits"] == disabled["sequence_evaluations"] == 13 and disabled["cache_hits"] == 0
        assert plain["sequence_visits"] == snapshot["sequence_visits"] == 13, "Every occurrence must be visited"
        assert plain["cache_hits"] == 5 and plain["sequence_evaluations"] == 8, "Expected eight unique blocks and five repeated-block hits"
        assert plain["sequence_evaluations"] + plain["cache_hits"] == plain["sequence_visits"]
        assert snapshot["cache_hits"] == 0 and snapshot["sequence_evaluations"] == snapshot["sequence_visits"]
        assert snapshot["snapshot_cache_bypass"], "Snapshot counts-cache bypass must be explicit"
        report["cache_accounting_passed"] = True
    except (AssertionError, KeyError, TypeError, OSError) as error:
        report["cache_accounting_passed"] = False
        report["failures"].append({"kind": "cache_accounting", "error": str(error)})
    # Preserve the complete selected cache-control trace, compressed without truncation.
    import gzip
    import shutil
    path = raw / "cache-snapshot.jsonl"
    if path.is_file():
        destination = Path(str(path) + ".gz")
        with path.open("rb") as source, gzip.open(destination, "wb", compresslevel=1) as target:
            shutil.copyfileobj(source, target)
        path.unlink()
        report["cache_snapshot"] = {"path": relative(destination), "sha256": sha256(destination)}
    # Random initialization consumes the same stream after resampling. I=0-only
    # scheduler tests would not detect a lost or restarted RNG position here.
    directory = raw / "randomized-bootstrap"
    random_args = ["-p", "4+5*3+4", "-N", "2", "-t", "15", "-r", "4", "-I", "0.1"]
    command = [binary, "bootstrap", "--replicates", "3", "--workers", "1", "--seed", "20261009",
               "--output-dir", relative(directory), "--memory-mib", "2048", "--task-order", "reverse",
               *validation["backend_arguments"]["cpu"], *random_args, "tests/fixtures/blocks.psmcfa"]
    result = subprocess.run(command, cwd=ROOT, env=clean_env(), capture_output=True, timeout=180)
    (raw / "randomized-bootstrap.stdout").write_bytes(result.stdout)
    (raw / "randomized-bootstrap.stderr").write_bytes(result.stderr)
    random_control = {"command": command, "returncode": result.returncode, "comparisons": [], "failures": []}
    if result.returncode:
        random_control["failures"].append({"kind": "exit", "diagnostic": result.stderr.decode(errors="replace")})
    else:
        for rep in range(3):
            env = clean_env()
            env["PSMC_SEED"] = str(20261009 + rep)
            oracle_command = [provenance["binaries"]["instrumented"]["path"], "-b", *random_args, "tests/fixtures/blocks.psmcfa"]
            oracle = subprocess.run(oracle_command, cwd=ROOT, env=env, capture_output=True, timeout=180)
            (raw / f"randomized-oracle-{rep:02d}.psmc").write_bytes(oracle.stdout)
            (raw / f"randomized-oracle-{rep:02d}.stderr").write_bytes(oracle.stderr)
            try:
                assert oracle.returncode == 0
                comparison = compare_output(oracle.stdout, (directory / f"replicate-{rep:02d}.psmc").read_bytes())
                random_control["comparisons"].append({"replicate": rep, "seed": 20261009 + rep,
                                                       "oracle_command": oracle_command, **comparison})
            except (AssertionError, OSError) as error:
                random_control["failures"].append({"replicate": rep, "error": str(error)})
    random_control["passed"] = not random_control["failures"] and len(random_control["comparisons"]) == 3
    report["randomized_bootstrap_control"] = random_control
    if not random_control["passed"]:
        report["failures"].append({"kind": "randomized_bootstrap_stream", "failures": random_control["failures"]})
    verify_binaries(provenance)
    report["status"] = "failed" if report["failures"] else "passed"
    report["completed_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    save(ROOT / options.report, report)
    print(json.dumps({"status": report["status"], "report": options.report, "runs": len(report["runs"]),
                      "cache_accounting_passed": report["cache_accounting_passed"]}, indent=2))
    return bool(report["failures"])


if __name__ == "__main__":
    raise SystemExit(main())

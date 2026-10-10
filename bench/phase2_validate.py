#!/usr/bin/env python3
"""Exact Phase 2 CPU/dense regression against pinned C; default prints the plan.

Reuses the Phase 1 harness unchanged through explicit, hash-guarded wrappers.
No Phase 1 report or raw artifact is overwritten. No speed measurements here.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import sys

from common import ROOT, save, sha256
from phase2_common import freeze, invoke, relative, utc_stamp, verify_binaries, wrapper

DEFAULT_SELECTION = r"^(?!independent_path_enumeration_and_Q$|snapshot_exact_K64_N1$).+"


def plan():
    return {
        "scope": "Phase 2 strict dense and CPU backends versus pinned vanilla C on synthetic fixtures",
        "selection": DEFAULT_SELECTION,
        "output_contract": "Only the single MM Version line excluded; all other bytes exact",
        "snapshot_contract": "Complete ordered events and fields, exact finite binary64 and signed-zero equality; nonfinite class parity separately",
        "included_snapshots": ["tiny_N2", "grid_N1", "K23_N1"],
        "omitted_repeated_snapshots": {
            "independent_path_enumeration_and_Q": "The unchanged model, optimizer and dense oracle retain the Phase 1 exhaustive 100,022-event trace. Phase 2 isolated CPU HMM tests check messages/counts over all state sizes. Full dense/CPU outputs and three complete traces are rerun.",
            "snapshot_exact_K64_N1": "The Phase 1 36,956,397-field model/callback trace is retained. Phase 2 changes HMM memory use, not model/optimizer callbacks. K64 isolated HMM exactness and complete output are rerun; no callback is truncated in the selected snapshots.",
        },
        "bootstrap_gate": "All 30 materialized K23/N30 fits through each backend; require 27 finite and the same 3 retained reference pathologies",
        "timing": "not measured; snapshot runs are correctness diagnostics",
        "scheduler_gate": "Reported separately by bench/phase2_scheduler.py",
        "historical_child_report_labels": "The unchanged reused runner emits Phase 1 scope/not_validated text. This parent report and each wrapper's recorded backend arguments define the Phase 2 scope; child commands, results, exclusions and hashes are retained verbatim.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--candidate", default="target/release/psmc-rs")
    parser.add_argument("--phase1", default="bin/psmc-rs-phase1")
    parser.add_argument("--oracle", default="work/vanilla/psmc")
    parser.add_argument("--snapshot-oracle", default="work/instrumented/psmc")
    parser.add_argument("--dense-args", default='["--backend", "dense"]')
    parser.add_argument("--cpu-args", default='["--backend", "cpu"]')
    parser.add_argument("--only", help="Additional inherited test selection; an incomplete diagnostic, never a full gate")
    parser.add_argument("--report", default="bench/phase-2-validation.json")
    parser.add_argument("--timeout", type=int, default=180)
    options = parser.parse_args()
    os.chdir(ROOT)
    protocol = plan()
    backend_args = {"dense": json.loads(options.dense_args), "cpu": json.loads(options.cpu_args)}
    if not all(isinstance(value, list) and all(isinstance(arg, str) for arg in value) for value in backend_args.values()):
        parser.error("Backend arguments must be JSON arrays of strings")
    if not options.run:
        print(json.dumps({"status": "not_run", **protocol, "backend_arguments": backend_args}, indent=2))
        return 0
    run_dir = ROOT / "bench/phase-2-validation" / utc_stamp()
    run_dir.mkdir(parents=True)
    provenance = freeze(run_dir / "binaries", {"candidate": options.candidate, "phase1": options.phase1,
                        "vanilla": options.oracle, "instrumented": options.snapshot_oracle})
    report = {"schema_version": 1, "status": "running", "protocol": protocol,
              "provenance": provenance, "run_directory": relative(run_dir),
              "backend_arguments": backend_args, "complete_phase2_selection": not options.only,
              "runner_sha256": sha256(Path(__file__)), "inherited_runner_sha256": sha256(ROOT / "bench/phase1_differential.py"),
              "backend_reports": {}, "failures": [], "created_utc": dt.datetime.now(dt.timezone.utc).isoformat()}
    save(ROOT / options.report, report)
    for backend, arguments in backend_args.items():
        verify_binaries(provenance)
        entry = wrapper(run_dir / (backend + "-wrapper"), provenance["binaries"]["candidate"], arguments)
        child_path = run_dir / (backend + "-differential.json")
        command = [sys.executable, "bench/phase1_differential.py", "--candidate", entry["path"],
                   "--oracle", provenance["binaries"]["vanilla"]["path"],
                   "--snapshot-oracle", provenance["binaries"]["instrumented"]["path"],
                   "--raw", relative(run_dir / (backend + "-raw")), "--report", relative(child_path),
                   "--only", options.only or DEFAULT_SELECTION, "--timeout", str(options.timeout)]
        print(f"Validating {backend}; complete progress log: {relative(run_dir / (backend + '.stdout'))}", flush=True)
        execution = invoke(command, run_dir / backend)
        child = json.loads(child_path.read_text())
        bootstrap_cases = [case for case in child["cases"] if case["name"].startswith("strict_K23_N30_bootstrap_")]
        # Use the explicit finite flag; classification names belong to the unchanged runner.
        pathologies = [case["details"]["replicate"] for case in bootstrap_cases if "details" in case and not case["details"]["numerical_output"]["finite_outside_initial_RI"]]
        finite = sum(case.get("details", {}).get("numerical_output", {}).get("finite_outside_initial_RI", False) for case in bootstrap_cases)
        entry.update({"execution": execution, "report": relative(child_path), "report_sha256": sha256(child_path),
                      "passed": child["passed"], "failed": child["failed"], "selected_tests": child["selected_tests"],
                      "full_bootstrap_finite": finite, "full_bootstrap_pathologies": pathologies,
                      "snapshots": {case["name"]: case.get("details") for case in child["cases"] if case["name"].startswith("snapshot_exact_")}})
        report["backend_reports"][backend] = entry
        if execution["returncode"] or child["failed"]:
            report["failures"].append({"backend": backend, "kind": "differential_failure"})
        if not options.only and (finite != 27 or pathologies != [16, 26, 28] or len(bootstrap_cases) != 30):
            report["failures"].append({"backend": backend, "kind": "bootstrap_finite_pathology_classification_changed"})
        save(ROOT / options.report, report)
    verify_binaries(provenance)
    report["frozen_binaries_unchanged"] = True
    report["status"] = "failed" if report["failures"] else ("passed" if not options.only else "passed_partial_diagnostic")
    report["completed_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    save(ROOT / options.report, report)
    print(json.dumps({"status": report["status"], "report": options.report,
                      "checks": {name: {key: entry[key] for key in ("passed", "failed", "full_bootstrap_finite", "full_bootstrap_pathologies")} for name, entry in report["backend_reports"].items()}}, indent=2))
    return bool(report["failures"])


if __name__ == "__main__":
    raise SystemExit(main())

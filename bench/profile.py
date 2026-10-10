#!/usr/bin/env python3
"""Profile synthetic pinned PSMC only; run after other timed work has finished."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

from common import ROOT, draw_bootstrap, read_fasta, save, sha256, timed_run, write_fasta


def portable(value):
    if isinstance(value, str):
        return value.replace(str(ROOT), "${PROJECT}")
    if isinstance(value, list):
        return [portable(x) for x in value]
    if isinstance(value, dict):
        return {k: portable(v) for k, v in value.items()}
    return value


def parse_flat_profile(text):
    period = re.search(r"Each sample counts as ([0-9.]+) seconds", text)
    rows = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        try:
            percent, cumulative, self_seconds = map(float, parts[:3])
        except ValueError:
            continue
        record = {"function": parts[-1], "self_percent": percent,
                  "cumulative_seconds": cumulative, "self_seconds": self_seconds}
        if len(parts) >= 7:
            try:
                record["calls"] = int(parts[3])
            except ValueError:
                pass
        rows.append(record)
    self_sum = sum(row["self_seconds"] for row in rows)
    interval = float(period.group(1)) if period else None
    return {"sample_period_seconds": interval, "self_seconds_sum": self_sum,
            "estimated_samples_from_rounded_self_seconds": round(self_sum / interval) if interval else None,
            "functions": rows}


def check_finite_output(text):
    round_index = None
    failures = []
    allowed = []
    for number, line in enumerate(text.splitlines(), 1):
        fields = line.split()
        if fields and fields[0] == "RD":
            round_index = int(fields[1])
        nonfinite = [token for token in fields if token.lower() in
                     {"nan", "+nan", "-nan", "inf", "+inf", "-inf", "infinity", "-infinity", "+infinity"}]
        if nonfinite:
            entry = {"line": number, "round": round_index, "record": line}
            if fields[0] == "RI" and round_index == 0:
                allowed.append(entry)
            else:
                failures.append(entry)
    return {"status": "passed" if not failures else "failed_nonfinite",
            "allowed_initial_RI": allowed, "failures": failures}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeat", type=int, default=4,
                        help="repeat source observation strings within each of the same three records")
    parser.add_argument("--iterations", type=int, default=5)
    args = parser.parse_args()
    if args.repeat < 1 or args.iterations < 1:
        parser.error("repeat and iterations must be positive")
    raw = ROOT / "bench/raw/profile"
    raw.mkdir(parents=True, exist_ok=True)
    fixtures = ROOT / "tests/fixtures"
    source = fixtures / "workload.psmcfa"
    source_records = read_fasta(source)
    records = [(name + "_profile", seq * args.repeat) for name, seq in source_records]
    fixture = fixtures / "profile.psmcfa"
    write_fasta(fixture, records)
    split_path = raw / "profile-blocks.psmcfa"
    split_command = ["work/vanilla/utils/splitfa", str(fixture.relative_to(ROOT)), "1000"]
    split = subprocess.run(split_command, cwd=ROOT, capture_output=True, check=True)
    split_path.write_bytes(split.stdout)
    (raw / "split.stderr").write_bytes(split.stderr)
    blocks = read_fasta(split_path)
    seed = 42
    indices, expected_draws = draw_bootstrap(blocks, seed)
    replicate = raw / "profile-bootstrap.psmcfa"
    write_fasta(replicate, [blocks[i] for i in indices])
    manifest = {"seed": seed, "ordered_block_indices": indices, "draws": expected_draws,
                "source_blocks": [{"index": i, "id": name, "length_bins": len(seq)}
                                  for i, (name, seq) in enumerate(blocks)],
                "file": str(replicate.relative_to(ROOT)), "sha256": sha256(replicate)}
    save(raw / "bootstrap-manifest.json", manifest)
    common_args = ["-p", "4+25*2+4+6", "-N", str(args.iterations), "-t", "15", "-r", "4", "-I", "0"]
    report = {"schema_version": 1, "created_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "synthetic attribution only; no real-workload or speedup claim",
              "source_commit": "82fa2ada83ee463fe1251b562ae3d60e82d7ad6a",
              "states": 64, "iterations": args.iterations, "arguments": common_args,
              "fixture": {"file": str(fixture.relative_to(ROOT)), "sha256": sha256(fixture),
                          "source": str(source.relative_to(ROOT)), "source_sha256": sha256(source),
                          "repeat_within_each_record": args.repeat,
                          "records": [{"id": name, "length_bins": len(seq)} for name, seq in records],
                          "total_length_bins": sum(len(seq) for _, seq in records),
                          "provenance": "generated synthetic observations; no biological coordinate scale"},
              "bootstrap": {"split_command": split_command, "blocks_sha256": sha256(split_path),
                            "manifest": str((raw / "bootstrap-manifest.json").relative_to(ROOT)),
                            "input": str(replicate.relative_to(ROOT)), "input_sha256": sha256(replicate),
                            "seed": seed, "ordered_block_indices": indices,
                            "length_bins": sum(len(blocks[i][1]) for i in indices)},
              "binaries": {mode: {"file": f"work/{mode}/psmc", "sha256": sha256(ROOT / f"work/{mode}/psmc"),
                                  "build_record": f"reference/build-{mode}.json"}
                           for mode in ("vanilla", "gprof", "instrumented")},
              "runs": {}, "checks": {}, "limitations": [
                  "One diagnostic run per variant and workload; these do not estimate benchmark variance.",
                  "Only vanilla wall/RSS measurements use an unmodified executable; gprof and timers perturb execution.",
                  "gprof samples the profiled executable; shared-library allocator/libm time is not separately resolved.",
                  "gprof call counts reflect optimized compiled code and may omit inlined functions.",
                  "Profile allocation_setup_seconds covers sequence/count setup only; HMM/model allocations remain inclusive in those phases.",
                  "m_step_seconds overlaps model, Q and normalizer times; phase values must not all be added.",
                  "CLI startup includes input reading, parsing and bootstrap where applicable; output I/O is not isolated.",
                  "Materialized-bootstrap inference timings exclude resampling; the seeded -b replay additionally checks in-process sampling.",
                  "Synthetic record repetition changes the profiling fixture, not any user input or scientific workload.",
                  "GPU profiling and real-workload attribution are not_run."
              ]}
    base_env = os.environ.copy()
    for key in ("PSMC_SEED", "PSMC_SNAPSHOT", "PSMC_PROFILE", "PSMC_BOOTSTRAP_TRACE", "GMON_OUT_PREFIX"):
        base_env.pop(key, None)
    for case, input_path in (("fit", fixture), ("bootstrap", replicate)):
        case_runs = {}
        outputs = {}
        for mode in ("vanilla", "gprof", "instrumented"):
            env = base_env.copy()
            outbase = raw / f"{case}-{mode}"
            if mode == "gprof":
                prefix = raw / f"{case}-gmon"
                for old in raw.glob(prefix.name + ".*"):
                    old.unlink()
                env["GMON_OUT_PREFIX"] = str(prefix)
            if mode == "instrumented":
                profile_path = raw / f"{case}-phases.jsonl"
                env["PSMC_PROFILE"] = str(profile_path)
            command = [f"work/{mode}/psmc", *common_args, str(input_path.relative_to(ROOT))]
            result = timed_run(command, outbase, env=env, timeout=300)
            if result["exit_code"] != 0:
                raise RuntimeError(f"{case}/{mode} failed: see {outbase}.stderr")
            outputs[mode] = outbase.with_suffix(".psmc").read_bytes()
            result["numerical_output_check"] = check_finite_output(outputs[mode].decode())
            if mode == "gprof":
                gmons = list(raw.glob(prefix.name + ".*"))
                if len(gmons) != 1:
                    raise RuntimeError(f"Expected one gprof sample file, got {gmons}")
                sample_file = raw / f"{case}.gmon.out"
                gmons[0].replace(sample_file)
                for flags, label in ((["-b", "-p"], "flat"), (["-b"], "full")):
                    command = ["gprof", *flags, "work/gprof/psmc", str(sample_file.relative_to(ROOT))]
                    gp = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=True)
                    (raw / f"{case}-gprof-{label}.txt").write_text(gp.stdout)
                    (raw / f"{case}-gprof-{label}.stderr").write_text(gp.stderr)
                    if label == "flat":
                        result["sampling"] = parse_flat_profile(gp.stdout)
                        result["sampling"]["command"] = command
                result["gmon_file"] = str(sample_file.relative_to(ROOT))
            if mode == "instrumented":
                events = [json.loads(line) for line in profile_path.read_text().splitlines()]
                em = [e for e in events if e["event"] == "em_profile"]
                result["profile_file"] = str(profile_path.relative_to(ROOT))
                result["phase_totals_seconds"] = {k: sum(e[k] for e in em) for k in em[0] if k.endswith("_seconds")}
                result["startup_events"] = [e for e in events if e["event"] == "startup"]
                result["profile_optimizer_evaluations"] = [e["optimizer_evaluations"] for e in em]
                assert result["profile_optimizer_evaluations"] == result["optimizer_evaluations"]
                assert len(em) == args.iterations
            case_runs[mode] = result
            print(f"{case}/{mode}: {result['wall_seconds']:.3f}s, {result['peak_rss_kib']} KiB, {result['numerical_output_check']['status']}", flush=True)
        parity = {mode: outputs[mode] == outputs["vanilla"] for mode in ("gprof", "instrumented")}
        assert all(parity.values()), f"Numerical-output parity failed: {case}: {parity}"
        report["runs"][case] = case_runs
        report["checks"][case + "_complete_stdout_byte_parity"] = parity
        report["checks"][case + "_numerical_output_finite_after_initial_RI"] = all(
            result["numerical_output_check"]["status"] == "passed" for result in case_runs.values())
        save(ROOT / "bench/profile.json", portable(report))
    trace_path = raw / "bootstrap-trace.jsonl"
    replay_phases = raw / "bootstrap-replay-phases.jsonl"
    env = base_env | {"PSMC_SEED": str(seed), "PSMC_BOOTSTRAP_TRACE": str(trace_path), "PSMC_PROFILE": str(replay_phases)}
    replay = timed_run(["work/instrumented/psmc", "-b", *common_args, str(split_path.relative_to(ROOT))],
                       raw / "bootstrap-replay", env=env, timeout=300)
    assert replay["exit_code"] == 0
    replay["numerical_output_check"] = check_finite_output((raw / "bootstrap-replay.psmc").read_text())
    trace = [json.loads(line) for line in trace_path.read_text().splitlines()]
    actual_draws = [{k: e[k] for k in expected_draws[0]} for e in trace if e["event"] == "bootstrap_draw"]
    assert actual_draws == expected_draws
    assert (raw / "bootstrap-replay.psmc").read_bytes() == (raw / "bootstrap-vanilla.psmc").read_bytes()
    report["runs"]["seeded_bootstrap_replay"] = replay
    report["checks"]["bootstrap_trace_matches_independent_lcg_and_stop_rule"] = True
    report["checks"]["seeded_bootstrap_complete_stdout_matches_materialized_vanilla"] = True
    report["checks"]["phase_evaluation_counts_match_output_IT"] = True
    perf = shutil.which("perf")
    perf_command = [perf or "perf", "record", "-e", "cpu-clock", "-o", "bench/raw/profile/perf.data", "--",
                    "work/vanilla/psmc", "-p", "2+2", "-N", "0", "-I", "0", "tests/fixtures/tiny.psmcfa"]
    if perf:
        probe = subprocess.run(perf_command, cwd=ROOT, env=base_env, capture_output=True, text=True)
        (raw / "perf.stdout").write_text(probe.stdout)
        (raw / "perf.stderr").write_text(probe.stderr)
        report["perf_probe"] = {"command": perf_command, "exit_code": probe.returncode,
                                "status": "unavailable" if probe.returncode else "available",
                                "stderr_file": "bench/raw/profile/perf.stderr"}
    else:
        report["perf_probe"] = {"status": "not_installed", "command": perf_command}
    paranoid = Path("/proc/sys/kernel/perf_event_paranoid")
    report["perf_probe"]["perf_event_paranoid"] = paranoid.read_text().strip() if paranoid.exists() else None
    report["perf_probe"]["settings_or_privileges_changed"] = False
    report["sampling_fallback"] = "GNU gprof -pg, actual execution samples plus call instrumentation"
    for tool in ("gprof", "perf"):
        if shutil.which(tool):
            result = subprocess.run([tool, "--version"], capture_output=True, text=True)
            report.setdefault("tool_versions", {})[tool] = (result.stdout or result.stderr).splitlines()[0]
    finite = all(result["numerical_output_check"]["status"] == "passed"
                 for case in ("fit", "bootstrap") for result in report["runs"][case].values())
    report["status"] = "passed_synthetic_profile_and_parity_checks" if finite else "invalid_synthetic_fixture_nonfinite_output"
    save(ROOT / "bench/profile.json", portable(report))
    print("Saved bench/profile.json; no real-workload performance claim.")


if __name__ == "__main__":
    main()

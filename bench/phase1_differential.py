#!/usr/bin/env python3
"""Phase 1 Rust versus pinned C: strict output, exact snapshots, and legacy controls.

This harness never rewrites Phase 0 evidence. Timings are deliberately excluded;
instrumented snapshot runs are correctness diagnostics, not speed measurements.
"""
import argparse
from collections import Counter
import ctypes
import gzip
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys

from common import ROOT, save, sha256, write_fasta
from differential import enumeration_check, output_diagnostics

SOURCE_COMMIT = "82fa2ada83ee463fe1251b562ae3d60e82d7ad6a"
VERSION_PREFIX = b"MM\tVersion: "


def strict_output(data):
    """Allow exactly one version record; retain every other byte, including MM."""
    lines = data.splitlines(keepends=True)
    excluded = [line for line in lines if line.startswith(VERSION_PREFIX)]
    if len(excluded) != 1:
        raise AssertionError(f"Expected exactly one MM Version record, found {len(excluded)}")
    return b"".join(line for line in lines if not line.startswith(VERSION_PREFIX)), excluded[0].decode().rstrip("\r\n")


def compare_output(oracle, candidate):
    left, left_version = strict_output(oracle)
    right, right_version = strict_output(candidate)
    if left != right:
        lines_a, lines_b = left.splitlines(), right.splitlines()
        for line, (a, b) in enumerate(itertools.zip_longest(lines_a, lines_b), 1):
            if a != b:
                raise AssertionError(f"stdout mismatch outside version record at line {line}: C={a!r}, Rust={b!r}")
        raise AssertionError("stdout newline/byte mismatch outside version record")
    return {"compared_sha256": hashlib.sha256(left).hexdigest(),
            "compared_bytes": len(left), "excluded_oracle_version": left_version,
            "excluded_candidate_version": right_version}


def numerical_class(value):
    if isinstance(value, str) and value in ("nan", "inf", "-inf"):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if math.isnan(value):
            return "nan"
        if math.isinf(value):
            return "inf" if value > 0 else "-inf"
        return "finite"
    return None


def compare_snapshots(oracle_path, candidate_path):
    """Compare every event and field in order without a floating-point tolerance.

    JSON's 1 and 1.0 encode the same finite binary64 value. Negative zero is also
    checked; NaN payload/sign are not, as stipulated in the validation policy.
    All mismatch counts are retained; only diagnostic examples are bounded.
    """
    stats = {"events": 0, "event_types": Counter(), "finite_numeric_values": 0,
             "nonfinite_classes": Counter(), "non_numeric_values": 0,
             "mismatches": 0, "first_mismatches": [], "finite_tolerance": 0,
             "negative_zero_checked": True, "event_order_checked": True}

    def mismatch(path, a, b):
        stats["mismatches"] += 1
        if len(stats["first_mismatches"]) < 25:
            stats["first_mismatches"].append({"path": path, "oracle": repr(a), "candidate": repr(b)})

    def compare(a, b, path):
        class_a, class_b = numerical_class(a), numerical_class(b)
        if class_a is not None or class_b is not None:
            if class_a != class_b:
                mismatch(path, a, b)
            elif class_a == "finite":
                stats["finite_numeric_values"] += 1
                if a != b or (a == 0 and math.copysign(1.0, a) != math.copysign(1.0, b)):
                    mismatch(path, a, b)
            else:
                stats["nonfinite_classes"][class_a] += 1
            return
        if isinstance(a, dict) and isinstance(b, dict):
            if set(a) != set(b):
                mismatch(path + ".keys", sorted(a), sorted(b))
            for key in a:
                if key in b:
                    compare(a[key], b[key], path + "." + key)
        elif isinstance(a, list) and isinstance(b, list):
            if len(a) != len(b):
                mismatch(path + ".length", len(a), len(b))
            for index, (left, right) in enumerate(zip(a, b)):
                compare(left, right, f"{path}[{index}]")
        elif type(a) is not type(b) or a != b:
            mismatch(path, a, b)
        else:
            stats["non_numeric_values"] += 1

    with oracle_path.open() as oracle, candidate_path.open() as candidate:
        for line, (left, right) in enumerate(itertools.zip_longest(oracle, candidate), 1):
            if left is None or right is None:
                mismatch(f"line[{line}]", None if left is None else "extra C event", None if right is None else "extra Rust event")
                continue
            a, b = json.loads(left), json.loads(right)
            stats["events"] += 1
            stats["event_types"][a.get("event", "<missing>")] += 1
            compare(a, b, f"event[{line}]/{a.get('event', '<missing>')}")
    stats["event_types"] = dict(stats["event_types"])
    stats["nonfinite_classes"] = dict(stats["nonfinite_classes"])
    if not stats["events"]:
        raise AssertionError("Snapshot comparison had no events")
    required = {"model", "sequence", "aggregate", "objective", "em_end"}
    if required - set(stats["event_types"]):
        raise AssertionError(f"Missing snapshot event types: {required - set(stats['event_types'])}")
    return stats


def independent_counts_and_q(events):
    """Retain the Phase 0 independent diagnostic and its unchanged tolerances."""
    details = enumeration_check(events)
    agg = next(e for e in events if e["event"] == "aggregate")
    sequences = [e for e in events if e["event"] == "sequence" and e["iteration"] == 1]
    n = len(agg["A0"])
    a0, a, e = [0.0] * n, [[0.0] * n for _ in range(n)], [[0.0] * n for _ in range(3)]
    likelihood = 0.0
    for seq in sequences:
        likelihood += seq["log_likelihood"]
        for k in range(n):
            a0[k] += seq["A0"][k]
            for l in range(n):
                a[k][l] += seq["A"][k][l]
        for b in range(2):
            for k in range(n):
                e[b][k] += seq["E"][b][k]
    if (a0, a, e, likelihood) != (agg["A0"], agg["A"], agg["E"], agg["log_likelihood"]):
        raise AssertionError("Counts or likelihood differ from ordered per-sequence summation")
    q0 = 0.0
    for k in range(n):
        total = 0.0
        for b in range(2):
            total += e[b][k]
        for b in range(2):
            q0 += e[b][k] * math.log(e[b][k] / total)
    for k in range(n):
        total = 0.0
        for l in range(n):
            total += a[k][l]
        for l in range(n):
            q0 += a[k][l] * math.log(a[k][l] / total)
    if not math.isclose(q0, agg["stored_Q0"], rel_tol=1e-10, abs_tol=1e-12):
        raise AssertionError("Independent full-count Q normalizer mismatch")
    models = {e["model_id"]: e for e in events if e["event"] == "model"}
    checked, maxdiff, objectives = 0, 0.0, 0
    skipped = {"nonpositive_probability": 0, "nonfinite_model": 0}
    for event in events:
        if event["event"] != "objective":
            continue
        objectives += 1
        model = models[event["model_id"]]
        probabilities = [v for row in model["transition"] for v in row]
        probabilities += [v for row in model["emission"][:2] for v in row]
        if any(numerical_class(v) == "finite" and v <= 0 for v in probabilities):
            if event["negative_Q"] != 1e300:
                raise AssertionError("Nonpositive probability did not return +1e300 negative-Q sentinel")
            skipped["nonpositive_probability"] += 1
            continue
        if any(numerical_class(v) != "finite" for v in probabilities):
            skipped["nonfinite_model"] += 1
            continue
        if numerical_class(event["negative_Q"]) != "finite":
            raise AssertionError("Finite positive model produced nonfinite candidate Q")
        q = 0.0
        for b in range(2):
            for k in range(n):
                q += e[b][k] * math.log(model["emission"][b][k])
        for k in range(n):
            for l in range(n):
                q += a[k][l] * math.log(model["transition"][k][l])
        q -= q0
        maxdiff = max(maxdiff, abs(q + event["negative_Q"]))
        if not math.isclose(q, -event["negative_Q"], rel_tol=1e-10, abs_tol=1e-12):
            raise AssertionError("Independent candidate-Q mismatch")
        checked += 1
    if not checked:
        raise AssertionError("No finite candidate Q checked independently")
    details.update({"ordered_aggregate_exact": True, "independent_Q0": q0,
                    "stored_Q0": agg["stored_Q0"], "Q0_absolute_difference": abs(q0 - agg["stored_Q0"]),
                    "candidate_Q_checks": checked, "candidate_Q_max_absolute_difference": maxdiff,
                    "objective_events": objectives, "invalid_candidate_categories": skipped})
    return details


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", default="target/release/psmc-rs")
    parser.add_argument("--oracle", default="work/vanilla/psmc")
    parser.add_argument("--snapshot-oracle", default="work/instrumented/psmc")
    parser.add_argument("--raw", default="bench/raw/phase1-tests")
    parser.add_argument("--report", default="bench/phase1-differential.json")
    parser.add_argument("--only", help="Select test names by regular expression; report explicitly marks incomplete scope")
    parser.add_argument("--list", action="store_true", help="List selected test names without running them")
    parser.add_argument("--timeout", type=int, default=180, help="Per-process timeout; this is not a timing benchmark")
    options = parser.parse_args()
    raw = ROOT / options.raw
    raw.mkdir(parents=True, exist_ok=True)
    results, diagnostics, commands, tests = [], {}, [], []

    def execute(binary, args, inp, name, env_extra=None, stdin=None, expected_success=True):
        expected_hash = next(entry["sha256"] for entry in provenance.values() if entry["path"] == binary)
        if sha256(ROOT / binary) != expected_hash:
            raise AssertionError(f"Executable changed during validation: {binary}; rerun against one pinned build")
        env = {k: v for k, v in os.environ.items() if not k.startswith("PSMC_")}
        env.update(env_extra or {})
        command = [str(binary), *map(str, args)] + ([] if inp is None else [str(inp)])
        stdout_path, stderr_path = raw / f"{name}.psmc", raw / f"{name}.stderr"
        try:
            result = subprocess.run(command, cwd=ROOT, env=env, input=stdin, capture_output=True, timeout=options.timeout)
        except subprocess.TimeoutExpired as error:
            stdout_path.write_bytes(error.stdout or b"")
            stderr_path.write_bytes(error.stderr or b"")
            commands.append({"name": name, "command": command, "controls": env_extra or {}, "timeout": True})
            raise AssertionError(f"Process timed out after {options.timeout} seconds: {name}") from error
        stdout_path.write_bytes(result.stdout)
        stderr_path.write_bytes(result.stderr)
        commands.append({"name": name, "command": command, "controls": env_extra or {},
                         "returncode": result.returncode,
                         "input_sha256": sha256(ROOT / inp) if inp not in (None, "-") and (ROOT / inp).is_file() else None,
                         "stdin_sha256": hashlib.sha256(stdin).hexdigest() if stdin is not None else None,
                         "stdout_sha256": hashlib.sha256(result.stdout).hexdigest(),
                         "stderr_sha256": hashlib.sha256(result.stderr).hexdigest()})
        diagnostics[name] = output_diagnostics(result.stdout)
        if expected_success and result.returncode:
            raise AssertionError(f"Exit {result.returncode}: {result.stderr.decode(errors='replace')[:600]}")
        if not expected_success:
            if result.returncode <= 0:
                raise AssertionError(f"Expected clean nonzero rejection, got {result.returncode}")
            if b"panicked at" in result.stderr or not result.stderr.strip():
                raise AssertionError("Rejection must produce an explanatory error without a panic")
        return result

    def add(name, operation):
        tests.append((name, operation))

    base = ["-p", "2+2", "-N", "2", "-t", "15", "-r", "4", "-I", "0"]
    cases = [
        ("tiny", "tiny.psmcfa", []), ("gzip", "tiny.psmcfa.gz", []),
        ("aliases", "aliases.psmcfa", []), ("repeated", "repeated.psmcfa", []),
        ("fixed", "tiny.psmcfa", ["-i", "tests/fixtures/fixed.par"]),
        ("grid", "tiny.psmcfa", ["-i", "tests/fixtures/grid.par"]),
        ("missing", "missing.psmcfa", ["-i", "tests/fixtures/fixed.par", "-N", "1"]),
        ("single", "single.psmcfa", ["-i", "tests/fixtures/fixed.par", "-N", "1"]),
        ("64_states", "tiny.psmcfa", ["-p", "4+25*2+4+6"]),
        ("30_iterations", "tiny.psmcfa", ["-N", "30"]),
        ("finite_workload_30_iterations", "workload.psmcfa", ["-p", "4+5*3+4", "-N", "30"]),
        ("decoding", "tiny.psmcfa", ["-d"]), ("full_posterior", "tiny.psmcfa", ["-D"]),
        ("probability", "tiny.psmcfa", ["-s"]), ("divergence", "tiny.psmcfa", ["-T", "0.2"]),
        ("alpha", "tiny.psmcfa", ["-l", "0.2"]), ("cap", "tiny.psmcfa", ["-d", "-C", "1"]),
    ]
    for name, filename, args in cases:
        def pair(name=name, filename=filename, args=args):
            inp = "tests/fixtures/" + filename
            c = execute(options.oracle, base + args, inp, name + "-oracle").stdout
            r = execute(options.candidate, base + args, inp, name + "-candidate").stdout
            detail = compare_output(c, r)
            numerical = output_diagnostics(c)
            if name == "finite_workload_30_iterations" and not numerical["finite_outside_initial_RI"]:
                raise AssertionError("Required finite 30-round reference workload has nonfinite output")
            detail.update({"arguments": base + args + [inp], "numerical_output": numerical})
            return detail
        add("strict_" + name, pair)

    def aliases():
        left = execute(options.candidate, base, "tests/fixtures/aliases.psmcfa", "alias-source").stdout
        right = execute(options.candidate, base, "tests/fixtures/aliases-canonical.psmcfa", "alias-canonical").stdout
        assert left == right, "Candidate aliases differ from canonical encoding"
        return {"implementation": "Rust", "exact_full_stdout": True}
    add("encoding_alias_equivalence", aliases)

    def boundaries():
        left = execute(options.candidate, base, "tests/fixtures/tiny.psmcfa", "boundaries-original").stdout
        right = execute(options.candidate, base, "tests/fixtures/tiny-joined.psmcfa", "boundaries-joined").stdout
        lks = lambda text: [line for line in text.splitlines() if line.startswith(b"LK\t")]
        assert lks(left) != lks(right), "Fixture failed to expose an invalid change in HMM boundaries"
        return {"implementation": "Rust", "note": "Joining independent records changes likelihood"}
    add("sequence_boundaries_negative_control", boundaries)

    def rng_check():
        libc = ctypes.CDLL(None)
        libc.srand48.argtypes = [ctypes.c_long]
        libc.drand48.restype = ctypes.c_double
        for seed in [0, 1, 20261009, 4294967295]:
            libc.srand48(seed)
            state = ((seed & 0xffffffff) << 16) | 0x330e
            for _ in range(100):
                state = (0x5deece66d * state + 0xb) & ((1 << 48) - 1)
                assert libc.drand48() == state / (1 << 48)
        return {"exact_double_draw_comparisons": 400, "scope": "Independent replay versus linked libc; Rust end-to-end trace tests follow"}
    add("glibc_rng_replay", rng_check)

    workload = json.loads((ROOT / "bench/workload.json").read_text())
    for rep in workload["bootstrap"]["replicates"]:
        def bootstrap(rep=rep):
            trace = raw / f"bootstrap-{rep['id']:02d}.jsonl"
            candidate = execute(options.candidate, base + ["-b"], "tests/fixtures/blocks.psmcfa", f"bootstrap-{rep['id']:02d}-candidate",
                                {"PSMC_SEED": str(rep["seed"]), "PSMC_BOOTSTRAP_TRACE": str(trace)}).stdout
            oracle = execute(options.oracle, base, rep["file"], f"bootstrap-{rep['id']:02d}-oracle").stdout
            detail = compare_output(oracle, candidate)
            actual = [json.loads(line) for line in trace.read_text().splitlines()]
            draws = [event for event in actual if event["event"] == "bootstrap_draw"]
            assert len(draws) == len(rep["draws"]), "Bootstrap proposal count differs"
            for ordinal, (draw, expected) in enumerate(zip(draws, rep["draws"])):
                assert draw["draw"] == ordinal, "Bootstrap proposal order differs"
                assert all(draw[key] == value for key, value in expected.items()), "Bootstrap draw/stop mismatch"
            ends = [event for event in actual if event["event"] == "bootstrap_end"]
            assert len(ends) == 1 and actual[-1] == ends[0], "Missing or misplaced bootstrap completion event"
            assert ends[0]["accepted_sequences"] == len(rep["ordered_block_indices"])
            assert ends[0]["length"] == rep["raw_length_bins"]
            detail.update({"seed": rep["seed"], "draws": len(draws), "accepted": len(rep["ordered_block_indices"]),
                           "raw_length_bins": rep["raw_length_bins"], "numerical_output": output_diagnostics(oracle)})
            return detail
        add(f"bootstrap_replay_{rep['id']:02d}", bootstrap)

    def snapshot_pair(name, args, inp, *, enumerate_paths=False):
        cpath, rpath = raw / f"{name}-C.jsonl", raw / f"{name}-Rust.jsonl"
        details = {"arguments": args + [str(inp)], "seed": 7}
        try:
            c = execute(options.snapshot_oracle, args, inp, name + "-snapshot-oracle", {"PSMC_SEED": "7", "PSMC_SNAPSHOT": str(cpath)}).stdout
            unmodified = execute(options.oracle, args, inp, name + "-vanilla-oracle").stdout
            assert c == unmodified, "C instrumentation changed stdout on deterministic input"
            r = execute(options.candidate, args, inp, name + "-candidate", {"PSMC_SEED": "7", "PSMC_SNAPSHOT": str(rpath)}).stdout
            comparison = compare_snapshots(cpath, rpath)
            details.update(comparison)
            # Preserve all internal mismatches in a separate record, even when
            # the printed-output assertion also fails.
            save(raw / f"{name}-comparison.json", comparison)
            details.update(compare_output(c, r))
            if comparison["mismatches"]:
                raise AssertionError(f"{comparison['mismatches']} exact snapshot differences; first: {comparison['first_mismatches'][0]}")
            if enumerate_paths:
                details["independent_diagnostic"] = independent_counts_and_q([json.loads(line) for line in rpath.read_text().splitlines()])
            details["numerical_output"] = output_diagnostics(c)
            return details
        finally:
            artifacts = []
            for path in (cpath, rpath):
                if path.exists():
                    destination = Path(str(path) + ".gz")
                    with path.open("rb") as source, gzip.open(destination, "wb", compresslevel=1) as target:
                        shutil.copyfileobj(source, target)
                    path.unlink()
                    artifacts.append({"path": str(destination.relative_to(ROOT)), "sha256": sha256(destination)})
            save(raw / f"{name}-artifacts.json", artifacts)

    enum_input = "tests/fixtures/enumeration.psmcfa"
    add("independent_path_enumeration_and_Q", lambda: snapshot_pair("enumeration", ["-i", "tests/fixtures/fixed.par", "-N", "1"], enum_input, enumerate_paths=True))

    def seeded_random():
        args, controls = base + ["-I", "0.1"], {"PSMC_SEED": "20261009"}
        c = execute(options.snapshot_oracle, args, "tests/fixtures/tiny.psmcfa", "random-C", controls).stdout
        first = execute(options.candidate, args, "tests/fixtures/tiny.psmcfa", "random-Rust-1", controls).stdout
        second = execute(options.candidate, args, "tests/fixtures/tiny.psmcfa", "random-Rust-2", controls).stdout
        assert first == second, "Candidate seed replay differs"
        details = compare_output(c, first)
        details["scope"] = "Seeded Rust compared with instrumented C; unmodified C has no seed control"
        return details
    add("random_initialization_replay", seeded_random)

    snapshot_cases = [
        ("tiny_N2", base, "tests/fixtures/tiny.psmcfa"),
        ("grid_N1", ["-i", "tests/fixtures/grid.par", "-N", "1"], enum_input),
        # The finite workload exercises the same complete model/callback schema
        # without the tiny fixture's50k callback limit and multi-GB trace.
        ("K23_N1", ["-p", "4+5*3+4", "-N", "1", "-I", "0"], "tests/fixtures/workload.psmcfa"),
        ("K64_N1", ["-p", "4+25*2+4+6", "-N", "1", "-I", "0"], "tests/fixtures/workload.psmcfa"),
    ]
    for name, args, inp in snapshot_cases:
        add("snapshot_exact_" + name, lambda name=name, args=args, inp=inp: snapshot_pair(name, args, inp))

    full_args = ["-p", "4+5*3+4", "-N", "30", "-t", "15", "-r", "4", "-I", "0"]
    for rep in workload["bootstrap"]["replicates"]:
        def full_bootstrap(rep=rep):
            name = f"K23_N30_bootstrap_{rep['id']:02d}"
            c = execute(options.oracle, full_args, rep["file"], name + "-oracle").stdout
            r = execute(options.candidate, full_args, rep["file"], name + "-candidate").stdout
            details = compare_output(c, r)
            rounds = [int(line.split()[1]) for line in c.splitlines() if line.startswith(b"RD\t")]
            assert rounds == list(range(31)), "Expected initial round plus exactly30 EM rounds"
            details.update({"replicate": rep["id"], "seed_materialization": rep["seed"],
                            "input_sha256": sha256(ROOT / rep["file"]), "arguments": full_args + [rep["file"]],
                            "numerical_output": output_diagnostics(c),
                            "previously_known_nonfinite_reference": rep["id"] in (16, 26, 28)})
            return details
        add(f"strict_K23_N30_bootstrap_{rep['id']:02d}", full_bootstrap)

    def rejection(name, args, inp="tests/fixtures/tiny.psmcfa", content=None):
        if content is not None:
            path = raw / f"invalid-{name}.psmcfa"
            path.write_bytes(content)
            inp = str(path.relative_to(ROOT))
        result = execute(options.candidate, args, inp, "rejected-" + name, expected_success=False)
        return {"returncode": result.returncode, "diagnostic": result.stderr.decode(errors="replace").strip(),
                "scope": "Explicit runtime safety/unsupported-feature rejection; C crash behavior is not reproduced"}
    rejected = [
        ("simulation", ["-S"], None), ("cpg", ["-c", "unused.bin"], None),
        ("equivalent_mode", ["--mode", "equivalent"], None),
        ("research_mode", ["--mode", "research"], None),
        ("cuda_backend", ["--backend", "cuda"], None),
        ("unknown_flag", ["--not-a-psmc-option"], None),
        ("negative_iterations", ["-N", "-1"], None),
        ("zero_width_pattern", ["-p", "0+2"], None),
        ("malformed_pattern", ["-p", "2++2"], None),
        ("malformed_number", ["-r", "abc"], None),
        ("nonfinite_number", ["-t", "NaN"], None),
        ("zero_ratio", ["-r", "0"], None),
        ("empty_input", [], b""), ("empty_record", [], b">empty\n"),
        ("no_header", [], b"TKTKTK\n"),
        ("truncated_fastq", [], b"@record\nTKTK\n+\n!!!\n"),
    ]
    for name, args, content in rejected:
        add("reject_" + name, lambda name=name, args=args, content=content: rejection(name, args, content=content))
    add("reject_missing_input", lambda: rejection("missing-input", [], inp=None))
    add("reject_missing_option_value", lambda: rejection("missing-option-value", ["-N"], inp=None))

    def output_alias(name, variant):
        directory = raw / ("safety-" + name)
        directory.mkdir(parents=True, exist_ok=True)
        source = directory / "input.psmcfa"
        original = (ROOT / "tests/fixtures/tiny.psmcfa").read_bytes()
        source.write_bytes(original)
        destination = directory / "result.psmc"
        if destination.exists():
            destination.unlink()
        args, controls = ["-N", "0"], {}
        if variant == "hardlink":
            os.link(source, destination)
            args += ["-o", str(destination)]
        elif variant == "dot_alias":
            args += ["-o", str(destination), "--snapshot", str(directory) + "/./result.psmc"]
        elif variant == "trace_output":
            args += ["-b", "-o", str(destination)]
            controls["PSMC_BOOTSTRAP_TRACE"] = str(destination)
        elif variant == "trace_snapshot":
            args += ["-b", "--snapshot", str(destination)]
            controls["PSMC_BOOTSTRAP_TRACE"] = str(destination)
        elif variant == "dangling_symlink":
            alias = directory / "dangling-alias.psmc"
            if alias.is_symlink() or alias.exists():
                alias.unlink()
            alias.symlink_to(destination.name)
            args += ["-o", str(destination), "--snapshot", str(alias)]
        else:
            raise AssertionError("Invalid harness safety variant")
        result = execute(options.candidate, args, str(source), name, controls, expected_success=False)
        assert source.read_bytes() == original, "Rejected operation changed its input file"
        if variant != "hardlink":
            assert not destination.exists(), "Rejected alias operation created an output file"
        return {"input_unchanged": True, "returncode": result.returncode,
                "diagnostic": result.stderr.decode(errors="replace").strip()}
    for label, variant in [("input_output_hardlink", "hardlink"), ("new_output_snapshot_dot_alias", "dot_alias"),
                           ("trace_output", "trace_output"), ("trace_snapshot", "trace_snapshot"),
                           ("dangling_output_snapshot_symlink", "dangling_symlink")]:
        add("safety_reject_" + label, lambda label=label, variant=variant: output_alias(label, variant))

    def full_snapshot_device():
        assert Path("/dev/full").exists(), "Linux /dev/full required for the pinned-stack write-failure test"
        result = execute(options.candidate, ["-N", "0", "--snapshot", "/dev/full"],
                         "tests/fixtures/tiny.psmcfa", "snapshot-dev-full", expected_success=False)
        return {"returncode": result.returncode, "diagnostic": result.stderr.decode(errors="replace").strip(),
                "scope": "An initial-only snapshot must propagate its final buffered write failure"}
    add("safety_snapshot_final_flush_failure", full_snapshot_device)

    def standard_stream_alias(name, args, inp, stdin=None):
        result = execute(options.candidate, args, inp, name, stdin=stdin, expected_success=False)
        assert not result.stdout, "Unsafe standard-stream alias emitted partial output before rejection"
        return {"returncode": result.returncode, "diagnostic": result.stderr.decode(errors="replace").strip()}
    add("safety_reject_output_alias_of_stdin", lambda: standard_stream_alias(
        "output-alias-of-stdin", ["-N", "0", "-o", "/dev/stdin"], "-", (ROOT / "tests/fixtures/tiny.psmcfa").read_bytes()))
    add("safety_reject_snapshot_alias_of_stdout", lambda: standard_stream_alias(
        "snapshot-alias-of-stdout", ["-N", "0", "--snapshot", "/dev/stdout"], "tests/fixtures/tiny.psmcfa"))

    def round_zero_nonfinite_warning():
        path = raw / "all-heterozygous.psmcfa"
        path.write_text(">all_heterozygous\nKKKKKKKK\n")
        c = execute(options.oracle, ["-N", "0"], str(path), "all-heterozygous-C")
        r = execute(options.candidate, ["-N", "0"], str(path), "all-heterozygous-Rust")
        details = compare_output(c.stdout, r.stdout)
        assert b"nonfinite legacy calculation at round 0" in r.stderr, "Missing nonfinite round-zero diagnostic"
        details["numerical_output"] = output_diagnostics(c.stdout)
        assert not details["numerical_output"]["finite_outside_initial_RI"]
        return details
    add("pathology_round_zero_nonfinite_warning", round_zero_nonfinite_warning)

    def stdin_parity():
        data = (ROOT / "tests/fixtures/tiny.psmcfa").read_bytes()
        c = execute(options.oracle, base, "-", "stdin-C", stdin=data).stdout
        r = execute(options.candidate, base, "-", "stdin-Rust", stdin=data).stdout
        return compare_output(c, r)
    add("strict_stdin", stdin_parity)

    def fastq_parity():
        path = raw / "valid.fastq"
        path.write_text("@first comment\nTKNNTKTK\n+\nIIIIIIII\n@second\nKTTKTN\n+\nIIIIII\n")
        inp = str(path.relative_to(ROOT))
        c = execute(options.oracle, base, inp, "fastq-C").stdout
        r = execute(options.candidate, base, inp, "fastq-Rust").stdout
        return compare_output(c, r)
    add("strict_fastq_qualities_ignored", fastq_parity)

    selected = [(name, operation) for name, operation in tests if not options.only or re.search(options.only, name)]
    if not selected:
        parser.error("Test selection is empty")
    if options.list:
        print("\n".join(name for name, _ in selected))
        return 0
    binaries = {"candidate": options.candidate, "oracle": options.oracle, "snapshot_oracle": options.snapshot_oracle}
    provenance = {key: {"path": value, "sha256": sha256(ROOT / value)} for key, value in binaries.items()}
    source_files = sorted(ROOT.glob("crates/**/*.rs")) + [ROOT / name for name in ("Cargo.toml", "Cargo.lock", "rust-toolchain.toml")]
    source_hashes = {str(path.relative_to(ROOT)): sha256(path) for path in source_files}

    def report():
        failures = [case for case in results if case["status"] == "failed"]
        full_boots = [case for case in results if case["name"].startswith("strict_K23_N30_bootstrap_")]
        pathological = [case["name"] for case in full_boots
                        if not case.get("details", {}).get("numerical_output", {}).get("finite_outside_initial_RI", True)]
        finished = len(results) == len(selected)
        record = {"schema_version": 1, "scope": "Phase1 dense Rust vs pinned C; synthetic inputs only",
                  "status": "failed" if failures else ("passed" if finished else "running"),
                  "complete_suite": finished and len(selected) == len(tests),
                  "selection": options.only, "available_tests": len(tests), "selected_tests": len(selected),
                  "source_commit": SOURCE_COMMIT, "binaries": provenance,
                  "source_hashes_at_start": source_hashes,
                  "platform": platform.platform(), "harness_sha256": sha256(Path(__file__)),
                  "strict_metadata_allowlist": ["Exactly one line beginning MM\\tVersion: ; all remaining stdout bytes compared"],
                  "snapshot_comparison": "Every JSON event/field in order; exact finite numeric equality and signed-zero check; NaN/Inf class equality",
                  "independent_diagnostic_tolerances": {"relative": 1e-10, "absolute": 1e-12, "source": "Unchanged Phase0 path/count/Q diagnostic; not a production equivalent-mode contract"},
                  "passed": len(results) - len(failures), "failed": len(failures),
                  "full_30_round_bootstraps_completed": len(full_boots),
                  "full_30_round_bootstrap_reference_pathologies": pathological,
                  "run_numerical_diagnostics": diagnostics, "commands": commands, "cases": results,
                  "not_validated": ["Real genome input or current user settings", "CUDA", "Accelerated CPU or equivalent backend",
                                    "Cross-platform bitwise parity", "Simulation and CpG binary input", "Performance or10x speedup"]}
        save(ROOT / options.report, record)
        return failures

    for index, (name, operation) in enumerate(selected, 1):
        try:
            detail = operation()
            results.append({"name": name, "status": "passed", "details": detail})
        except Exception as error:
            results.append({"name": name, "status": "failed", "error": str(error)})
        report()
        print(f"[{index}/{len(selected)}] {name}: {results[-1]['status']}", flush=True)
    failures = report()
    print(json.dumps({"passed": len(results) - len(failures), "failed": failures, "report": options.report}))
    return bool(failures)


if __name__ == "__main__":
    sys.exit(main())

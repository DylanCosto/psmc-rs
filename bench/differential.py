#!/usr/bin/env python3
"""Strict C-oracle regression harness, bootstrap replay, and independent tiny path checks.

The initial candidate is the instrumented C build. This does not establish a
Rust port or any accelerated backend's compatibility.
"""
import argparse
import ctypes
import gzip
import itertools
import json
import math
import os
import re
from pathlib import Path
import subprocess
import sys
from common import ROOT, save, sha256, read_fasta, write_fasta, draw_bootstrap

RUN_DIAGNOSTICS = {}

def output_diagnostics(output):
    """Distinguish exact legacy pathology replay from a finite EM trajectory."""
    round_index = None
    nonfinite = []
    exempt_initial_ri = 0
    for line_number, line in enumerate(output.decode().splitlines(), 1):
        fields = line.split()
        if not fields:
            continue
        if fields[0] == "RD":
            round_index = int(fields[1])
        if fields[0] == "CC":
            continue
        bad = [v for v in fields[1:] if re.fullmatch(r"[+-]?(?:inf(?:inity)?|nan)(?:\([^)]*\))?", v, flags=re.I)]
        if bad:
            if fields[0] == "RI" and round_index == 0:
                exempt_initial_ri += 1
            else:
                nonfinite.append({"line": line_number, "round": round_index, "tag": fields[0], "values": bad})
    return {"finite_outside_initial_RI": not nonfinite,
            "nonfinite_record_count": len(nonfinite),
            "nonfinite_first_records": nonfinite[:20],
            "expected_initial_RI_nonfinite_records": exempt_initial_ri,
            "classification": "finite_reference_output" if not nonfinite else "legacy_nonfinite_pathology_parity_only"}

def execute(binary, args, input_file, name, extra_env=None):
    env = os.environ.copy()
    for key in list(env):
        if key.startswith("PSMC_"):
            del env[key]
    env.update(extra_env or {})
    command = [str(binary), *args, str(input_file)]
    result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, timeout=60)
    (ROOT / "bench/raw/tests" / (name + ".psmc")).write_bytes(result.stdout)
    (ROOT / "bench/raw/tests" / (name + ".stderr")).write_bytes(result.stderr)
    RUN_DIAGNOSTICS[name] = output_diagnostics(result.stdout)
    if result.returncode:
        raise AssertionError(f"Exit {result.returncode}: {result.stderr.decode()[:500]}")
    return result.stdout

def enumeration_check(events):
    """Enumerate all hidden paths using the *C-generated* PSMC model.

    This checks forward/backward/counts independently, not parameter-to-matrix
    construction. Diagnostic tolerance is fixed here, not a future backend gate.
    """
    model = next(x for x in events if x["event"] == "model")
    sequences = [x for x in events if x["event"] == "sequence" and x["iteration"] == 1]
    if not sequences:
        raise AssertionError("No sequences available for independent path enumeration")
    maxdiff = 0.0
    exact_tiny_checks = 0
    def close(a, b):
        nonlocal maxdiff
        maxdiff = max(maxdiff, abs(a-b))
        if not math.isclose(a, b, rel_tol=1e-10, abs_tol=1e-12):
            raise AssertionError(f"Enumeration mismatch {a} vs {b}")
    n = model["states"]
    for seq in sequences:
        obs = seq["observations"]
        length = len(obs)
        posterior = [[0.0]*n for _ in obs]
        A = [[0.0]*n for _ in range(n)]
        E = [[0.0]*n for _ in range(3)]
        total = 0.0
        for path in itertools.product(range(n), repeat=length):
            p = model["initial"][path[0]] * model["emission"][obs[0]][path[0]]
            for u in range(1, length):
                p *= model["transition"][path[u-1]][path[u]] * model["emission"][obs[u]][path[u]]
            total += p
            for u, state in enumerate(path):
                posterior[u][state] += p
                if u+1 < length:
                    A[state][path[u+1]] += p
                    E[obs[u]][state] += p # Legacy deliberately omits final emission.
        close(math.log(total), seq["log_likelihood"])
        for u in range(length):
            for k in range(n):
                close(posterior[u][k]/total, seq["forward"][u+1][k]*seq["backward"][u+1][k]*seq["scales"][u+1])
        for k in range(n):
            close(posterior[0][k]/total, seq["A0"][k])
            for l in range(n):
                close(A[k][l]/total+1e-25, seq["A"][k][l])
                if A[k][l] == 0.0:
                    if seq["A"][k][l] != 1e-25:
                        raise AssertionError("Transition cell with no contribution lost exact HMM_TINY")
                    exact_tiny_checks += 1
            for b in range(3):
                close(E[b][k]/total+1e-25, seq["E"][b][k])
                if E[b][k] == 0.0:
                    if seq["E"][b][k] != 1e-25:
                        raise AssertionError("Emission cell with no contribution lost exact HMM_TINY")
                    exact_tiny_checks += 1
    return {"sequences": len(sequences), "max_absolute_difference": maxdiff, "exact_tiny_cell_checks": exact_tiny_checks, "relative_tolerance": 1e-10, "absolute_tolerance": 1e-12}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", default="work/instrumented/psmc")
    parser.add_argument("--oracle", default="work/vanilla/psmc")
    a = parser.parse_args()
    raw = ROOT / "bench/raw/tests"
    raw.mkdir(parents=True, exist_ok=True)
    results = []
    def test(name, operation):
        try:
            detail = operation()
            results.append({"name": name, "status": "passed", "details": detail})
        except Exception as error:
            results.append({"name": name, "status": "failed", "error": str(error)})
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
        ("decoding", "tiny.psmcfa", ["-d"]),
        ("full_posterior", "tiny.psmcfa", ["-D"]),
        ("probability", "tiny.psmcfa", ["-s"]),
        ("divergence", "tiny.psmcfa", ["-T", "0.2"]),
        ("alpha", "tiny.psmcfa", ["-l", "0.2"]),
        ("cap", "tiny.psmcfa", ["-d", "-C", "1"]),
    ]
    for name, filename, args in cases:
        def pair(name=name, filename=filename, args=args):
            inp = "tests/fixtures/" + filename
            oracle = execute(a.oracle, base+args, inp, name+"-oracle")
            candidate = execute(a.candidate, base+args, inp, name+"-candidate")
            if oracle != candidate:
                raise AssertionError("Complete stdout byte mismatch (metadata allowlist empty)")
            numerical = output_diagnostics(oracle)
            if name == "finite_workload_30_iterations" and not numerical["finite_outside_initial_RI"]:
                raise AssertionError("Required finite 30-round workload has nonfinite numerical records")
            return {"output_sha256": __import__('hashlib').sha256(oracle).hexdigest(), "bytes": len(oracle), "arguments": base+args+[inp], "numerical_output": numerical}
        test("strict_"+name, pair)
    def aliases():
        left = execute(a.oracle, base, "tests/fixtures/aliases.psmcfa", "alias-source")
        right = execute(a.oracle, base, "tests/fixtures/aliases-canonical.psmcfa", "alias-canonical")
        assert left == right, "Character conversion differs from audited table"
    test("encoding_alias_equivalence", aliases)
    def boundaries():
        left = execute(a.oracle, base, "tests/fixtures/tiny.psmcfa", "boundaries-original")
        right = execute(a.oracle, base, "tests/fixtures/tiny-joined.psmcfa", "boundaries-joined")
        lks = lambda text: [x for x in text.splitlines() if x.startswith(b"LK\t")]
        assert lks(left) != lks(right), "Fixture failed to expose boundary changes"
        return {"note": "Joining independent records changes likelihood; harness detects it"}
    test("sequence_boundaries_negative_control", boundaries)
    def rng_check():
        libc = ctypes.CDLL(None)
        libc.srand48.argtypes = [ctypes.c_long]
        libc.drand48.restype = ctypes.c_double
        for seed in [0, 1, 20261009, 4294967295]:
            libc.srand48(seed)
            state = ((seed & 0xffffffff)<<16) | 0x330e
            for _ in range(100):
                state = (0x5deece66d*state+0xb) & ((1<<48)-1)
                assert libc.drand48() == state/(1<<48), "LCG differs from linked libc"
        return {"exact_double_draw_comparisons": 400}
    test("glibc_rng_replay", rng_check)
    workload = json.loads((ROOT / "bench/workload.json").read_text())
    for rep in workload["bootstrap"]["replicates"]:
        def bootstrap(rep=rep):
            trace = raw / f"bootstrap-{rep['id']:02d}.jsonl"
            candidate = execute(a.candidate, base+["-b"], "tests/fixtures/blocks.psmcfa", f"bootstrap-{rep['id']:02d}-candidate",
                {"PSMC_SEED": str(rep["seed"]), "PSMC_BOOTSTRAP_TRACE": str(trace)})
            oracle = execute(a.oracle, base, rep["file"], f"bootstrap-{rep['id']:02d}-oracle")
            assert candidate == oracle, "C -b differs from vanilla fit of materialized replay"
            actual = [json.loads(x) for x in trace.read_text().splitlines()]
            draws = [x for x in actual if x["event"] == "bootstrap_draw"]
            assert len(draws) == len(rep["draws"])
            for actual_draw, expected in zip(draws, rep["draws"]):
                assert all(actual_draw[key] == value for key, value in expected.items()), "Bootstrap draw/stop mismatch"
            return {"seed": rep["seed"], "draws": len(draws), "accepted": len(rep["ordered_block_indices"]), "raw_length_bins": rep["raw_length_bins"]}
        test(f"bootstrap_replay_{rep['id']:02d}", bootstrap)
    enum_path = ROOT / "tests/fixtures/enumeration.psmcfa"
    write_fasta(enum_path, [("short_mixed", "TKNNTK"), ("missing", "NNNN"), ("single", "K")])
    def snapshots():
        path = raw / "enumeration-snapshot.jsonl"
        args = ["-i", "tests/fixtures/fixed.par", "-N", "1"]
        out = execute(a.candidate, args, "tests/fixtures/enumeration.psmcfa", "snapshot-candidate", {"PSMC_SEED": "7", "PSMC_SNAPSHOT": str(path)})
        oracle = execute(a.oracle, args, "tests/fixtures/enumeration.psmcfa", "snapshot-oracle")
        assert out == oracle, "Active snapshots changed printed results"
        events = [json.loads(x) for x in path.read_text().splitlines()]
        details = enumeration_check(events)
        # Independently verify ordered count aggregation and full-count entropy.
        agg = next(x for x in events if x["event"] == "aggregate")
        sequences = [x for x in events if x["event"] == "sequence" and x["iteration"] == 1]
        if not sequences:
            raise AssertionError("Aggregate check has no sequence snapshots")
        n = len(agg["A0"])
        summed_A0 = [0.0]*n
        summed_A = [[0.0]*n for _ in range(n)]
        summed_E = [[0.0]*n for _ in range(3)]
        summed_LL = 0.0
        for seq in sequences:
            summed_LL += seq["log_likelihood"]
            for k in range(n):
                summed_A0[k] += seq["A0"][k]
                for l in range(n):
                    summed_A[k][l] += seq["A"][k][l]
            for b in range(2):
                for k in range(n):
                    summed_E[b][k] += seq["E"][b][k]
        if (summed_A0 != agg["A0"] or summed_A != agg["A"] or
            summed_E != agg["E"] or summed_LL != agg["log_likelihood"]):
            raise AssertionError("C aggregate differs from explicit input-order scalar additions")
        independent_Q0 = 0.0
        for k in range(n):
            total = 0.0
            for b in range(2):
                total += agg["E"][b][k]
            for b in range(2):
                independent_Q0 += agg["E"][b][k]*math.log(agg["E"][b][k]/total)
        for k in range(n):
            total = 0.0
            for l in range(n):
                total += agg["A"][k][l]
            for l in range(n):
                independent_Q0 += agg["A"][k][l]*math.log(agg["A"][k][l]/total)
        if not math.isclose(independent_Q0, agg["stored_Q0"], rel_tol=1e-10, abs_tol=1e-12):
            raise AssertionError("Independent full-count Q normalizer mismatch")
        details.update({"ordered_aggregate_exact": True,
                        "independent_Q0": independent_Q0,
                        "stored_Q0": agg["stored_Q0"],
                        "Q0_absolute_difference": abs(independent_Q0-agg["stored_Q0"])})
        # Candidate Q uses independently derived normalizer, not the stored value.
        models = {x["model_id"]: x for x in events if x["event"] == "model"}
        maxq = 0.0
        checked = 0
        skipped = {"nonpositive_probability": 0, "nonfinite_model": 0, "nonfinite_objective": 0}
        objectives = 0
        for event in events:
            if event["event"] != "objective":
                continue
            objectives += 1
            m = models[event["model_id"]]
            probabilities = [v for row in m["transition"] for v in row]
            probabilities += [v for row in m["emission"][:2] for v in row]
            if any(isinstance(v, (int,float)) and v <= 0.0 for v in probabilities):
                # hmm_Q returns its sentinel at the first <=0 check, unless an
                # earlier NaN already contaminated arithmetic; NaNs alone do
                # not trigger that branch. Here <=0 always eventually returns.
                if event["negative_Q"] != 1e300:
                    raise AssertionError("Nonpositive candidate did not return legacy +1e300 negative-Q sentinel")
                skipped["nonpositive_probability"] += 1
                continue
            if any(not isinstance(v, (int,float)) or not math.isfinite(v) for v in probabilities):
                skipped["nonfinite_model"] += 1
                continue
            if not isinstance(event["negative_Q"], (int,float)) or not math.isfinite(event["negative_Q"]):
                skipped["nonfinite_objective"] += 1
                raise AssertionError("Finite positive candidate model produced nonfinite Q")
            q = 0.0
            for b in range(2):
                for k in range(m["states"]):
                    q += agg["E"][b][k]*math.log(m["emission"][b][k])
            for k in range(m["states"]):
                for l in range(m["states"]):
                    q += agg["A"][k][l]*math.log(m["transition"][k][l])
            q -= independent_Q0
            diff = abs(q + event["negative_Q"])
            maxq = max(maxq, diff)
            if not math.isclose(q, -event["negative_Q"], rel_tol=1e-10, abs_tol=1e-12):
                raise AssertionError("Independent candidate-Q mismatch")
            checked += 1
        if checked == 0 or objectives == 0:
            raise AssertionError("No finite objective candidates were independently checked")
        details.update({"candidate_Q_checks": checked, "candidate_Q_max_absolute_difference": maxq,
                        "objective_events": objectives, "invalid_candidate_categories": skipped,
                        "snapshot": "bench/raw/tests/enumeration-snapshot.jsonl.gz", "events": len(events)})
        with gzip.open(str(path)+".gz", "wb") as f:
            f.write(path.read_bytes())
        path.unlink()
        return details
    test("independent_path_enumeration_and_Q", snapshots)
    def seeded_random():
        env = {"PSMC_SEED": "20261009"}
        one = execute(a.candidate, base+["-I", "0.1"], "tests/fixtures/tiny.psmcfa", "random-one", env)
        two = execute(a.candidate, base+["-I", "0.1"], "tests/fixtures/tiny.psmcfa", "random-two", env)
        assert one == two
        return {"scope": "instrumented replay only; unmodified C has no seed flag"}
    test("random_initialization_replay", seeded_random)
    failures = [x for x in results if x["status"] != "passed"]
    save(ROOT / "bench/differential.json", {"scope": "Phase 0 C versus instrumented C, plus independent path enumeration using C model matrices",
         "status": "failed" if failures else "passed", "candidate": a.candidate, "candidate_sha256": sha256(ROOT/a.candidate),
         "oracle": a.oracle, "oracle_sha256": sha256(ROOT/a.oracle), "strict_metadata_allowlist": [], "run_numerical_diagnostics": RUN_DIAGNOSTICS,
         "cases": results, "passed": len(results)-len(failures), "failed": len(failures),
         "not_validated": ["Rust implementation", "accelerated CPU or CUDA backend", "independent PSMC parameter-to-matrix derivation", "real genome EM or bootstraps", "future equivalent-mode tolerance contract", "simulation and CpG binary input"]})
    print(json.dumps({"passed": len(results)-len(failures), "failed": failures}))
    return bool(failures)

if __name__ == "__main__":
    sys.exit(main())

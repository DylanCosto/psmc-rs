"""Shared, dependency-free helpers for Phase 0; no production inference code."""
import hashlib
import json
from pathlib import Path
import time
import subprocess
import re
import os
import signal
import threading

ROOT = Path(__file__).resolve().parents[1]

def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def save(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")

def read_fasta(path):
    records = []
    for line in Path(path).read_text().splitlines():
        if line.startswith(">"):
            records.append([line[1:].split()[0], ""])
        elif line.strip():
            records[-1][1] += line.strip()
    return records

def write_fasta(path, records):
    with Path(path).open("w") as f:
        for name, seq in records:
            f.write(f">{name}\n")
            for i in range(0, len(seq), 60):
                f.write(seq[i:i+60] + "\n")

def draw_bootstrap(records, seed):
    """Independent replay of audited srand48/drand48 and psmc_resamp stop rule.

    Fixture lengths fit C int; this is not a portable replacement for the
    original RNG on arbitrary libc platforms or oversized data.
    """
    state = ((seed & 0xffffffff) << 16) | 0x330e
    target = sum(len(seq) for _, seq in records)
    total = 0
    selected, draws = [], []
    while True:
        state = (0x5deece66d * state + 0xb) & ((1 << 48) - 1)
        index = int(len(records) * state / (1 << 48))
        length = len(records[index][1])
        remaining, overshoot = target-total, total+length-target
        accepted = overshoot <= 0 or (overshoot > 0 and remaining > 0 and overshoot < remaining)
        stop = remaining >= 0 and overshoot >= 0
        before = total
        if accepted:
            selected.append(index)
            total += length
        draws.append({"source_index": index, "length": length, "accepted": bool(accepted), "before_length": before, "after_length": total, "target_length": target, "stop": bool(stop)})
        if stop:
            break
    return selected, draws

def normalize_output(text):
    # IT contains optimizer evaluation counts and is scientifically relevant.
    # MM contains numerical C_pi and must NOT be broadly removed.
    # On this pinned C-versus-C stack no fields need an allowlist.
    return text

def nonfinite_records(text):
    records = []
    rd = None
    for line in text.splitlines():
        if line.startswith("RD\t"):
            rd = int(line.split()[1])
        if re.search(r"(?i)(?<![a-z])[-+]?(?:nan|inf)(?![a-z])", line):
            if not (rd == 0 and line == "RI\tinf"):
                records.append({"round": rd, "record": line})
    return records

def timed_run(command, outbase, *, cwd=ROOT, env=None, timeout=180):
    """Unmodified executable under /usr/bin/time; separate output for each run."""
    outbase = Path(outbase)
    outbase.parent.mkdir(parents=True, exist_ok=True)
    stats = outbase.with_suffix(".time")
    start = time.perf_counter()
    with outbase.with_suffix(".psmc").open("w") as out, outbase.with_suffix(".stderr").open("w") as err:
        process = subprocess.Popen(["/usr/bin/time", "-f", "%e %U %S %M", "-o", str(stats), *map(str, command)], cwd=cwd, env=env, stdout=out, stderr=err, start_new_session=True)
        expired = threading.Event()
        def expire():
            expired.set()
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        watchdog = threading.Timer(timeout, expire)
        watchdog.daemon = True
        watchdog.start()
        try:
            returncode = process.wait() # blocking waitpid; avoids timeout polling/backoff in short benchmarks
        finally:
            watchdog.cancel()
        if expired.is_set():
            raise TimeoutError(f"Timed out after {timeout}s: {command}")
    elapsed = time.perf_counter()-start
    values = stats.read_text().strip().splitlines()[-1].split()
    output = outbase.with_suffix(".psmc")
    return {"command": list(map(str, command)), "exit_code": returncode,
            "wall_seconds": elapsed, "time_wall_seconds": float(values[0]),
            "user_seconds": float(values[1]), "system_seconds": float(values[2]),
            "peak_rss_kib": int(values[3]), "output_sha256": sha256(output),
            "output": str(output.relative_to(ROOT)),
            "optimizer_evaluations": [int(line.split()[1]) for line in output.read_text().splitlines() if line.startswith("IT\t")],
            "nonfinite_records_beyond_initial_RI": nonfinite_records(output.read_text())}

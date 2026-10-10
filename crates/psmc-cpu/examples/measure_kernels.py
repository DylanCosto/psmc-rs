#!/usr/bin/env python3
"""Record alternating isolated HMM timings; run only during a quiet benchmark window."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import time


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, default=root / "target/release/examples/kernel_bench")
    parser.add_argument("--output", type=Path, default=root / "bench/phase2-kernel-benchmark.json")
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--cpu", type=int, default=min(os.sched_getaffinity(0)))
    args = parser.parse_args()
    if args.samples < 3:
        parser.error("at least three paired samples are required")
    binary = args.binary.resolve()
    output = args.output.resolve()
    raw = output.parent / "raw" / output.stem
    raw.mkdir(parents=True, exist_ok=True)
    sources = [root / "crates/psmc-cpu/src/lib.rs", Path(__file__).with_name("kernel_bench.rs"), root / "crates/psmc-core/src/hmm.rs"]
    guarded = [binary, *sources]
    before = {str(path): digest(path) for path in guarded}
    runs = []
    for states, bins, repeats in [(23, 4400, 20), (64, 17600, 5)]:
        for sample in range(args.samples):
            modes = ["dense", "cpu"] if sample % 2 == 0 else ["cpu", "dense"]
            for mode in modes:
                label = f"k{states}-{sample + 1}-{mode}"
                command = [str(binary), mode, str(states), str(bins), str(repeats), "3"]
                rss_path = raw / f"{label}.rss.txt"
                started = time.perf_counter()
                result = subprocess.run(
                    ["/usr/bin/time", "-f", "%M", "-o", str(rss_path), *command],
                    capture_output=True, text=True, check=True,
                    preexec_fn=lambda: os.sched_setaffinity(0, {args.cpu}),
                )
                elapsed = time.perf_counter() - started
                (raw / f"{label}.stdout.json").write_text(result.stdout)
                (raw / f"{label}.stderr.txt").write_text(result.stderr)
                row = json.loads(result.stdout)
                row.update(sample=sample + 1, command=command,
                           process_wall_seconds=elapsed,
                           process_peak_rss_kib=int(rss_path.read_text()),
                           stdout_sha256=hashlib.sha256(result.stdout.encode()).hexdigest())
                runs.append(row)
    after = {str(path): digest(path) for path in guarded}
    if before != after:
        raise RuntimeError("a guarded executable/source changed during timing; raw data retained, report not accepted")
    summary = []
    for states in [23, 64]:
        subset = [row for row in runs if row["states"] == states]
        assert len({row["checksum"] for row in subset}) == 1
        median = {mode: statistics.median(row["seconds"] for row in subset if row["backend"] == mode) for mode in ["dense", "cpu"]}
        summary.append(dict(states=states, dense_median_seconds=median["dense"],
                            cpu_median_seconds=median["cpu"],
                            dense_over_cpu=median["dense"] / median["cpu"],
                            all_exact_checks=True, samples_each=args.samples))
    report = dict(
        schema=1, created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        scope="Isolated dense Rust oracle versus strict CPU workspace HMM; synthetic periodic observations, three unequal-length records; no EM, scheduler, C timing, or real workload claim.",
        binary=str(binary), binary_sha256=before[str(binary)],
        sources={str(path.relative_to(root)): before[str(path)] for path in sources},
        source_and_binary_unchanged_during_measurement=True,
        toolchain=subprocess.check_output(["rustc", "-Vv"], text=True, cwd=root),
        platform=platform.platform(), allowed_affinity=sorted(os.sched_getaffinity(0)),
        child_affinity=[args.cpu],
        warmup="Each process first exact-checks all forward/backward/scales/counts against the dense oracle outside timing. A fresh workspace is created before timed work; first message allocation is included.",
        memory_note="Process RSS and process wall include both implementations in the correctness warmup; diagnostic only, not backend-isolated memory/performance metrics. Compare the internal seconds field.",
        summary=summary, runs=runs,
    )
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

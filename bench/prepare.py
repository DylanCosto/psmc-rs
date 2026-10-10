#!/usr/bin/env python3
"""Create synthetic fixtures and an ordered 30-replicate bootstrap manifest."""
import gzip
import random
import subprocess
from common import ROOT, read_fasta, write_fasta, draw_bootstrap, sha256, save

def main():
    fixtures = ROOT / "tests/fixtures"
    fixtures.mkdir(exist_ok=True, parents=True)
    rng = random.Random(20261009)
    records = []
    for index, length in enumerate([3200, 4173, 5827]):
        # Unequal records, changing heterozygosity and contiguous missing spans.
        seq = "".join("N" if 450 <= i % 1600 < 520 else "K" if rng.random() < (0.025 if (i // 500) % 2 else 0.08) else "T" for i in range(length))
        records.append((f"synthetic_{index+1}", seq))
    write_fasta(fixtures / "workload.psmcfa", records)
    small = [("mixed_a", "TTTKTTNNTKTTTTKTTTNTKT"), ("mixed_b", "KTTTNNNTTTKTTKTTTTTTTTKTTTTN")]
    write_fasta(fixtures / "tiny.psmcfa", small)
    write_fasta(fixtures / "tiny-joined.psmcfa", [("joined", "".join(x[1] for x in small))])
    write_fasta(fixtures / "missing.psmcfa", [("all_missing", "N"*13)])
    write_fasta(fixtures / "single.psmcfa", [("single", "K")])
    write_fasta(fixtures / "repeated.psmcfa", [small[0], small[1], small[0]])
    aliases = "ACGTacgt0KMRWSYkmrwsy1NBX?"
    write_fasta(fixtures / "aliases.psmcfa", [("aliases", aliases)])
    mapped = "".join("T" if x in "ACGTacgt0" else "K" if x in "KMRWSYkmrwsy1" else "N" for x in aliases)
    write_fasta(fixtures / "aliases-canonical.psmcfa", [("aliases", mapped)])
    (fixtures / "tiny.psmcfa.gz").write_bytes(gzip.compress((fixtures / "tiny.psmcfa").read_bytes(), mtime=0))
    (fixtures / "fixed.par").write_text("2+2 0.06 0.015 15 1 1.3\n")
    (fixtures / "grid.par").write_text("2+2 0.06 0.015 -1 1 1.3 0 0.5 2 10\n")
    split_command = ["work/vanilla/utils/splitfa", "tests/fixtures/workload.psmcfa", "1000"]
    split = subprocess.run(split_command, cwd=ROOT, check=True, capture_output=True).stdout
    (fixtures / "blocks.psmcfa").write_bytes(split)
    blocks = read_fasta(fixtures / "blocks.psmcfa")
    reps = []
    repdir = fixtures / "bootstrap"
    repdir.mkdir(exist_ok=True)
    for index in range(30):
        seed = 20261009 + index
        indices, draws = draw_bootstrap(blocks, seed)
        path = repdir / f"replicate-{index:02d}.psmcfa"
        write_fasta(path, [blocks[i] for i in indices])
        reps.append({"id": index, "seed": seed, "ordered_block_indices": indices,
                     "raw_length_bins": sum(len(blocks[i][1]) for i in indices),
                     "file": str(path.relative_to(ROOT)), "sha256": sha256(path), "draws": draws})
    save(ROOT / "bench/workload.json", {
        "schema_version": 1, "scope": "synthetic Phase 0 harness validation only",
        "real_workload": {"status": "not_run", "bootstrap_processes_already_parallel": True,
            "replicates": 30, "source": "direct user clarification",
            "missing": ["exact command and p/N/t/r/i/I settings", "worker count and scheduling policy", "authorized input location and hash", "bin size", "record boundaries", "splitfa command", "assembly and mask provenance", "original workflow hardware", "whether preprocessing and plotting are timed"],
            "speedup_claim": None},
        "fixture_provenance": "generated here; no genome or public sample data",
        "generator": {"script": "bench/prepare.py", "seed": 20261009, "rng": "Python random.Random / Mersenne Twister; generated files and SHA256 are canonical"},
        "input": {"file": "tests/fixtures/workload.psmcfa", "sha256": sha256(fixtures / "workload.psmcfa"),
            "encoding": "T=nonheterozygous bin, K=heterozygous bin, N=missing bin",
            "bin_size_bp": None, "bin_size_note": "synthetic observations; no implied biological coordinate scale",
            "records": [{"id": name, "length_bins": len(seq), "callable_bins": len(seq)-seq.count("N"), "heterozygous_bins": seq.count("K"), "sequence_sha256": __import__('hashlib').sha256(seq.encode()).hexdigest()} for name, seq in records]},
        "split": {"command": split_command, "file": "tests/fixtures/blocks.psmcfa", "sha256": sha256(fixtures / "blocks.psmcfa"),
                  "block_size_bins": 1000, "records": [{"id": n, "length_bins": len(s)} for n,s in blocks]},
        "bootstrap": {"rng": "POSIX/glibc srand48/drand48 LCG; x0=(seed32<<16)|0x330e; x=(0x5deece66d*x+0xb) mod 2^48", "procedure": "audited original total-raw-length stopping rule; independent Python replay must pass C trace comparison", "replicates": reps},
        "benchmark": {"binary": "work/vanilla/psmc", "arguments": ["-p", "4+5*3+4", "-N", "5", "-t", "15", "-r", "4", "-I", "0"],
            "states": 23, "workers_to_test": [1,2,4], "repeated_batches_per_worker_count": 3,
            "timed_scope": "launch through inference exit on identical materialized inputs; includes process startup and file I/O; excludes bootstrap materialization and plotting",
            "limitations": "five-iteration PARTIAL-TRAJECTORY smoke only; full30-iteration synthetic23-state reference failed and is retained in bench/failed-23state.json. Cannot estimate full-fit or whole-genome speedup or optimal production concurrency"},
        "compatibility_recommendation": "same legacy model and inference, equivalent acceleration only after numerical contract review; retain pinned vanilla for strict reproduction",
        "future_equivalent_tolerances": {"status": "not_defined", "reason": "missing validation plan and real trajectory evidence; generic algebra tolerances are not a PSMC acceptance contract"}
    })
    print(f"Prepared {len(records)} input records, {len(blocks)} blocks, and {len(reps)} materialized replicates")

if __name__ == "__main__":
    main()

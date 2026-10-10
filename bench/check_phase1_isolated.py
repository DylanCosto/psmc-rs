#!/usr/bin/env python3
"""Rebuild and compare literal model/optimizer C and Rust differential fixtures.

Run from any directory. Requires the pinned source under work/vanilla, GCC,
Rust 1.90.0, and the system libm used by the project reference build.
All retained commands and artifact paths are relative to the project root.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import struct
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parent.parent
DEST = Path("bench/phase-1-isolated")
PIN = "82fa2ada83ee463fe1251b562ae3d60e82d7ad6a"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def portable(text: str) -> str:
    return text.replace(str(ROOT), "${PROJECT}")


def run(argv: list[str]) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(argv, cwd=ROOT, check=True, capture_output=True,
                          env={**os.environ, "LC_ALL": "C"})


def compare(c_data: bytes, rust_data: bytes) -> dict:
    if len(c_data) != len(rust_data) or len(c_data) % 8:
        return {"passed": False, "error": "output sizes differ or are not f64-aligned",
                "c_bytes": len(c_data), "rust_bytes": len(rust_data)}
    mismatches = []
    nan_pairs = 0
    finite_pairs = 0
    for i, ((a,), (b,)) in enumerate(zip(struct.iter_unpack("=d", c_data),
                                       struct.iter_unpack("=d", rust_data))):
        if math.isnan(a) and math.isnan(b):
            nan_pairs += 1
        if math.isfinite(a) and math.isfinite(b):
            finite_pairs += 1
        if c_data[8*i:8*i+8] != rust_data[8*i:8*i+8]:
            mismatches.append({"f64_index": i, "c": a.hex(), "rust": b.hex(),
                               "both_nan": math.isnan(a) and math.isnan(b)})
    return {"passed": not mismatches, "byte_exact": not mismatches,
            "f64_values": len(c_data) // 8, "finite_pairs": finite_pairs,
            "nan_pairs": nan_pairs, "byte_mismatches": len(mismatches),
            "first_mismatches": mismatches[:20]}


def main() -> int:
    os.chdir(ROOT)
    (DEST / "bin").mkdir(parents=True, exist_ok=True)
    (DEST / "raw").mkdir(exist_ok=True)
    vanilla = Path("work/vanilla")
    for name in ["core.c", "khmm.c", "kmin.c", "psmc.h", "khmm.h", "kmin.h"]:
        if not (vanilla / name).is_file():
            raise SystemExit(f"Missing pinned reference: {vanilla / name}. Run reference/build.py first.")
    pin_record = json.loads(Path("reference/build-vanilla.json").read_text())
    if pin_record["source_commit"] != PIN:
        raise SystemExit("Reference provenance does not identify the expected PSMC commit.")
    archive = Path("work/psmc-source-vanilla.tar")
    if not archive.is_file() or digest(archive) != pin_record["source_archive_sha256"]:
        raise SystemExit("The pinned source archive is missing or does not match reference/build-vanilla.json.")
    with tarfile.open(archive) as tf:
        for name in ["core.c", "khmm.c", "kmin.c", "psmc.h", "khmm.h", "kmin.h"]:
            archived = tf.extractfile(name)
            if archived is None or archived.read() != (vanilla / name).read_bytes():
                raise SystemExit(f"Reference source differs from the pinned archive: {vanilla / name}")
    rust_version = run(["rustc", "--version", "--verbose"]).stdout.decode()
    if not rust_version.startswith("rustc 1.90.0 "):
        raise SystemExit("This recorded gate is pinned to Rust 1.90.0; select the project toolchain.")
    gcc_version = run(["gcc", "--version"]).stdout.decode().splitlines()[0]
    commands: list[list[str]] = []
    source_hashes: dict[str, str] = {}
    binary_hashes: dict[str, str] = {}
    output_hashes: dict[str, str] = {}
    results: dict[str, dict] = {}
    diagnostics: dict[str, str] = {}
    for kind, c_files, cases in [("model", ["core.c", "khmm.c"], 60),
                                 ("optimizer", ["kmin.c"], 16)]:
        c_binary = DEST / "bin" / f"{kind}-c"
        rust_binary = DEST / "bin" / f"{kind}-rust"
        c_source = DEST / f"{kind}-check.c"
        rust_source = DEST / f"{kind}-check.rs"
        compile_c = ["gcc", "-g", "-Wall", "-O2", "-Wno-unused-function",
                     "-ffp-contract=off", f"-fdebug-prefix-map={ROOT}=/psmc-rs",
                     "-I", str(vanilla), str(c_source),
                     *[str(vanilla / x) for x in c_files], "-lm", "-o", str(c_binary)]
        compile_rust = ["rustc", "--edition=2024", "-C", "opt-level=2",
                        "-C", "codegen-units=1", "--remap-path-prefix",
                        f"{ROOT}=/psmc-rs", str(rust_source), "-o", str(rust_binary)]
        for cmd in [compile_c, compile_rust]:
            result = run(cmd)
            commands.append([portable(x) for x in cmd])
            if result.stderr:
                diagnostics[str(cmd[-1])] = portable(result.stderr.decode())
        for path in [c_source, rust_source, *[vanilla / x for x in c_files]]:
            source_hashes[str(path)] = digest(path)
        for binary in [c_binary, rust_binary]:
            binary_hashes[str(binary)] = digest(binary)
        data = []
        for name, binary in [("c", c_binary), ("rust", rust_binary)]:
            result = run([str(binary)])
            commands.append([str(binary)])
            output = DEST / "raw" / f"{kind}-{name}.bin"
            output.write_bytes(result.stdout)
            output_hashes[str(output)] = digest(output)
            data.append(result.stdout)
        results[kind] = {"cases": cases, **compare(*data)}
    for name in ["model.rs", "optimizer.rs", "math.rs", "rng.rs"]:
        path = Path("crates/psmc-core/src") / name
        source_hashes[str(path)] = digest(path)
    for name in ["psmc.h", "khmm.h", "kmin.h"]:
        source_hashes[str(vanilla / name)] = digest(vanilla / name)
    for path in [Path(__file__).relative_to(ROOT), Path("rust-toolchain.toml"),
                 Path("reference/build-vanilla.json")]:
        source_hashes[str(path)] = digest(path)
    libraries = {}
    for line in run(["ldd", str(DEST / "bin/model-c")]).stdout.decode().splitlines():
        match = re.search(r"(/[^\s()]+)", line)
        if match and Path(match.group(1)).is_file():
            lib = Path(match.group(1))
            libraries[lib.name] = {"path": str(lib), "sha256": digest(lib)}
    report = {
        "scope": "isolated literal scalar model and Hooke-Jeeves; not a full-EM or performance gate",
        "passed": all(r["passed"] for r in results.values()),
        "source_commit": PIN,
        "reference_source": f"https://github.com/lh3/psmc/tree/{PIN}",
        "reference_license": "reference/LICENSE.psmc.txt",
        "reference_source_verification": "archive SHA-256 verified against build-vanilla.json; all compiled C sources and project headers byte-match archive members",
        "reference_archive_sha256": digest(archive),
        "platform": {"system": platform.system(), "machine": platform.machine(),
                     "byte_order": sys.byteorder, "double_bytes": struct.calcsize("d")},
        "compilers": {"gcc": gcc_version, "rustc": rust_version.strip()},
        "libraries": libraries,
        "commands": commands,
        "source_sha256": source_hashes,
        "binary_sha256": binary_hashes,
        "raw_output_sha256": output_hashes,
        "compiler_diagnostics": diagnostics,
        "results": results,
        "limitations": ["Synthetic fixtures only; no biological-validation claim.",
                        "No timing or peak-memory benchmark in this isolated gate.",
                        "No CUDA, optimized CPU, or cross-platform compatibility claim.",
                        "Native-endian binary streams are interpretable using the recorded byte order.",
                        "Public Model fields and Settings shape are copied into this isolated harness; integration is validated separately."],
    }
    (DEST / "results.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"passed": report["passed"], "results": results,
                      "report": str(DEST / "results.json")}, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

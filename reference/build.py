#!/usr/bin/env python3
"""Build a pinned, unmodified C oracle and optional instrumented/profiling copies."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]
COMMIT = "82fa2ada83ee463fe1251b562ae3d60e82d7ad6a"
URL = "https://github.com/lh3/psmc.git"
FLAGS = "-g -Wall -O2 -Wno-unused-function -ffp-contract=off -fdebug-prefix-map="

def run(args, **kwargs):
    result = subprocess.run([str(x) for x in args], text=True, capture_output=True, **kwargs)
    if result.returncode:
        raise RuntimeError(f"Command failed: {args}\n{result.stdout}\n{result.stderr}")
    return result

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, help="Existing lh3/psmc checkout containing pinned commit")
    p.add_argument("--instrumented", action="store_true")
    p.add_argument("--gprof", action="store_true")
    p.add_argument("--zlib-include", type=Path, help="Extracted zlib headers if development package is absent")
    a = p.parse_args()
    work = ROOT / "work"
    work.mkdir(exist_ok=True)
    source = a.source.resolve() if a.source else work / "upstream"
    if not source.exists():
        run(["git", "clone", URL, source])
    actual = run(["git", "-C", source, "rev-parse", f"{COMMIT}^{{commit}}"]).stdout.strip()
    if actual != COMMIT:
        raise RuntimeError("Pinned commit not available")
    mode = "instrumented" if a.instrumented else "gprof" if a.gprof else "vanilla"
    if a.instrumented and a.gprof:
        p.error("Use separate instrumented and gprof builds")
    archive = work / f"psmc-source-{mode}.tar"
    run(["git", "-C", source, "archive", "--format=tar", "-o", archive, COMMIT])
    target = work / mode
    if target.exists():
        p.error(f"Build already exists: {target}. Choose a fresh project copy to rebuild.")
    pristine = work / f"source-{mode}"
    pristine.mkdir()
    with tarfile.open(archive) as tf:
        tf.extractall(pristine, filter="data")
    if a.instrumented:
        run([sys.executable, ROOT / "reference/instrument.py", pristine, target])
    else:
        shutil.copytree(pristine, target)
    flags = FLAGS + str(target) + "=/psmc"
    if a.gprof:
        flags += " -pg"
    if a.zlib_include:
        flags += " -I" + str(a.zlib_include.resolve())
    commands = [
        ["make", "-j2", "CC=gcc", f"CFLAGS={flags}", f"CCFLAGS={flags}", "LIBS=-lm -l:libz.so.1"],
        ["make", "-C", "utils", "-j2", "CC=gcc", f"CFLAGS={flags}", "LIBS=-lm -l:libz.so.1", "splitfa", "fq2psmcfa"],
    ]
    log = []
    for command in commands:
        result = run(command, cwd=target)
        log.extend([result.stdout, result.stderr])
    (ROOT / "reference" / f"build-{mode}.log").write_text("\n".join(log).replace(str(ROOT), "${PROJECT}"))
    libs = run(["ldd", target / "psmc"]).stdout
    library_files = {}
    for line in libs.splitlines():
        parts = line.split()
        if "=>" in parts and len(parts) > 2 and Path(parts[2]).is_file():
            library_files[parts[0]] = {"path": parts[2], "sha256": digest(parts[2])}
    record = {
        "source_url": URL, "source_commit": COMMIT, "source_archive_sha256": digest(archive),
        "mode": mode, "source_numerical_algorithm_modified": False,
        "compiler": run(["gcc", "--version"]).stdout.splitlines()[0],
        "compiler_target": run(["gcc", "-dumpmachine"]).stdout.strip(),
        "cflags": flags.replace(str(target), "${BUILD_DIR}").replace(str(ROOT), "${PROJECT}"),
        "link_flags": flags.replace(str(target), "${BUILD_DIR}").replace(str(ROOT), "${PROJECT}"),
        "linked_libraries": library_files,
        "libc": run(["ldd", "--version"]).stdout.splitlines()[0],
        "os": platform.platform(), "architecture": platform.machine(),
        "commands": [[x.replace(str(target), "${BUILD_DIR}").replace(str(ROOT), "${PROJECT}") for x in cmd] for cmd in commands],
        "executables": {name: {"path": f"work/{mode}/{name}", "sha256": digest(target / name)} for name in ["psmc", "utils/splitfa", "utils/fq2psmcfa"]},
        "notes": ["No fast-math or reduced precision; upstream O2 retained.", "Floating-point contraction explicitly disabled on the pinned x86-64 baseline target.", "Debug paths remapped for portable executable digests.", "Instrumented and gprof builds must not be used for headline timings."],
    }
    if a.instrumented:
        record["instrument_script_sha256"] = digest(ROOT / "reference/instrument.py")
    if a.zlib_include:
        record["zlib_headers_sha256"] = {name: digest(a.zlib_include / name) for name in ["zlib.h", "zconf.h"]}
    (ROOT / "reference" / f"build-{mode}.json").write_text(json.dumps(record, indent=2) + "\n")
    shutil.copy2(pristine / "LICENSE.txt", ROOT / "reference/LICENSE.psmc.txt")
    print(json.dumps({"mode": mode, "commit": COMMIT, "binary_sha256": digest(target / "psmc")}))

if __name__ == "__main__":
    main()

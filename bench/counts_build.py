#!/usr/bin/env python3
"""Build the pinned release Rust CLI and record portable build provenance."""
from __future__ import annotations

import ctypes
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
REPORT = Path("bench/counts-build.json")
BINARY = Path("target/release/psmc-rs")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def portable(text: str) -> str:
    return text.replace(str(ROOT), "${PROJECT}").replace(str(Path.home()), "${USER_HOME}")


def source_hashes() -> dict[str, str]:
    files = [Path("Cargo.toml"), Path("Cargo.lock"), Path("rust-toolchain.toml")]
    files += sorted(Path("crates").rglob("*.rs"))
    files += sorted(Path("crates").rglob("Cargo.toml"))
    if Path(".cargo/config.toml").exists():
        files.append(Path(".cargo/config.toml"))
    return {str(path): sha256(path) for path in files}


def command(argv: list[str], *, env: dict | None = None) -> str:
    result = subprocess.run(argv, cwd=ROOT, env=env, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def system_info() -> dict:
    cpu_fields = {}
    for line in Path("/proc/cpuinfo").read_text().splitlines():
        if ":" not in line:
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        if key in ["model name", "vendor_id", "cpu family", "model", "stepping", "flags"]:
            cpu_fields.setdefault(key, value)
    memory = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, value = line.split(":", 1)
        if key in ["MemTotal", "SwapTotal"]:
            memory[key] = value.strip()
    release = {}
    for line in Path("/etc/os-release").read_text().splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            if key in ["NAME", "VERSION", "VERSION_ID", "ID", "PRETTY_NAME"]:
                release[key] = value.strip('"')
    return {"system": platform.system(), "kernel": platform.release(),
            "architecture": platform.machine(), "byte_order": sys.byteorder,
            "os_release": release, "cpu": cpu_fields, "logical_cpu_count": os.cpu_count(),
            "process_cpu_affinity": sorted(os.sched_getaffinity(0)), "memory": memory}


def library_info(binary: Path) -> dict:
    libraries = {}
    for line in command(["ldd", str(binary)]).splitlines():
        match = re.search(r"(/[^\s()]+)", line)
        if match and Path(match.group(1)).is_file():
            path = Path(match.group(1))
            libraries[path.name] = {"path": portable(str(path)), "sha256": sha256(path)}
    libc = ctypes.CDLL("libc.so.6")
    libc.gnu_get_libc_version.restype = ctypes.c_char_p
    glibc_version = libc.gnu_get_libc_version().decode()
    zlib = ctypes.CDLL("libz.so.1")
    zlib.zlibVersion.restype = ctypes.c_char_p
    versions = {"libc": glibc_version, "libm": f"glibc {glibc_version}",
                "zlib": zlib.zlibVersion().decode()}
    return {"linked_files": libraries, "versions": versions}


def main() -> int:
    os.chdir(ROOT)
    from phase3_common import resource_policy
    policy = resource_policy()
    before = source_hashes()
    rust_version = command(["rustc", "--version", "--verbose"])
    if not rust_version.startswith("rustc 1.90.0 "):
        raise SystemExit("Select the project's Rust 1.90.0 toolchain before recording this build.")
    lock = tomllib.loads(Path("Cargo.lock").read_text())
    external = [p for p in lock["package"] if "source" in p]
    if external:
        raise SystemExit("This no-registry Phase 3a build contract does not permit external Cargo packages.")
    # Reject hidden code-generation changes instead of silently claiming the pinned profile.
    rejected = [key for key in os.environ if os.environ[key] and (
        key in ["RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS", "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER",
                "CARGO_BUILD_TARGET", "CARGO_TARGET_DIR", "RUSTC", "RUSTUP_TOOLCHAIN"]
        or key.startswith("CARGO_PROFILE_"))]
    if rejected:
        raise SystemExit("Unset build overrides before recording provenance: " + ", ".join(sorted(rejected)))
    env = {**os.environ, "LC_ALL": "C", "CARGO_NET_OFFLINE": "true"}
    argv = ["cargo", "build", "--release", "--locked", "--offline", "--verbose", "--jobs", "1"]
    result = subprocess.run(argv, cwd=ROOT, env=env, capture_output=True, text=True)
    log = Path("bench/counts-build.log")
    log.write_text(portable(result.stdout + result.stderr))
    if result.returncode:
        raise SystemExit(f"Release build failed; see {log}.")
    after = source_hashes()
    if before != after:
        raise SystemExit("Source changed during compilation; rerun after edits stop.")
    metadata = json.loads(command(["cargo", "metadata", "--offline", "--locked", "--no-deps", "--format-version", "1"], env=env))
    manifest = tomllib.loads(Path("Cargo.toml").read_text())
    reference = json.loads(Path("reference/build-vanilla.json").read_text())
    vanilla = Path("work/vanilla/psmc")
    expected = reference["executables"]["psmc"]["sha256"]
    if sha256(vanilla) != expected:
        raise SystemExit("Vanilla executable does not match the retained unmodified-reference record.")
    report = {
        "schema_version": 1, "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "resource_policy": policy, "status": "built", "source_commit_reference": reference["source_commit"],
        "implementation": "Rust dense scalar oracle and runtime-dispatched strict AVX/scalar CPU f64 backend, same system libm; deterministic bootstrap scheduler",
        "commands": [argv, ["rustc", "--version", "--verbose"], ["cargo", "--version", "--verbose"],
                     ["cargo", "metadata", "--offline", "--locked", "--no-deps", "--format-version", "1"]],
        "build_log": str(log), "build_log_sha256": sha256(log),
        "environment_contract": {"LC_ALL": "C", "CARGO_NET_OFFLINE": "true",
                                 "custom_rustflags": None, "profile_overrides": None},
        "rustc": rust_version, "cargo": command(["cargo", "--version", "--verbose"]),
        "release_profile": manifest["profile"]["release"],
        "cargo_lock_sha256": sha256(Path("Cargo.lock")),
        "cargo_packages": [{"name": p["name"], "version": p["version"], "source": p["source"]}
                           for p in metadata["packages"]],
        "external_registry_packages": 0, "network_dependency_resolution": "disabled (--offline --locked)",
        "source_sha256": before, "system": system_info(),
        "rust_binary": {"file": str(BINARY), "sha256": sha256(BINARY), **library_info(BINARY)},
        "reference_binary": {"file": str(vanilla), "sha256": expected,
                             "build_record": "reference/build-vanilla.json", **library_info(vanilla)},
        "validation": "Build success is not a compatibility or performance result; see separate reports.",
        "runner": {"file": "bench/counts_build.py", "sha256": sha256(Path("bench/counts_build.py"))},
    }
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": report["status"], "report": str(REPORT),
                      "rust_binary_sha256": report["rust_binary"]["sha256"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

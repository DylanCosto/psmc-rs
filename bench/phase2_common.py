"""Phase 2 evidence helpers. Inference binaries are frozen, never rebuilt here."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess

from common import ROOT, save, sha256


def utc_stamp():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def relative(path):
    return str(Path(path).resolve().relative_to(ROOT))


def clean_env():
    env = {k: v for k, v in os.environ.items() if not k.startswith("PSMC_")}
    env["LC_ALL"] = "C"
    return env


def source_hashes():
    paths = sorted(ROOT.glob("crates/**/*.rs"))
    paths += [ROOT / name for name in ("Cargo.toml", "Cargo.lock", "rust-toolchain.toml")]
    return {relative(path): sha256(path) for path in paths}


def freeze(directory, sources):
    """Retain one read-only executable snapshot and its original hash per label."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    binaries = {}
    for name, original in sources.items():
        original = (ROOT / original).resolve()
        before = sha256(original)
        destination = directory / name
        shutil.copy2(original, destination)
        destination.chmod(stat.S_IRUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
        if sha256(destination) != before or sha256(original) != before:
            raise RuntimeError(f"Executable changed while freezing {original}")
        binaries[name] = {"path": relative(destination), "sha256": before,
                          "copied_from": relative(original)}
    record = {"binaries": binaries, "source_sha256_at_freeze": source_hashes(),
              "created_utc": dt.datetime.now(dt.timezone.utc).isoformat()}
    save(directory / "manifest.json", record)
    return record


def verify_binaries(provenance):
    for name, record in provenance["binaries"].items():
        if sha256(ROOT / record["path"]) != record["sha256"]:
            raise RuntimeError(f"Frozen executable changed: {name}")


def wrapper(destination, binary, arguments):
    """The inherited harness hashes this wrapper; it additionally guards its binary."""
    destination = Path(destination)
    source = '''#!/usr/bin/env python3
import hashlib, os, pathlib, sys
root = pathlib.Path(__file__).resolve()
while not (root / "Cargo.toml").is_file():
    if root == root.parent:
        raise SystemExit("Cannot locate project root")
    root = root.parent
binary = root / BINARY
if hashlib.sha256(binary.read_bytes()).hexdigest() != EXPECTED_HASH:
    raise SystemExit("Frozen Phase 2 executable hash changed")
os.execv(str(binary), [str(binary), *ARGUMENTS, *sys.argv[1:]])
'''.replace("BINARY", repr(binary["path"])).replace("EXPECTED_HASH", repr(binary["sha256"])).replace("ARGUMENTS", repr(arguments))
    destination.write_text(source)
    destination.chmod(0o755)
    return {"path": relative(destination), "sha256": sha256(destination),
            "underlying_binary": binary, "prepended_arguments": arguments}


def invoke(command, log_base, timeout=None):
    log_base = Path(log_base)
    with log_base.with_suffix(".stdout").open("wb") as out, log_base.with_suffix(".stderr").open("wb") as err:
        completed = subprocess.run(command, cwd=ROOT, env=clean_env(), stdout=out, stderr=err, timeout=timeout)
    return {"command": [str(x) for x in command], "returncode": completed.returncode,
            "stdout": relative(log_base.with_suffix(".stdout")),
            "stderr": relative(log_base.with_suffix(".stderr"))}

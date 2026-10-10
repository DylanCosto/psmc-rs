#!/usr/bin/env python3
"""Tiny PHLASH feasibility run; never a legacy PSMC speed/equivalence benchmark."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import random
import resource
import subprocess
import sys
import time
import traceback
from urllib.parse import unquote, urlparse

PIN = "96a6e3f8e01053271e88d21c97862198422d9ae0"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--source-dir", type=Path, default=Path("work/phlash-upstream"))
    parser.add_argument("--require-gpu", action="store_true")
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.work_dir.mkdir(parents=True, exist_ok=True)
    settings = dict(
        window_size=100, hold_out=False, niter=2, num_particles=4,
        overlap=10, chunk_size=200, minibatch_size=2, num_workers=1,
        double_precision=True, progress=False,
    )
    result = dict(
        schema_version=1,
        comparator="PHLASH; different Bayesian inference method",
        source={"repository": "https://github.com/jthlab/phlash", "commit": PIN},
        status="started", scientific_inference_validated=False,
        legacy_output_equivalence_claim=False, bootstrap_equivalence_claim=False,
        speedup_claim=None,
        settings={**settings, "jax_random_seed": 1, "initial_pattern": "14*1+1*2",
                  "hidden_intervals": 16, "learning_rate": 0.1, "sigma": 1.0,
                  "alpha": 0.0, "beta": 0.0, "theta": "estimated from synthetic input",
                  "rho_over_theta_initial": 1.0, "t1": 0.0001, "tM": 15.0},
        runtime={"python": sys.version, "executable": sys.executable},
        command=sys.argv,
        real_workload={"status": "not_run", "reason": "No real sample, commands, masks, or input hashes supplied."},
    )
    start = time.perf_counter()
    try:
        gpu = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,driver_version,memory.total,compute_cap",
             "--format=csv,noheader"], capture_output=True, text=True, check=False,
        )
        result["hardware_gpu_inventory"] = gpu.stdout.strip() or gpu.stderr.strip()
    except FileNotFoundError:
        result["hardware_gpu_inventory"] = "nvidia-smi unavailable"
    try:
        # The fixture is generated without personal data and is not a demographic simulation.
        rng = random.Random(20261009)
        records = []
        for index in range(2):
            sequence = "".join(rng.choices("TKN", weights=[88, 10, 2], k=2000))
            records.append(f">synthetic_{index + 1}\n" + "\n".join(
                sequence[i:i + 60] for i in range(0, len(sequence), 60)) + "\n")
        fixture = args.work_dir / "phlash-smoke.psmcfa"
        fixture.write_text("".join(records))
        result["fixture"] = dict(
            kind="synthetic random PSMCFA; not biological simulation", records=2,
            bins_per_record=2000, total_bins=4000, represented_bp=400000,
            random_seed=20261009,
            sha256=hashlib.sha256(fixture.read_bytes()).hexdigest(),
            path=str(fixture),
        )
        import_start = time.perf_counter()
        import numpy as np
        import jax
        import phlash
        import phlash.mcmc as mcmc

        source_dir = args.source_dir.resolve()
        actual_commit = subprocess.check_output(
            ["git", "-C", str(source_dir), "rev-parse", "HEAD"], text=True,
        ).strip()
        if actual_commit != PIN:
            raise RuntimeError("Source checkout does not match required PHLASH pin")
        direct_url = json.loads(importlib.metadata.distribution("phlash").read_text("direct_url.json") or "{}")
        installed_from = Path(unquote(urlparse(direct_url.get("url", "")).path)).resolve()
        if installed_from != source_dir:
            raise RuntimeError("Installed PHLASH was not built from the pinned local checkout")
        checked = 0
        for path in (source_dir / "src/phlash").rglob("*.py"):
            relative = path.relative_to(source_dir / "src/phlash")
            if path.read_bytes() != (Path(phlash.__file__).parent / relative).read_bytes():
                raise RuntimeError("Installed PHLASH source differs: " + str(relative))
            checked += 1
        if subprocess.check_output(["git", "-C", str(source_dir), "diff", "HEAD", "--", "src/phlash"]):
            raise RuntimeError("Pinned PHLASH source has local modifications")
        result["source"].update(verified=True, installed_python_files_checked=checked)

        result["runtime"]["import_seconds"] = time.perf_counter() - import_start
        result["runtime"]["jax_devices"] = [str(d) for d in jax.devices()]
        result["runtime"]["jax_enable_x64"] = bool(jax.config.jax_enable_x64)
        result["runtime"]["packages"] = dict(sorted(
            (d.metadata["Name"], d.version) for d in importlib.metadata.distributions()
            if d.metadata["Name"]
        ))
        actual_kernels = []
        original_get_kernel = mcmc.get_kernel

        def recording_get_kernel(*a, **kw):
            kernel = original_get_kernel(*a, **kw)
            name = type(kernel).__module__ + "." + type(kernel).__name__
            actual_kernels.append(name)
            if args.require_gpu and not name.startswith("phlash.gpu."):
                raise RuntimeError("GPU required by probe, but PHLASH fell back to " + name)
            return kernel

        mcmc.get_kernel = recording_get_kernel
        callbacks = []

        def callback(models):
            # Materialize arrays to keep asynchronous work inside timed region.
            leaves = jax.tree.leaves(models)
            if not all(np.isfinite(np.asarray(x)).all() for x in leaves):
                raise RuntimeError("Nonfinite values in PHLASH callback")
            callbacks.append(1)

        settings["key"] = jax.random.PRNGKey(1)
        fit_start = time.perf_counter()
        models = phlash.psmc([str(fixture)], callback=callback, **settings)
        numeric = [{"theta": float(x.theta), "rho": float(x.rho),
                    "time_grid": np.asarray(x.eta.t).tolist(),
                    "coalescence_rates": np.asarray(x.eta.c).tolist()} for x in models]
        result["runtime"].update(
            fit_wall_seconds_including_preprocessing_and_jit=time.perf_counter() - fit_start,
            actual_kernels=actual_kernels, iterations_completed=len(callbacks),
            returned_models=len(models),
        )
        if len(models) != 4 or len(callbacks) != 2:
            raise RuntimeError("Unexpected model or iteration count")
        if not all(np.isfinite(np.asarray(x)).all() for model in models for x in jax.tree.leaves(model)):
            raise RuntimeError("Nonfinite output")
        result["posterior_smoke_output"] = numeric
        result["status"] = "passed_smoke_only"
        result["gpu_feasibility"] = dict(
            status="passed_smoke_only" if all(x.startswith("phlash.gpu.") for x in actual_kernels) else "not_run",
            reason=None if all(x.startswith("phlash.gpu.") for x in actual_kernels) else
            "Only isolated CPU dependencies were installed; CUDA Python and NVRTC/JAX GPU packages are absent. Physical GPU is present.",
        )
    except Exception as exc:
        result["status"] = "not_run" if isinstance(exc, (ImportError, ModuleNotFoundError)) else "failed"
        result["error"] = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
    finally:
        result["runtime"]["total_process_body_seconds"] = time.perf_counter() - start
        result["runtime"]["peak_main_process_rss_kib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        result["runtime"]["peak_child_process_rss_kib"] = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
        result["runtime"]["memory_note"] = "Linux ru_maxrss; separate process maxima, not summed simultaneous total; device memory not measured."
        args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"status": result["status"], "output": str(args.output)}))
    return 0 if result["status"] == "passed_smoke_only" else 1


if __name__ == "__main__":
    raise SystemExit(main())

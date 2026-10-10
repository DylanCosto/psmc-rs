"""Negative controls for provenance wrappers and parallel-process memory sampling."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
import unittest

from common import ROOT
from phase2_benchmark import ChildMemory, batch_exit_status, worker_comparison
from phase2_common import clean_env, freeze, verify_binaries, wrapper


class Phase2HarnessTests(unittest.TestCase):
    def test_wrapper_preserves_arguments_and_guards_actual_binary(self):
        with tempfile.TemporaryDirectory(prefix="phase2-harness-", dir=ROOT / "work") as directory:
            directory = Path(directory)
            source = directory / "source"
            source.write_text("#!/usr/bin/env python3\nimport json,sys\nprint(json.dumps(sys.argv[1:]))\n")
            source.chmod(0o755)
            provenance = freeze(directory / "frozen", {"test": str(source.relative_to(ROOT))})
            item = wrapper(directory / "wrapper", provenance["binaries"]["test"], ["--backend", "cpu", "space ; $(literal)"])
            run = subprocess.run([str(ROOT / item["path"]), "tail"], capture_output=True, env=clean_env())
            self.assertEqual(run.returncode, 0)
            self.assertEqual(json.loads(run.stdout), ["--backend", "cpu", "space ; $(literal)", "tail"])
            binary = ROOT / provenance["binaries"]["test"]["path"]
            binary.chmod(0o755)
            binary.write_text(binary.read_text() + "# changed\n")
            with self.assertRaisesRegex(RuntimeError, "Frozen executable changed"):
                verify_binaries(provenance)
            blocked = subprocess.run([str(ROOT / item["path"])], capture_output=True, env=clean_env())
            self.assertNotEqual(blocked.returncode, 0)
            self.assertIn(b"hash changed", blocked.stderr)
            self.assertEqual(blocked.stdout, b"")

    def test_batch_exit_status_rejects_signals_and_empty_batches(self):
        self.assertEqual(batch_exit_status([{"exit_code": -9}, {"exit_code": 0}]), -9)
        self.assertEqual(batch_exit_status([{"exit_code": 0}, {"exit_code": 2}]), 2)
        self.assertEqual(batch_exit_status([{"exit_code": 0}, {"exit_code": 0}]), 0)
        self.assertNotEqual(batch_exit_status([]), 0)

    def test_worker_budget_reduction_rejects_equal_worker_label(self):
        self.assertFalse(worker_comparison({"requested_workers": 4, "workers": 2}, 4, 30)["equal_worker_budget"])
        self.assertFalse(worker_comparison({"requested_workers": 3, "workers": 4}, 4, 30)["equal_worker_budget"])
        self.assertTrue(worker_comparison({"requested_workers": 4, "workers": 4}, 4, 30)["equal_worker_budget"])
        self.assertTrue(worker_comparison({"requested_workers": 40, "workers": 30}, 40, 30)["equal_worker_budget"])

    def test_empty_scope_from_conflicting_subset_flags_is_rejected(self):
        result = subprocess.run([sys.executable, str(ROOT / "bench/phase2_benchmark.py"), "--single-only", "--batch-only"],
                                cwd=ROOT, capture_output=True, env=clean_env())
        self.assertEqual(result.returncode, 2)
        self.assertIn(b"not allowed with argument", result.stderr)

    def test_memory_sampler_observes_children_started_by_worker_threads(self):
        def allocate():
            return subprocess.run([sys.executable, "-c", "import time; memory=bytearray(24*1024*1024); time.sleep(0.25)"], check=True)
        with ChildMemory() as memory:
            with ThreadPoolExecutor(max_workers=2) as pool:
                list(pool.map(lambda _: allocate(), range(2)))
        # Sampling cannot promise the true peak, but missing thread-owned children
        # entirely would invalidate the equal-worker memory comparison.
        self.assertGreater(memory.peak, 48 * 1024)
        self.assertGreater(memory.samples, 1)


if __name__ == "__main__":
    unittest.main()

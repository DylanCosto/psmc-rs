"""Negative controls for the Phase 1 comparator, independent of any PSMC run."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from phase1_differential import compare_output, compare_snapshots


class ComparatorControls(unittest.TestCase):
    def test_only_one_version_line_is_excluded(self):
        a = b"MM\tVersion: C\nMM\tC_pi: 1.25\nLK\t-9.0\n"
        b = b"MM\tVersion: Rust\nMM\tC_pi: 1.25\nLK\t-9.0\n"
        self.assertGreater(compare_output(a, b)["compared_bytes"], 0)
        with self.assertRaises(AssertionError):
            compare_output(a, b.replace(b"1.25", b"1.26"))
        with self.assertRaises(AssertionError):
            compare_output(a, b + b"MM\tVersion: second\n")
        with self.assertRaises(AssertionError):
            compare_output(a, b.replace(b"LK\t-9.0\n", b"LK\t-9.0"))

    def snapshots(self, change):
        events = [{"event": event, "model_id": index, "value": 0.125}
                  for index, event in enumerate(["model", "sequence", "aggregate", "objective", "em_end"])]
        candidate = copy.deepcopy(events)
        change(candidate)
        with tempfile.TemporaryDirectory() as directory:
            oracle, rust = Path(directory) / "C.jsonl", Path(directory) / "Rust.jsonl"
            oracle.write_text("".join(json.dumps(event) + "\n" for event in events))
            rust.write_text("".join(json.dumps(event) + "\n" for event in candidate))
            return compare_snapshots(oracle, rust)

    def test_exact_finite_difference_is_detected(self):
        self.assertEqual(self.snapshots(lambda events: None)["mismatches"], 0)
        self.assertEqual(self.snapshots(lambda events: events[0].update(value=0.12500000000000003))["mismatches"], 1)

    def test_missing_callback_and_id_change_are_detected(self):
        with self.assertRaises(AssertionError):
            self.snapshots(lambda events: events.pop(3))
        self.assertEqual(self.snapshots(lambda events: events[3].update(model_id=999))["mismatches"], 1)

    def test_nonfinite_class_changes_are_detected(self):
        self.assertEqual(self.snapshots(lambda events: events[0].update(value="nan"))["mismatches"], 1)
        self.assertEqual(self.snapshots(lambda events: events[0].update(value="-inf"))["mismatches"], 1)


if __name__ == "__main__":
    unittest.main()

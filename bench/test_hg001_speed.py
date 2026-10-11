import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import hg001_speed as speed


class SpeedTests(unittest.TestCase):
    def test_schedule_separates_phases_and_balances_single_core(self):
        jobs = speed.schedule()
        self.assertEqual(len(jobs), 20)
        self.assertTrue(all(c.endswith('-one') for _, c in jobs[:12]))
        self.assertTrue(all(c.endswith('-full') for _, c in jobs[12:]))
        for config in speed.CONFIGS:
            self.assertEqual(sum(c == config and p == 'warmup' for p, c in jobs), 1)
            self.assertEqual(sum(c == config and p != 'warmup' for p, c in jobs), 3)
        for position in range(3):
            self.assertEqual({jobs[3+r*3+position][1] for r in range(3)}, set(speed.CONFIGS[:3]))

    def test_command_affinity_and_budget(self):
        source, root = Path('/source'), Path('/results')
        for config in speed.CONFIGS:
            cmd = speed.command(source, root, 'test', config)
            self.assertEqual(cmd[2], '0' if config.endswith('-one') else '0-15')
            if config.startswith('strict'):
                self.assertEqual(cmd[cmd.index('--memory-mib')+1], '8192')
        result = subprocess.check_output(['/usr/bin/taskset', '-c', '0', sys.executable,
                   '-c', 'import os;print(sorted(os.sched_getaffinity(0)))'], text=True)
        self.assertEqual(json.loads(result), [0])

    def test_elapsed_and_summary_exclude_warmups(self):
        self.assertEqual(speed.wall_seconds('Elapsed (wall clock) time (h:mm:ss or m:ss): 1:02:03.45'), 3723.45)
        rows = []
        for phase, config in speed.schedule():
            rows.append({'phase': phase, 'config': config, 'wall_seconds': 999 if phase == 'warmup' else 10,
                         'timing': {'peak_rss_kib': 2048}, 'workers': 1})
        summary = speed.summarize(rows)
        self.assertEqual(summary['c-one']['median_seconds'], 10)
        self.assertEqual(summary['strict-full']['speedup_vs_same_mode_one'], 1)

    def test_dependency_fails_closed(self):
        with tempfile.TemporaryDirectory() as d, patch.object(speed, 'dependency_live', return_value=False):
            root = Path(d)
            with self.assertRaises(RuntimeError): speed.dependency_ready(root)
            (root/'stop.json').write_text('{}')
            with self.assertRaises(RuntimeError): speed.dependency_ready(root)
            (root/'stop.json').unlink()
            (root/'report.json').write_text('{}')
            audit = {'audit_passed': True, 'strict_c_exact': True,
                     'report_sha256': speed.base.sha(root/'report.json')}
            (root/'audit.json').write_text(json.dumps(audit))
            self.assertTrue(speed.dependency_ready(root))
            (root/'report.json').write_text('{"changed":true}')
            with self.assertRaises(AssertionError): speed.dependency_ready(root)

    def test_output_difference_is_rejected(self):
        with patch.object(speed.base.p, 'curve'):
            speed.verify_output('MM\tVersion: a\nLK\t1\n', 'MM\tVersion: b\nLK\t1\n')
            with self.assertRaises(AssertionError): speed.verify_output('LK\t2\n', 'LK\t1\n')


if __name__ == '__main__': unittest.main()

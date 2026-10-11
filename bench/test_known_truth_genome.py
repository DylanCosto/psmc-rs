import json
import resource
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import known_truth_genome as g


class GenomeHarnessTests(unittest.TestCase):
    def test_design_and_seeds(self):
        self.assertEqual(sum(g.LENGTHS), 3_000_000_000)
        self.assertEqual(len(g.LENGTHS), 24)
        self.assertEqual(max(g.LENGTHS), 250_000_000)
        values = [tuple(g.seeds(h,i,k)) for h in g.HISTORIES for i in range(10) for k in range(24)]
        self.assertEqual(len(set(values)), 720)
        self.assertTrue(all(0 < x < 65536 for v in values for x in v))

    def test_conversion_preserves_one_continuous_record(self):
        raw = 'ms 2 1\n\n//\nsegsites: 3\npositions: 0.0 0.5 0.999999999999\n000\n111\n'
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'chr.psmcfa'
            p.write_text(g.p.convert_ms(raw,length=1000,bin_size=100,expected=1))
            self.assertEqual(g.validate_input(p,[1000]),[10])
            p.write_text(p.read_text()+p.read_text())
            with self.assertRaises(AssertionError):g.validate_input(p,[1000])

    def test_compression_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'ms.out';p.write_bytes(b'genomic fixture\n'*1000)
            digest = g.sha(p);result = g.compress_verified(p)
            self.assertFalse(p.exists())
            self.assertEqual(result['original_sha256'],digest)
            self.assertEqual(g.compressed_sha(str(p)+'.gz'),digest)

    def test_real_child_limits_resume_and_tamper(self):
        # Exercise real child limits and resume integrity independently of the
        # CI host's free space. This tiny child does not run a genome workload.
        with tempfile.TemporaryDirectory() as d, \
                patch.object(g, 'available', return_value=16*g.GIB), \
                patch.object(g.shutil, 'disk_usage', return_value=SimpleNamespace(free=40*g.GIB)):
            runner = g.Runner(Path(d))
            try:
                base = Path(d)/'limit-check'
                cmd = [sys.executable,'-c','import resource,os,json; print(json.dumps([resource.getrlimit(resource.RLIMIT_AS),resource.getrlimit(resource.RLIMIT_FSIZE),os.nice(0)]))']
                first = runner.stage(base,cmd)
                limits = json.loads(Path(str(base)+'.out').read_text())
                self.assertEqual(limits[0],[6*g.GIB]*2)
                self.assertEqual(limits[1],[2*g.GIB]*2)
                self.assertGreaterEqual(limits[2],10)
                self.assertEqual(runner.stage(base,cmd),first)
                self.assertEqual(len(list(Path(d).glob('*.attempt-*.json'))),1)
                Path(str(base)+'.out').write_text('corrupt')
                with self.assertRaises(AssertionError):runner.stage(base,cmd)
            finally:runner.close()

    def test_resource_floor_fails_closed(self):
        for ram, free, panel in [(3,40,0), (16,24,0), (16,40,13)]:
            with self.subTest(ram=ram, free=free, panel=panel), \
                    tempfile.TemporaryDirectory() as d, \
                    patch.object(g, 'available', return_value=ram*g.GIB), \
                    patch.object(g.shutil, 'disk_usage', return_value=SimpleNamespace(free=free*g.GIB)), \
                    patch.object(g, 'disk_bytes', return_value=panel*g.GIB):
                runner = g.Runner(Path(d))
                try:
                    self.assertTrue(runner.stop.wait(5))
                    with self.assertRaises(RuntimeError):
                        runner.stage(Path(d)/'never-launched',['/usr/bin/true'])
                    self.assertFalse(list(Path(d).glob('*.attempt-*.json')))
                    self.assertIn('resource floor',runner.reason)
                finally:runner.close()


if __name__=='__main__':unittest.main()

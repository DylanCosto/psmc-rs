import gzip,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import hg001_genome_prepare as prep
import hg001_genome_run as run

class HG001GenomeTests(unittest.TestCase):
    def test_streamed_conversion_masks_and_partial_bin(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            result=prep.convert_chromosome(root,'chr1',11023,[(0,11000)],
                [(0,'A',['C'],'PASS','0/1'),(10001,'AC',['A'],'PASS','0/1'),
                 (10002,'A',['G'],'PASS','0/1'),(11022,'A',['C'],'PASS','0/1')],
                prep.ROOT/'work/vanilla/utils/fq2psmcfa')
            self.assertTrue(result['independent_binning_exact'])
            self.assertEqual(result['variants']['called_het_bases'],1)
            self.assertEqual(result['bins'],111)
            sequence=prep.read_fasta(root/'chromosomes/chr1.psmcfa')[0][1]
            self.assertEqual(sequence[0],'K');self.assertEqual(sequence[-1],'T')
            with gzip.open(root/'chromosomes/chr1.states.fa.gz','rt') as f:states=''.join(f.read().splitlines()[1:])
            self.assertEqual(states[10002],'N');self.assertEqual(states[11022],'N')

    def test_stage_limits_and_reuse(self):
        with tempfile.TemporaryDirectory() as d:
            r=run.Run(Path(d))
            try:
                command=[sys.executable,'-c','import resource,json;print(json.dumps([resource.getrlimit(resource.RLIMIT_AS),resource.getrlimit(resource.RLIMIT_FSIZE)]))']
                a=r.stage('tiny',command,ceiling=3,min_ram=1)
                limits=json.loads((Path(d)/'tiny.out').read_text())
                self.assertEqual(limits,[[3*run.GIB]*2,[512*1024**2]*2])
                self.assertEqual(r.stage('tiny',command,ceiling=3,min_ram=1),a)
            finally:r.close()

    def test_monitor_stops_on_low_memory(self):
        with tempfile.TemporaryDirectory() as d,patch.object(run,'available',return_value=3*run.GIB):
            r=run.Run(Path(d))
            try:self.assertTrue(r.stop.wait(5));self.assertIn('resource floor',r.reason)
            finally:r.close()

if __name__=='__main__':unittest.main()

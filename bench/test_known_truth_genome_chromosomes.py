import unittest
from audit_genome_chromosomes import verify_payload


class IndependentEncodingAudit(unittest.TestCase):
    command=['ms','2','1','-seeds','1','2','3']
    prefix='ms 2 1 -seeds 1 2 3\n1 2 3\n\n//\n'

    def test_bin_edges_and_end_clamping(self):
        raw=self.prefix+'segsites: 4\npositions: 0 0.099999999999 0.1 1\n0000\n1111\n'
        result=verify_payload(raw,'>chr-1\nKKTTTTTTTK\n',1000,0,self.command)
        self.assertEqual(result['heterozygous_bins'],3)
        with self.assertRaises(AssertionError):verify_payload(raw,'>chr-1\nKTTTTTTTTK\n',1000,0,self.command)

    def test_zero_sites_and_boundary_rejection(self):
        raw=self.prefix+'segsites: 0\n'
        verify_payload(raw,'>chr-2\nTTTTTTTTTT\n',1000,1,self.command)
        with self.assertRaises(AssertionError):verify_payload(raw,'>chr-1\nTTTTT\n>chr-2\nTTTTT\n',1000,0,self.command)
        with self.assertRaises(AssertionError):verify_payload(raw+'\n//\nsegsites: 0\n','>chr-1\nTTTTTTTTTT\n',1000,0,self.command)

    def test_seed_echo(self):
        raw=self.prefix.replace('1 2 3\n\n','1 2 4\n\n')+'segsites: 0\n'
        with self.assertRaises(AssertionError):verify_payload(raw,'>chr-1\nTTTTTTTTTT\n',1000,0,self.command)


if __name__=='__main__':unittest.main()

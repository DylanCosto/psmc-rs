import unittest
from known_truth import convert_ms, curve, GRID, MU, BIN
import math

class KnownTruthTests(unittest.TestCase):
    def test_exact_bin_boundaries_and_two_haplotypes(self):
        text='ms header\n//\nsegsites: 5\npositions: 0 .099999999999 .1 .5 1\n00001\n11101\n'
        self.assertEqual(convert_ms(text,1000,100,1),'>ms-1\nKKTTTTTTTT\n')
    def test_empty_replicate_and_length(self):
        self.assertEqual(convert_ms('header\n//\nsegsites: 0\n',101,100,1),'>ms-1\nTT\n')
    def test_rejects_truncated_records(self):
        for text in ['header','header\n//\nsegsites: 1\npositions: .1\n0\n']:
            with self.assertRaises(ValueError): convert_ms(text,1000,100,1)
    def test_absolute_scaling_and_group_grid(self):
        text=''.join(f'RD\t{i}\n' for i in range(31))+'PA\t2+2 0.1 0.02 15 1 2\n'
        values,p=curve(text)
        self.assertAlmostEqual(p['n0'],10000)
        self.assertAlmostEqual(values[0],math.log(10000))
        self.assertAlmostEqual(values[-1],math.log(20000))
        self.assertAlmostEqual(p['group_starts_generations'][1],.1*math.expm1(math.log(151)*2/3)*20000)

if __name__=='__main__': unittest.main()

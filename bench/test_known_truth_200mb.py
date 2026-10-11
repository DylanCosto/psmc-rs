import unittest,math
from known_truth_200mb import grid,at,curve_metrics,event_ratio,HISTORIES

class Bands(unittest.TestCase):
 def test_edges_are_not_counted_twice(self):
  a=grid(1000,5000);b=grid(5000,20000)
  self.assertEqual(len(a),128);self.assertEqual(a[0],1000);self.assertLess(a[-1],5000);self.assertEqual(b[0],5000)
 def test_truth_curves_have_zero_error_and_expected_events(self):
  for name,h in HISTORIES.items():
   params={'n0':10000,'group_starts_generations':[t for t,n in h],'lambdas':[n/10000 for t,n in h]}
   result=curve_metrics({m:params for m in ['c','strict','equivalent']},h,5000,80000)
   self.assertEqual(result['rmse']['strict'],0);self.assertEqual(result['mode_curve_rmse'],0)
   ratio=event_ratio(params,name)
   if name=='bottleneck':self.assertAlmostEqual(ratio,.2)
   elif name=='expansion':self.assertAlmostEqual(ratio,2)
   else:self.assertIsNone(ratio)
if __name__=='__main__':unittest.main()

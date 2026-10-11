"""Numerical invariants for the diagnostic oracle, not production inference."""
import unittest
from pilot_decimal_model import model

class DecimalModelTests(unittest.TestCase):
    def test_precision_and_probability_invariants(self):
        for groups, params in [([0,0,1,1,2,2],[.02,.004,15.,1.,2.,.5]),
                               ([0]*4+[i for i in range(1,26) for _ in range(2)]+[26]*4+[27]*6,
                                [.045,.0064,22.]+[1e7,2e6,3e6]+[1.]*25)]:
            a=model(params,groups,50);b=model(params,groups,80)
            self.assertEqual(a,b)
            n=len(groups)
            self.assertAlmostEqual(sum(a[:n]),1.,places=13)
            for k in range(n):
                self.assertAlmostEqual(sum(a[n+k*n:n+(k+1)*n]),1.,places=13)
                self.assertAlmostEqual(a[n+n*n+k]+a[n+n*n+n+k],1.,places=15)
                self.assertAlmostEqual(sum(a[j]*a[n+j*n+k] for j in range(n)),a[k],places=13)

if __name__=='__main__':unittest.main()

import importlib.util,json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import adoption_qualification as q

class QualificationTests(unittest.TestCase):
    def test_exact_screen_and_failed_compiler_control(self):
        params=dict(theta=.02,rho=.004,n0=2000,max_t=15,group_starts_generations=[0,10000],lambdas=[1,2])
        a=dict(params=params,curves=q.logs(params),legacy_lk=-100,bins=10000,finite_trajectory=True)
        self.assertTrue(q.compare(a,a)['exploratory_screen'])
        b={**a,'params':{**params,'theta':.04}}
        self.assertFalse(q.compare(a,b)['exploratory_screen'])
    def test_resource_preflight_stops_before_spawn(self):
        with tempfile.TemporaryDirectory() as d,patch.object(q,'OUT',Path(d)),patch.object(q,'available',return_value=3*q.GIB):
            with self.assertRaises(AssertionError):q.stage('test',['/bin/true'])
            self.assertEqual(list(Path(d).iterdir()),[])
    def test_real_child_limits_and_success_evidence(self):
        with tempfile.TemporaryDirectory() as d,patch.object(q,'OUT',Path(d)),patch.object(q,'available',return_value=20*q.GIB):
            command=[sys.executable,'-c','import resource,os; print(resource.getrlimit(resource.RLIMIT_AS)); print(resource.getrlimit(resource.RLIMIT_FSIZE)); print(os.nice(0)); print(os.environ["MALLOC_ARENA_MAX"])']
            result=q.stage('probe',command)
            lines=(Path(d)/'probe.out').read_text().splitlines()
            self.assertEqual(lines[0],str((12*q.GIB,12*q.GIB)))
            self.assertEqual(lines[1],str((512*1024**2,512*1024**2)))
            self.assertGreaterEqual(int(lines[2]),10);self.assertEqual(lines[3],'2')
            self.assertEqual(result['exit_code'],0);self.assertTrue((Path(d)/'probe.done.json').exists())

if __name__=='__main__':unittest.main()

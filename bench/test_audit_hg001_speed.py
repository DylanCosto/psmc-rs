import unittest
import audit_hg001_speed as audit


class AuditTests(unittest.TestCase):
    def test_elapsed_parser_and_failed_exit(self):
        text = '''Command being timed: "taskset -c 0 psmc input"
User time (seconds): 3600.1
System time (seconds): 1.2
Elapsed (wall clock) time (h:mm:ss or m:ss): 1:02:03.45
Maximum resident set size (kbytes): 1024
Swaps: 0
Exit status: 0
'''
        wall, timing, swaps, cmd = audit.parse_time(text)
        self.assertEqual(wall, 3723.45)
        self.assertEqual(timing['peak_rss_kib'], 1024)
        self.assertEqual(swaps, 0)
        self.assertEqual(cmd, 'taskset -c 0 psmc input')
        with self.assertRaises(AssertionError):
            audit.parse_time(text.replace('Exit status: 0', 'Exit status: 1'))

    def test_fit_rejects_missing_round_nonfinite_and_bad_q(self):
        text = ''.join(f'RD\t{i}\n' for i in range(31))+'PA\t1+1 0.1 0.2 15 1 1\nQU\t0 -> 1\nLK\t-1\n'
        audit.check_fit(text)
        for altered in [text.replace('RD\t30\n', ''), text.replace('LK\t-1', 'LK\tnan'),
                        text.replace('0 -> 1', '0 x 1'), text.replace('0.1 0.2', '-0.1 0.2')]:
            with self.assertRaises(AssertionError): audit.check_fit(altered)


if __name__ == '__main__': unittest.main()

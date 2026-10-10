"""Complete the predeclared 128-record occupancy control without rebuilding."""
import json
import os
import statistics
import subprocess
from common import ROOT, save, sha256
from phase2_common import clean_env

os.chdir(ROOT)
binary = 'work/exhaust/cpu/baseline/target/release/examples/exhaust_resident_cpu'
previous = json.load(open('bench/exhaust-resident-cpu.json'))
assert sha256(binary) == previous['binary_sha256']
report = dict(status='running', binary=binary, binary_sha256=sha256(binary),
              runner_sha256=sha256(__file__), scope=previous['scope'], runs=[])
for workers in [10, 16]:
    for repeat in range(4):
        command = [binary, '128', str(workers)]
        result = subprocess.run(command, env=clean_env(), capture_output=True,
                                text=True, check=True, timeout=120)
        row = json.loads(result.stdout)
        row.update(command=command, repeat=repeat)
        report['runs'].append(row)
        save('bench/exhaust-resident128-cpu.json', report)
report['medians'] = [dict(jobs=128, workers=w, seconds=statistics.median(
    row['seconds'] for row in report['runs'] if row['workers'] == w and row['repeat'] > 0))
    for w in [10, 16]]
report['status'] = 'measured'
save('bench/exhaust-resident128-cpu.json', report)
print(report['medians'], flush=True)

"""Install only the frozen, accepted artifacts; retain previous executables."""
import json
import os
import shutil
from pathlib import Path
from common import ROOT, save, sha256

os.chdir(ROOT)
audit = json.load(open('bench/exhaust-audit.json'))
assert audit['status'] == 'passed'
for path, entry in audit['reports'].items():
    assert sha256(path) == entry['sha256'], path
for group in ['source_sha256', 'configuration_sha256']:
    for path, digest in audit[group].items():
        assert sha256(path) == digest, path
cpu_old = 'f0c3282e87e3eed0cc31c63a438429c19ad47cedec4c56c1150cc8520838e305'
cuda_old = '60c1499386096d7c5412c822ab8cf635af716ffc1399804f7dc3bb05b893f15c'
assert sha256('bin/psmc-rs') == sha256('bin/psmc-rs-v0.3.3') == cpu_old
assert sha256('bin/psmc-rs-cuda') == cuda_old
assert not Path('bin/psmc-rs-v0.4.1').exists()
assert not Path('bin/psmc-rs-cuda-v0.4.0').exists()
shutil.copy2('bin/psmc-rs-cuda', 'bin/psmc-rs-cuda-v0.4.0')
for backend, destinations in [('cpu', ['bin/psmc-rs-v0.4.1', 'bin/psmc-rs']),
                              ('cuda', ['bin/psmc-rs-cuda'])]:
    entry = audit['binaries'][backend]
    assert sha256(entry['path']) == entry['sha256']
    for destination in destinations:
        temporary = Path(destination + '.new')
        assert not temporary.exists()
        shutil.copy2(entry['path'], temporary)
        assert sha256(temporary) == entry['sha256']
        temporary.replace(destination)
paths = ['bin/psmc-rs', 'bin/psmc-rs-v0.4.1', 'bin/psmc-rs-v0.3.3',
         'bin/psmc-rs-cuda', 'bin/psmc-rs-cuda-v0.4.0']
result = dict(status='installed', runner_sha256=sha256(__file__),
              audit_sha256=sha256('bench/exhaust-audit.json'),
              files={p: sha256(p) for p in paths},
              recommendation='Use --backend cpu. Optional CUDA remains experimental; no GPU speed promotion.')
save('bench/exhaust-install.json', result)
print(json.dumps(result), flush=True)

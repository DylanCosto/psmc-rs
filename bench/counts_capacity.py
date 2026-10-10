#!/usr/bin/env python3
"""Record Vec capacity for HG block lengths; does not measure resident memory."""
import json
import os
from pathlib import Path
import subprocess
from common import ROOT, save, sha256


def main():
    os.chdir(ROOT)
    source='bench/counts_capacity.rs';binary='work/counts-campaign/capacity-probe'
    commands=[['rustc','--edition=2024','-O',source,'-o',binary],[binary]]
    subprocess.run(commands[0],check=True)
    rows=json.loads(subprocess.check_output(commands[1],text=True))
    assert len(rows)==3 and rows[1]['new_capacity_cells']<rows[1]['old_capacity_cells']
    assert rows[1]['new_capacity_cells']==rows[2]['new_capacity_cells']
    save('bench/counts-capacity.json',dict(status='passed',commands=commands,rustc=subprocess.check_output(['rustc','--version','--verbose'],text=True),runner_sha256=sha256(__file__),source_sha256=sha256(source),binary_sha256=sha256(binary),rows=rows,scope='One standard Vec<f64> replaying old/new message allocation at HG K64 block lengths; capacity only, not live-workspace instrumentation, RSS, timing or allocator physical reservation.'))

if __name__=='__main__':main()

#!/usr/bin/env python3
"""Run each complete campaign acceptance stage sequentially, never concurrently."""
import os
from pathlib import Path
import subprocess
from common import ROOT, save, sha256
from phase3_common import resource_policy


def main():
    os.chdir(ROOT);policy=resource_policy()
    steps=[]
    for command in [
        ['python3','bench/cpu_campaign_build.py'],
        ['python3','bench/cpu_campaign_cargo.py'],
        ['python3','bench/phase3_validate.py','--run','--report','bench/cpu-campaign-validation.json'],
        ['python3','bench/cpu_campaign_extended_gate.py'],
        ['python3','bench/phase3_scheduler.py','--run','--validation','bench/cpu-campaign-validation.json','--report','bench/cpu-campaign-scheduler.json'],
        ['python3','bench/cpu_campaign_review.py'],
        ['python3','bench/cpu_campaign_benchmark.py','--run'],
        ['python3','bench/cpu_campaign_final_profile.py'],
    ]:
        print('START '+command[1],flush=True)
        result=subprocess.run(command)
        steps.append(dict(command=command,returncode=result.returncode))
        save('bench/cpu-campaign-gate-run.json',dict(status='running',resource_policy=policy,steps=steps,runner_sha256=sha256(__file__)))
        assert result.returncode==0,command
    save('bench/cpu-campaign-gate-run.json',dict(status='passed',resource_policy=policy,steps=steps,runner_sha256=sha256(__file__)))


if __name__=='__main__':main()

#!/usr/bin/env python3
"""Final sequential checks and assembly audit for the campaign candidate."""
import json
import os
from pathlib import Path
import re
import subprocess
from common import ROOT,save,sha256
from phase2_common import clean_env,source_hashes
from phase3_common import resource_policy


def main():
    os.chdir(ROOT);policy=resource_policy();before=source_hashes()
    env=clean_env();env.update(CARGO_BUILD_JOBS='1',RUST_TEST_THREADS='1',CARGO_NET_OFFLINE='true')
    steps=[]
    commands=[['cargo','fmt','--all','--','--check'],
        ['cargo','test','--locked','--offline','--workspace','--jobs','1','--','--test-threads=1'],
        ['cargo','test','--locked','--offline','--workspace','--jobs','1','--release','--','--test-threads=1'],
        ['cargo','clippy','--locked','--offline','--workspace','--all-targets','--jobs','1','--','-W','clippy::almost_swapped'],
        ['cargo','build','--release','--locked','--offline','--jobs','1','--examples']]
    for command in commands:
        result=subprocess.run(command,env=env,capture_output=True,text=True)
        steps.append(dict(command=command,returncode=result.returncode,output=(result.stdout+result.stderr).replace(str(ROOT),'${PROJECT}')))
        save('bench/cpu-campaign-cargo.json',dict(status='running',resource_policy=policy,source_sha256=before,steps=steps))
        assert result.returncode==0,steps[-1]
    assert source_hashes()==before
    save('bench/cpu-campaign-cargo.json',dict(status='passed',lint_policy='Advisory existing style warnings retained; almost_swapped on the unchanged scalar optimizer is a warning. No oracle rewrites for lints.',resource_policy=policy,source_sha256=before,steps=steps,runner_sha256=sha256(__file__)))
    binary='target/release/psmc-rs'
    dis=subprocess.run(['objdump','-d','-C',binary],capture_output=True,text=True,check=True).stdout
    ops=re.findall(r'\t([a-z][a-z0-9]+)\s',dis)
    fma=sum(o.startswith(('vfm','vfnm')) for o in ops)
    horizontal=sum(o.startswith(('vhadd','vhsub','hadd','hsub')) for o in ops)
    packed=sum(o in ['vaddpd','vmulpd','vdivpd'] for o in ops)
    assert fma==horizontal==0 and packed>0
    save('bench/cpu-campaign-assembly.json',dict(status='passed',binary_sha256=sha256(binary),command=['objdump','-d','-C',binary],fma_ops=fma,horizontal_ops=horizontal,packed_avx_ops=packed,scope='Whole executable instruction inventory; isolated exact tests validate lane and operand order.',runner_sha256=sha256(__file__)))
    print(json.dumps(dict(status='passed',unit_tests=[sum(map(int,re.findall(r'test result: ok\. (\d+) passed;',s['output']))) for s in steps if s['command'][1]=='test'],fma=fma,horizontal=horizontal,packed_avx=packed)),flush=True)


if __name__=='__main__':main()

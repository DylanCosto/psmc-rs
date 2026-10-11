#!/usr/bin/env python3
"""Read live process state and compact qualification progress without modifying it."""
import argparse
from collections import deque
import json
import shlex
from pathlib import Path
import time


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--panel',required=True,type=Path)
    a=parser.parse_args();root=a.panel.resolve()
    pid=int((root/'run.lock').read_text())
    proc=Path('/proc')/str(pid)
    try:
        command=(proc/'cmdline').read_bytes().replace(b'\0',b' ').decode()
        parts=shlex.split(command)
        output=Path(parts[parts.index('--output')+1])
        if not output.is_absolute():output=(proc/'cwd').resolve()/output
        live='known_truth_genome.py' in command and output.resolve()==root
    except (OSError, ValueError, IndexError):command=None;live=False
    with (root/'resources.jsonl').open() as f:
        last=json.loads(deque(f,maxlen=1)[0])
    jobs=[]
    for group,stage in last['jobs'].items():
        members=[]
        for path in Path('/proc').iterdir():
            if not path.name.isdigit():continue
            try:
                fields=(path/'stat').read_text().rsplit(')',1)[1].split()
                if fields[2]==group:
                    members.append({'pid':int(path.name),'state':fields[0],
                        'command':(path/'cmdline').read_bytes().replace(b'\0',b' ').decode()})
            except (OSError,IndexError):pass
        jobs.append({'stage':stage,'live_members':members})
    fits={mode:len(list(root.glob(f'*/{mode}.done.json'))) for mode in ['c','strict','equivalent']}
    results=[json.loads(p.read_text()) for p in root.glob('*/result.json')]
    report={'harness_pid':pid,'harness_live':live,'command':command,
        'resource_sample_age_seconds':time.time()-last['time'],'live_jobs':jobs,
        'converted_chromosomes':len(list(root.glob('*/chr-*.converted.json'))),
        'planned_chromosomes':720,'finished_primary_fits':fits,
        'completed_datasets':sum(r['status']=='complete' for r in results),
        'planned_datasets':30,'report_exists':(root/'report.json').exists(),
        'resource_stop_exists':(root/'resource-stop.json').exists(),
        'incomplete_attempts':len(list(root.glob('*/incomplete-*.json'))),
        'latest_resources':last}
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()

#!/usr/bin/env python3
"""Inventory reachable Git history before publication; never print matched secrets.
This is a narrow scanner plus a review inventory, not a guarantee of secret absence.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--allow-author-metadata', action='store_true',
                        help='Use only after the owner explicitly accepts publishing existing author/committer addresses')
    args = parser.parse_args()
    head = git('rev-parse', 'HEAD').decode().strip()
    objects = {}
    for line in git('rev-list', '--objects', '--all').decode().splitlines():
        oid, _, name = line.partition(' ')
        objects[oid] = name
    patterns = {
        'github_token': rb'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b',
        'aws_access_key': rb'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b',
        'private_key': rb'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----',
    }
    input_suffixes = ('.psmcfa', '.psmcfa.gz', '.fq', '.fastq', '.fq.gz', '.fastq.gz',
                      '.fa', '.fasta', '.fa.gz', '.fasta.gz', '.vcf', '.vcf.gz', '.bcf',
                      '.bed', '.bed.gz', '.bam', '.cram', '.sam', '.ms')
    findings, home_paths, inputs = [], set(), []
    count = total = 0
    with subprocess.Popen(['git', 'cat-file', '--batch'], cwd=ROOT,
                          stdin=subprocess.PIPE, stdout=subprocess.PIPE) as reader:
        for oid, name in objects.items():
            reader.stdin.write((oid+'\n').encode()); reader.stdin.flush()
            header = reader.stdout.readline().decode().split()
            size = int(header[2]); data = reader.stdout.read(size)
            assert reader.stdout.read(1) == b'\n'
            # Commit/tag messages can expose credentials too; do not print matches.
            for kind, pattern in patterns.items():
                if re.search(pattern, data): findings.append(dict(path=name, object=oid, kind=kind))
            if header[1] != 'blob': continue
            count += 1; total += size
            if re.search(rb'/home/[A-Za-z0-9_.-]+/', data): home_paths.add(name)
            if name.lower().endswith(input_suffixes):
                inputs.append(dict(path=name, object=oid, bytes=size, sha256=hashlib.sha256(data).hexdigest()))
        reader.stdin.close()
        assert reader.wait() == 0
    identities = set(git('log', '--all', '--format=%ae%n%ce').decode().splitlines())
    tag_identities = {line.strip('<>') for line in git('for-each-ref', 'refs/tags', '--format=%(taggeremail)').decode().splitlines() if line}
    identities.update(tag_identities)
    personal_identities = {email for email in identities if email and not email.lower().endswith(('@localhost', '@users.noreply.github.com'))}
    tracked = git('ls-files', '-z').decode().split('\0')[:-1]
    private_trees = [p for p in tracked if p.startswith(('work/', 'bin/', 'target/'))]
    outside = [item for item in inputs if not item['path'].startswith('tests/fixtures/')]
    result = dict(head=head, scope='Reachable Git objects and tracked path inventory; known credential patterns only, commit/tag identity exposure; manual review still required',
                  blob_count=count, blob_bytes=total,
                  tracked_files=len(tracked), tracked_bytes=sum((ROOT/p).stat().st_size for p in tracked),
                  credential_like_findings=findings, tracked_private_work_trees=private_trees,
                  absolute_home_path_files=sorted(home_paths),
                  historical_input_like_objects=len(inputs), input_objects_outside_fixture_tree=outside,
                  synthetic_fixture_inventory=inputs,
                  fixture_provenance=['bench/prepare.py', 'bench/phlash_probe.py', 'tests/fixtures/golden/README.md',
                                      'bench/cpu_campaign_fixtures.py', 'bench/cpu-campaign-fixtures.json',
                                      'bench/cpu_campaign_hmm_fixtures.py', 'bench/cpu-campaign-hmm-fixtures.json'],
                  non_noreply_commit_or_tag_identity_count=len(personal_identities),
                  author_metadata_publication_accepted=args.allow_author_metadata,
                  automated_blockers=bool(findings or private_trees or outside or (personal_identities and not args.allow_author_metadata)),
                  manual_review='Required for fixture provenance and historical build/test path context before making repository public')
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ['synthetic_fixture_inventory','fixture_provenance']}, indent=2))
    if result['automated_blockers']: raise SystemExit(1)


if __name__ == '__main__':
    main()

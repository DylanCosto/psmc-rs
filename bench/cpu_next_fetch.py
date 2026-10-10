#!/usr/bin/env python3
"""Fetch only the pinned single-individual public GIAB fixture, never a cohort."""
import hashlib,os,urllib.request
from pathlib import Path
from common import ROOT,sha256
FILES = [{'url': 'https://ftp-trace.ncbi.nlm.nih.gov/ReferenceSamples/giab/release/AshkenazimTrio/HG002_NA24385_son/NISTv4.2.1/GRCh38/HG002_GRCh38_1_22_v4.2.1_benchmark.vcf.gz', 'path': 'work/cpu-next/hg002/benchmark.vcf.gz', 'sha256': 'adb4d4a50048aa13353a06b84fcfcbca09a5d17525efaa4cea44f8822e81175c'}, {'url': 'https://ftp-trace.ncbi.nlm.nih.gov/ReferenceSamples/giab/release/AshkenazimTrio/HG002_NA24385_son/NISTv4.2.1/GRCh38/HG002_GRCh38_1_22_v4.2.1_benchmark_noinconsistent.bed', 'path': 'work/cpu-next/hg002/callable.bed', 'sha256': 'fba9a57c36ec88e5d14ea3e259c8866c7935f4998d3ec0fa2d6c3962da5b5575'}, {'url': 'https://ftp-trace.ncbi.nlm.nih.gov/ReferenceSamples/giab/release/AshkenazimTrio/HG002_NA24385_son/NISTv4.2.1/README_v4.2.1.txt', 'path': 'work/cpu-next/README_v4.2.1.txt', 'sha256': '70e7d8cd54119c40e1be946574ce1b91db835af594809466bcf7d3727eaa9699'}]

def main():
    os.chdir(ROOT)
    for entry in FILES:
        path=Path(entry['path']);path.parent.mkdir(parents=True,exist_ok=True)
        if not path.exists():
            temporary=path.with_suffix(path.suffix+'.download')
            try:
                total=0
                with urllib.request.urlopen(entry['url'],timeout=60) as response,temporary.open('wb') as out:
                    while chunk:=response.read(1024*1024):
                        total+=len(chunk)
                        if total>200*1024*1024:raise RuntimeError('Unexpected file size; bounded public-fixture download stopped')
                        out.write(chunk)
                assert sha256(temporary)==entry['sha256'],entry['path']
                temporary.rename(path)
            finally:
                temporary.unlink(missing_ok=True)
        assert sha256(path)==entry['sha256'],entry['path']
        print('Verified '+entry['path'])
if __name__=='__main__':main()

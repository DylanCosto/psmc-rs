#!/usr/bin/env python3
"""Bounded RSS regression on eight distinct million-bin records; no unsafe full-pool run."""
import argparse,hashlib,json,subprocess,random
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 fixture=out/'eight-million-bins.psmcfa'
 with fixture.open('w') as f:
  for i in range(8):
   rng=random.Random(1400+i)
   seq=''.join('K' if rng.randrange(50)==0 else 'T' for _ in range(1_000_000))
   f.write(f'>distinct-{i}\n');f.write('\n'.join(seq[j:j+60] for j in range(0,len(seq),60))+'\n')
 args=['-p','4+25*2+4+6','-N','2','-t','15','-r','5','-I','0','--seed','42']
 runs=[];reference=None
 for name,binary,extra in [('previous_serial',ROOT/'bin/psmc-rs-v0.6.2',['--record-workers','1']),('bounded_serial',ROOT/'target/release/psmc-rs',['--record-workers','16','--memory-mib','2048']),('bounded_two',ROOT/'target/release/psmc-rs',['--record-workers','16','--memory-mib','3500'])]:
  command=[str(binary),*args,*extra,'--stats',str(out/f'{name}.stats.json'),str(fixture)]
  with (out/f'{name}.psmc').open('w') as stdout,(out/f'{name}.stderr').open('w') as stderr:
   subprocess.run(['/usr/bin/time','-f','%e %U %S %M','-o',str(out/f'{name}.time'),*command],stdout=stdout,stderr=stderr,check=True,timeout=600)
  text=''.join(l for l in (out/f'{name}.psmc').read_text().splitlines(keepends=True) if not l.startswith('MM\tVersion:'))
  if reference is None:reference=text
  assert text==reference,name
  wall,user,system,rss=map(float,(out/f'{name}.time').read_text().split())
  stats=json.loads((out/f'{name}.stats.json').read_text())
  admission=stats.get('memory_admission')
  if admission:
   assert admission['workers']==(1 if name=='bounded_serial' else 2),admission
   assert rss*1024<admission['budget_bytes'],(name,rss,admission)
  r={'name':name,'command':[s.replace(str(ROOT)+'/', '') for s in command],'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'wall_seconds':wall,'cpu_seconds':user+system,'max_rss_kib':rss,'admission':admission,'output_exact':True};runs.append(r);print(json.dumps(r),flush=True)
 report={'input_sha256':hashlib.sha256(fixture.read_bytes()).hexdigest(),'records':8,'bins_per_record':1_000_000,'runs':runs,'scope':'Two-iteration allocation/ordered-output regression; not a speedup benchmark or full-fit qualification.'}
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()

"""Fixed local refinement of the successful joint-source tile mechanism."""
import sys
from pathlib import Path
import exhaust_cpu as e
e.RAW=Path('work/exhaust/refine');e.REPORT='bench/exhaust-refine.json'
e.CONFIGS={'joint2s16':(2,16,16),'joint4s16':(4,8,16),'joint2s32':(2,16,32)}
if __name__=='__main__':getattr(e,sys.argv[1])()

#!/usr/bin/env python3
"""Reproduce the README figure from the audited v0.6.3 timing evidence."""
import hashlib,json,statistics
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[1]
source=ROOT/'bench/hg001-speed-results.json'; data=json.loads(source.read_text())
keys=['c-one','strict-one','equivalent-one','strict-full','equivalent-full']
labels=['Vanilla C','Rust strict','Rust equivalent','Rust strict\n2 admitted workers · memory-limited','Rust equivalent\n16 configured workers']
positions=[5,4,3,1,0]
colors=['#8c959d','#bc8b32','#236d9a','#bc8b32','#236d9a']
fig,ax=plt.subplots(figsize=(10,6.8))
fig.subplots_adjust(left=.34,right=.96,top=.80,bottom=.30)
rows=[]
for key,label,y,color in zip(keys,labels,positions,colors):
    runs=[r for r in data['rows'] if r['config']==key and r['phase']!='warmup']
    warmups=[r for r in data['rows'] if r['config']==key and r['phase']=='warmup']
    assert len(runs)==3 and len(warmups)==1 and all(r['output_exact'] for r in runs+warmups)
    times=[r['wall_seconds'] for r in runs];median=statistics.median(times);low,high=min(times),max(times)
    assert median==data['summary'][key]['median_seconds'] and [low,high]==data['summary'][key]['range_seconds']
    ax.barh(y,median,color=color,height=.53,zorder=3)
    ax.errorbar(median,y,xerr=[[median-low],[high-median]],color='#25313a',capsize=3,linewidth=1,zorder=4)
    ax.text(high+45,y,f'{median:,.2f} s',va='center',fontsize=11,color='#202b33')
    rows.append(dict(configuration=key,median_seconds=median,range_seconds=[low,high],peak_rss_mib=data['summary'][key]['peak_rss_mib']))
ax.set_yticks(positions,labels,fontsize=11)
ax.set_xlim(0,3650);ax.set_xticks([0,1000,2000,3000]);ax.set_xlabel('Wall time per whole-autosome fit (seconds; lower is faster)',fontsize=10)
ax.set_ylim(-.6,5.6);ax.tick_params(axis='y',length=0,pad=12)
ax.grid(axis='x',color='#e4e8eb',zorder=0);ax.spines[['top','right','left']].set_visible(False)
ax.spines['bottom'].set_color('#a5adb3');ax.axhline(2,color='#dce2e6',linewidth=1)
fig.text(.04,.945,'PSMC-rs on public HG001: controlled timing',fontsize=17,weight='bold',color='#202b33')
fig.text(.04,.90,'22 autosomes · 64 states · 30 iterations · i5-12600K shared host · Rust v0.6.3',fontsize=10,color='#4b5964')
fig.text(.04,.827,'SINGLE CORE',fontsize=10,weight='bold',color='#4b5964')
fig.text(.04,.53,'FULL CPU AFFINITY',fontsize=10,weight='bold',color='#4b5964')
fig.text(.04,.11,'Bars: median of 3 measured runs. Whiskers: observed range, not confidence intervals.\nOne complete warmup excluded per configuration. Strict full-affinity budget: 8 GiB; 2 of 16 workers admitted.\nSingle-fit evidence only; these are not bootstrap-batch times or a fresh v0.8.0 speed benchmark.',fontsize=9,color='#4b5964',linespacing=1.5)
fig.text(.04,.035,'Source: docs/hg001-speed-report.md · bench/hg001-speed-results.json',fontsize=9,color='#4b5964')
for suffix in ['png','svg']:fig.savefig(ROOT/f'docs/assets/hg001-benchmark.{suffix}',dpi=180,metadata={'Creator':'PSMC-rs benchmark plotting script'})
plt.close(fig)
(ROOT/'docs/assets/hg001-benchmark-data.json').write_text(json.dumps(dict(source='bench/hg001-speed-results.json',source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),rows=rows),indent=2)+'\n')

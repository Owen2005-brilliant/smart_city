"""Run alongside validate.py and the original frozen tables."""
from pathlib import Path
from types import ModuleType
import numpy as np
import math
for delay in range(6):
 v=ModuleType('experiment')
 source=Path('validate.py').read_text().split('def run(period,cuts):')[0]
 exec(source.replace('DELAY=3',f'DELAY={delay}'),vars(v))
 for train_end,select_start,test_start,test_end in [('2025-07-01','2026-01-01','2026-07-01','2027'),('2025-01-01','2025-07-01','2026-01-01','2026-07-01')]:
  tr=v.dates<train_end;val=(v.dates>=select_start)&(v.dates<test_start);te=(v.dates>=test_start)&(v.dates<test_end)
  def score(x,h,fit,d):
   feature=np.column_stack([x[:,0]+h*np.maximum(0,x[:,1]),x[:,5]])
   return v.odds(feature,fit,d)
  s0=score(v.X,30,tr,0)
  if delay:
   s0=s0-math.log(2)
   s1=np.where(v.ok,score(v.X2,30-delay,tr&v.ok,delay),-np.inf)
  else:s1=np.full(len(s0),-np.inf)
  peak=np.maximum(s0,s1)
  for mode in ['locked','matched']:
   early=np.zeros(len(s0),bool);late=early.copy()
   for group in (v.nt,~v.nt):
    if mode=='locked':
     neg=np.round(peak[val&~v.y&group],8)
     cut=min(i for i in np.unique(neg) if np.mean(neg>=i)<=.1)
     threshold=(cut+max(neg[neg<cut]))/2
     a,b=s0,s1
    else:
     a,b=np.round(s0,8)+v.tie,np.round(s1,8)+v.tie
     threshold=v.threshold(np.maximum(a,b),np.flatnonzero(te&group),.1)
    early[group]=a[group]>=threshold
    late[group]=(~early[group])&(b[group]>=threshold)
   timely=(early&(v.lead>=5))|(late&(v.lead>=5+delay))
   def counts(mask):
    return (sum(timely&mask),sum((early|late)&~v.y&mask))
   print(delay,test_start,mode,*map(int,counts(te)),*map(int,counts(te&v.nt)),int(sum(v.ok&te)),int(sum(te&v.y&(v.lead>=5+delay))))

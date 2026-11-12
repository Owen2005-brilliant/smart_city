from pathlib import Path
from types import ModuleType
v=ModuleType('experiment')
exec(Path('validate.py').read_text().split('def run(period,cuts):')[0],vars(v))
import numpy as np
import math
for cut in [('2025-07-01','2026-01-01','2026-07-01','2027-01-01'),('2025-01-01','2025-07-01','2026-01-01','2026-07-01')]:
 tr=v.dates<cut[0]; ca=(v.dates>=cut[0])&(v.dates<cut[1]); val=(v.dates>=cut[1])&(v.dates<cut[2]); test=(v.dates>=cut[2])&(v.dates<cut[3])
 def score(x,minutes,mask,delay):
  ext=x[:,0]+minutes*np.maximum(0,x[:,1])
  return v.odds(np.column_stack([ext,x[:,5]]),mask,delay)
 simple=v.plan(score(v.X,30,tr,0),score(v.X2,27,tr&v.ok,3),np.ones(len(v.y),dtype=bool),math.log(2))
 l,u=v.bands(v.X[:,[0,1,2,3,5,6,7]],tr,ca)['tail']
 gate=(l<4)&(u>=4)
 rich=v.plan(v.odds(v.X,tr,0),v.odds(v.X2,tr&v.ok,3),gate,math.log(2))
 for group,mask in [('all',np.ones(len(v.y),dtype=bool)),('non',v.nt),('tidal',~v.nt)]:
  idx=np.flatnonzero(mask&test); vi=np.flatnonzero(mask&val)
  print(cut[2],group,'crossing interval',gate[idx].sum(),len(idx))
  def count(p,ix,cal):
   s=np.maximum(p[0],p[1]);h=v.threshold(s,cal,.1)
   m=v.alarm_result(p,ix,h)
   return [m['timely'],m['fp']]
  for p in [simple,rich]: print('matched & frozen',count(p,idx,idx),count(p,idx,vi))
  if group=='all' and cut[2]=='2026-07-01':
   solo=v.plan(score(v.X,30,tr,0))
   rng=np.random.default_rng(37); chunks=[idx[v.blocks[idx]==b] for b in np.unique(v.blocks[idx])]
   def recall(p,sub):
    a,b,_=p; neg=np.maximum(a,b)[sub[~v.y[sub]]]
    k=int(.1*len(neg));h=np.sort(neg)[-k]
    f=(k-np.sum(neg>h))/np.sum(neg==h)
    def timely(early,late):return np.sum((early&(v.lead[sub]>=5))|(~early&late&(v.lead[sub]>=8)))
    return (f*timely(a[sub]>=h,b[sub]>=h)+(1-f)*timely(a[sub]>h,b[sub]>h))/sum(v.y[sub])
   bootstrap=[]
   for _ in range(2000):
    sub=np.concatenate([chunks[k] for k in rng.integers(len(chunks),size=len(chunks))])
    if sum(v.y[sub]) and sum(~v.y[sub])>=10:
     r=recall(simple,sub);bootstrap.append((r-recall(solo,sub),recall(rich,sub)-r))
   print('solo',count(solo,idx,idx),'bootstrap simple2-simple1 and rich-simple2',np.quantile(bootstrap,[.025,.975],axis=0))
  diff=[]
  for b in np.unique(v.blocks[idx]):
   sub=idx[v.blocks[idx]!=b]
   diff.append((count(rich,sub,sub)[0]-count(simple,sub,sub)[0])/sum(v.y[sub]) if sum(v.y[sub]) else float('nan'))
  print('leave-1-block',np.nanmin(diff),np.nanmax(diff))

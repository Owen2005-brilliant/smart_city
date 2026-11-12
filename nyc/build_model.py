"""Run in this directory with the existing validation script and FloodNet snapshots."""
import csv,json,math
from pathlib import Path
from types import ModuleType
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

v=ModuleType('cohort')
exec(Path('validate.py').read_text().split('def run(period,cuts):')[0],vars(v))
train=v.dates<'2025-07-01'
selection=(v.dates>='2026-01-01')&(v.dates<'2026-07-01')
test=v.dates>='2026-07-01'
params=[]; scores=[]
for delay,x,available in [(0,v.X,train),(3,v.X2,train&v.ok)]:
    ext=x[:,0]+(30-delay)*np.maximum(0,x[:,1])
    features=np.column_stack([ext,x[:,5]])
    fit=available & (~v.y | (v.lead>=5+delay))
    pipeline=make_pipeline(StandardScaler(),LogisticRegression(max_iter=2000)).fit(features[fit],v.y[fit])
    scale,logit=pipeline.steps[0][1],pipeline.steps[1][1]
    coef=logit.coef_[0]/scale.scale_
    bias=float(logit.intercept_[0]-coef@scale.mean_)-(0 if delay else math.log(2))
    params.append(dict(depth=float(coef[0]),tide=float(coef[1]),bias=bias))
    scores.append(features@coef+bias)
peak=np.maximum(scores[0],np.where(v.ok,scores[1],-np.inf))
# Choose a cutoff between distinct validation scores; equal scores get the same decision.
def cutoff_for(mask):
    neg=np.round(peak[selection&~v.y&mask],8)
    boundary=min(s for s in np.unique(neg) if np.mean(neg>=s)<=.1)
    return float((boundary+max(neg[neg<boundary]))/2)
cutoffs=[cutoff_for(v.X[:,5]==flag) for flag in [0,1]]
threshold=np.where(v.X[:,5]==1,cutoffs[1],cutoffs[0])
first=scores[0]>=threshold
second=~first&v.ok&(scores[1]>=threshold)
stats={}
for label,mask in [('全样本',test),('非潮汐站',test&(v.X[:,5]==0))]:
    n=int(sum(mask));pos=int(sum(mask&v.y))
    tp=int(sum(mask&v.y&(first|second)));fp=int(sum(mask&~v.y&(first|second)))
    timely=int(sum(mask&((first&(v.lead>=5))|(second&(v.lead>=8)))))
    stats[label]=dict(n=n,pos=pos,fp=fp,tp=tp,timely=timely)
data=dict(params=params,cutoffs=cutoffs,stats=stats)
Path('model.json').write_text(json.dumps(data,ensure_ascii=False,indent=2))
examples=[]
for name,rule in [('复查案例',second&v.y&(v.lead>=8)),('快速上涨',~first&v.y&(v.lead>=0)&(v.lead<5)),('误报案例',(first|second)&~v.y)]:
    choices=np.flatnonzero(test&rule&(v.X[:,5]==(name!='快速上涨')))
    if not len(choices): choices=np.flatnonzero(test&rule)
    i=choices[0];r=v.cohort[i]
    wet=r['cut']-300
    readings=[[s-wet,d] for s,d in zip(r['t'],r['d']) if wet<=s<=wet+2100]
    examples.append(dict(name=name,site=r['site'],date=r['date'],tide=bool(v.X[i,5]),points=readings))
Path('examples.json').write_text(json.dumps(examples,ensure_ascii=False))
# Oracle for testing JavaScript replays. Never included in the inference parameters.
oracle=[]
for i in np.flatnonzero(test):
    r=v.cohort[i];wet=r['cut']-300
    oracle.append(dict(p=[[s-wet,d] for s,d in zip(r['t'],r['d']) if wet<=s<=wet+480],tide=bool(v.X[i,5]),alarm=5 if first[i] else 8 if second[i] else None))
Path('oracle.json').write_text(json.dumps(oracle))
print(json.dumps(data,ensure_ascii=False))

"""Run from the directory with events.csv and sites.csv. Outputs are reproducible."""
import csv
import hashlib
import json
import math
from bisect import bisect_right
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

WET=10/25.4
DATE='%m/%d/%Y %I:%M:%S %p'
DELAY=3
BUDGET=.10
def rows(name):
    with open(name,newline='') as f: return list(csv.DictReader(f))
sites={r['Sensor ID']:r for r in rows('sites.csv')}
events=sorted(rows('events.csv'),key=lambda e:datetime.strptime(e['Flood Start Datetime (GMT)'],DATE))

def features(t,d,i,j,cut,site):
    # i is the first wet reading; j is exclusive.
    elapsed=(t[j-1]-t[i])/60
    slope=(d[j-1]-d[i])/max(elapsed,1/60)
    height=site['Sensor Ground Height Above Local Low Point (inches)']
    return [d[j-1],slope,d[i],(cut-t[j-1])/60,j-i,int(site['Tidally Influenced']=='Yes'),float(height or 0),int(not height)]

cohort=[]
block_end=datetime.min
block=-1
for e in events:
    start=datetime.strptime(e['Flood Start Datetime (GMT)'],DATE)
    end=datetime.strptime(e['Flood End Datetime (GMT)'],DATE)
    if start-block_end>timedelta(hours=24): block+=1
    block_end=max(end,block_end)
    t=json.loads(e['Time Series Depth Timestamps (seconds)'])
    d=json.loads(e['Time Series Depth Values (inches)'])
    wet=next((i for i,value in enumerate(d) if value>WET),None)
    if wet is None: continue
    cut=t[wet]+300
    j=bisect_right(t,cut)
    if cut-t[j-1]>180 or d[j-1]<=WET or max(d[:j])>=4: continue
    stop=bisect_right(t,cut+1800)
    until=min(t[-1],cut+1800)
    support=[t[j-1],*t[j:stop],until]
    if stop==j or max(np.diff(support))>300 or (until<cut+1800 and d[-1]!=0): continue
    sensor=e['Sensor ID']
    x=features(t,d,wet,j,cut,sites[sensor])
    cut2=cut+60*DELAY
    j2=bisect_right(t,cut2)
    # A known threshold breach, stale/dry latest reading or no new packet forbids recheck.
    eligible=j2>j and max(d[j:j2])<4 and d[j2-1]>WET and cut2-t[j2-1]<=180
    x2=features(t,d,wet,j2,cut2,sites[sensor]) if eligible else x
    crossing=next((k for k in range(j,stop) if d[k]>=4),None)
    lower_lead=max(0,(t[crossing-1]-cut)/60) if crossing is not None else -1
    key=sensor+'|'+start.isoformat()
    tie=int(hashlib.sha256(key.encode()).hexdigest()[:12],16)/16**12
    cohort.append(dict(key=key,date=start.date().isoformat(),x=x,x2=x2,eligible=eligible,peak=max(d[j:stop]),
                 lead=lower_lead,block=block,tie=tie,t=t,d=d,cut=cut,site=e['Sensor Name']))
def col(k):return np.array([r[k] for r in cohort])
X=col('x');X2=col('x2');ok=col('eligible');z=col('peak');y=z>=4;lead=col('lead')
dates=col('date');blocks=col('block');nt=X[:,5]==0; tie=col('tie')*1e-9
assert len(cohort)==2771
def order_stat(a,q):
    a=np.sort(a)
    return a[min(len(a)-1,math.ceil((len(a)+1)*q)-1)]
def odds(x,train,delay):
    keep=train & (~y | (lead>=delay+5))
    model=make_pipeline(StandardScaler(),LogisticRegression(max_iter=2000))
    model.fit(x[keep],y[keep])
    return model.decision_function(x)
def bands(x,tr,ca):
    def pred(q):
        mod=GradientBoostingRegressor(loss='quantile',alpha=q,n_estimators=75,max_depth=2,min_samples_leaf=20,random_state=42)
        return mod.fit(x[tr],z[tr]).predict(x)
    a,b=pred(.05),pred(.95)
    lo=np.minimum(a,b);hi=np.maximum(a,b)
    adj=max(0.,order_stat(np.maximum(lo-z,z-hi)[ca],.9))
    l=np.maximum(0,lo-adj);u=hi+adj
    risk=hi>=np.quantile(hi[tr],.75)
    # Aim for 90% positive upper-side coverage in historical bins, expand only.
    positive=ca&y
    pooled=max(0.,order_stat((z-u)[positive],.9))
    extra=np.zeros(len(y))
    for group in (False,True):
        mask=positive&(risk==group)
        extra[risk==group]=max(0.,order_stat((z-u)[mask],.9)) if sum(mask)>=20 else pooled
    return {'global':(l,u),'tail':(l,u+extra),'uniform_width':(l,u+extra[ca].mean()),'positive_pooled':(l,u+pooled)}
def ranked(a):return np.round(a,8)+tie
def plan(a,b=None,gate=None,discount=0):
    score=ranked(a-(discount*gate if gate is not None else 0))
    wait=np.zeros(len(y),dtype=bool) if b is None else (np.ones(len(y),dtype=bool) if gate is None else gate)
    later=np.full(len(y),-np.inf) if b is None else np.where(wait&ok,ranked(b),-np.inf)
    return score,later,wait
def threshold(peak_scores,idx,budget):
    negatives=peak_scores[idx[~y[idx]]]
    k=math.floor(len(negatives)*budget+1e-10)
    if not k: return np.nextafter(np.max(negatives),np.inf)
    return np.sort(negatives)[-k]
def alarm_result(policy,idx,h):
    a,b,w=policy
    early=a[idx]>=h
    later=(~early)&(b[idx]>=h)
    useful=y[idx]&((early&(lead[idx]>=5))|(later&(lead[idx]>=5+DELAY)))
    return dict(n=len(idx),pos=int(sum(y[idx])),fp=int(sum((early|later)&~y[idx])),timely=int(sum(useful)),
                recall=float(sum(useful)/sum(y[idx])),fpr=float(sum((early|later)&~y[idx])/sum(~y[idx])),
                held=int(sum(w[idx]&~early)),rechecked=int(sum(w[idx]&~early&ok[idx])),late_alarms=int(sum(later)))
def interval_result(l,u,idx):
    lower=l[idx];upper=u[idx];peak=z[idx];pos=y[idx]
    cover=(peak>=lower)&(peak<=upper)
    score=(upper-lower)+20*(np.maximum(lower-peak,0)+np.maximum(peak-upper,0))
    return dict(n=len(idx),pos=int(sum(pos)),covered_pos=int(sum(cover&pos)),overall=cover.mean(),positive=cover[pos].mean(),
                width=(upper-lower).mean(),interval_score=score.mean(),upper_misses=int(sum(pos&(peak>upper))))
def pack(obj):
    if isinstance(obj,np.generic):return obj.item()
    raise TypeError(type(obj))
def run(period,cuts):
    tr=dates<cuts[0];ca=(dates>=cuts[0])&(dates<cuts[1]);val=(dates>=cuts[1])&(dates<cuts[2]);test=(dates>=cuts[2])&(dates<cuts[3])
    assert all(not(set(blocks[a])&set(blocks[b])) for a,b in [(tr,ca),(ca,val),(val,test)])
    s=odds(X,tr,0);s2=odds(X2,tr&ok,DELAY)
    ext=X[:,0]+30*np.maximum(0,X[:,1]);ext2=X2[:,0]+27*np.maximum(0,X2[:,1])
    cols=[0,1,2,3,5,6,7]
    intervals=bands(X[:,cols],tr,ca)
    single=bands(X[:,:1],tr,ca)['global']
    residual=z[ca]-ext[ca]
    slope_lo=np.maximum(0,ext+np.quantile(residual,.05))
    slope_hi=np.maximum(slope_lo,ext+np.quantile(residual,.95))
    intervals.update(one=single,slope=(slope_lo,slope_hi))
    policies={'slope':plan(ext),'slope_recheck':plan(ext,ext2),'timely_now':plan(s),'timely_recheck':plan(s,s2)}
    # Controls: ordinary escalation objective, a tide-adjusted rise score,
    # and a two-look scheme with the same discount for everyone.
    ordinary=make_pipeline(StandardScaler(),LogisticRegression(max_iter=2000)).fit(X[tr],y[tr]).decision_function(X)
    tide_features=np.column_stack([ext, X[:,5]])
    tide_score=odds(tide_features,tr,0)
    slope0=odds(ext[:,None],tr,0);slope3=odds(ext2[:,None],tr&ok,DELAY)
    policies['rise_uniform_wait']=plan(slope0,slope3,np.ones(len(y),dtype=bool),math.log(2))
    policies.update(ordinary_now=plan(ordinary),slope_plus_tide=plan(tide_score),
                    uniform_wait=plan(s,s2,np.ones(len(y),dtype=bool),math.log(2)))
    for method in ['global','tail','uniform_width']:
        low,high=intervals[method]
        policies['wait_'+method]=plan(s,s2,(low<4)&(high>=4),math.log(2))
    # An interval-driven rule independent of the classification score.
    for method in ['global','tail']:
        low,high=intervals[method]
        policies['upper_'+method]=plan(high)
    result={}
    for group,mask in [('all',np.ones(len(y),dtype=bool)),('non_tidal',nt),('tidal',~nt)]:
        idx=np.flatnonzero(mask&test);vi=np.flatnonzero(mask&val)
        rr=dict(reachable=int(sum(y[idx]&(lead[idx]>=5))),intervals={},policies={},blocks=len(set(blocks[idx])),positive_blocks=len(set(blocks[idx[y[idx]]])),fold_sizes=[int(sum(f&mask)) for f in (tr,ca,val,test)])
        for k,(l,u) in intervals.items():rr['intervals'][k]=interval_result(l,u,idx)
        for k,p in policies.items():
            peak=np.maximum(p[0],p[1])
            r={}
            for budget in (.05,.1,.15):
                h=threshold(peak,idx,budget)
                r[str(budget)]=alarm_result(p,idx,h)
            h=threshold(peak,vi,BUDGET)
            r['frozen']=alarm_result(p,idx,h)
            rr['policies'][k]=r
        # Paired cluster bootstrap. Duplicate clusters carry duplicate observations.
        # Fractional ties at the negative cutoff preserve the exact FP budget per resample.
        def matched(p,i):
            a,b,_=p
            scores=np.maximum(a[i],b[i]);ng=scores[~y[i]]
            budget=math.floor(.1*len(ng));cut=np.partition(ng,len(ng)-budget)[-budget] if budget else np.inf
            share=(budget-sum(ng>cut))/sum(ng==cut) if budget else 0
            def useful(v,inclusive):
                first=a[i]>=v if inclusive else a[i]>v
                second=b[i]>=v if inclusive else b[i]>v
                return sum((first&(lead[i]>=5))|(~first&second&(lead[i]>=8)))
            return ((1-share)*useful(cut,False)+share*useful(cut,True))/sum(y[i])
        rng=np.random.default_rng(811);cl=[idx[blocks[idx]==v] for v in np.unique(blocks[idx])]
        ci={};chosen=['wait_tail','timely_now','timely_recheck','upper_tail']
        for n in chosen:
            for base in ['slope','slope_recheck','timely_recheck','uniform_wait','ordinary_now','slope_plus_tide','rise_uniform_wait']:ci[n+' minus '+base]=[]
        for a,b in [('tail','global'),('tail','uniform_width'),('tail','one'),('tail','slope')]:ci[a+' coverage minus '+b]=[]
        for _ in range(1200):
            i=np.concatenate([cl[j] for j in rng.integers(len(cl),size=len(cl))])
            if not np.any(y[i]) or not np.any(~y[i]):continue
            mr={k:matched(policies[k],i) for k in chosen+['slope','slope_recheck','uniform_wait','ordinary_now','slope_plus_tide','rise_uniform_wait']}
            for n in chosen:
                for base in ['slope','slope_recheck','timely_recheck','uniform_wait','ordinary_now','slope_plus_tide','rise_uniform_wait']:ci[n+' minus '+base].append(mr[n]-mr[base])
            ip=i[y[i]]
            coverage={k:np.mean((z[ip]>=l[ip])&(z[ip]<=u[ip])) for k,(l,u) in intervals.items()}
            for k in ['global','uniform_width','one','slope']:ci['tail coverage minus '+k].append(coverage['tail']-coverage[k])
        rr['ci95']={k:np.quantile(v,[.025,.975]).tolist() for k,v in ci.items()}
        result[group]=rr
        if period=='main' and group in ('all','non_tidal'):
            # Per-event frozen decisions for an actual classroom replay.
            export=[]
            for i in idx:
                d=cohort[i];row=dict(key=d['key'],site=d['site'],non_tidal=bool(nt[i]),peak=z[i],lead=lead[i],cut=d['cut'],t=d['t'],depth=d['d'])
                for k in ['slope','slope_recheck','wait_tail','timely_now']:
                    a,b,w=policies[k];h=threshold(np.maximum(a,b),vi,.1)
                    row[k]=0 if a[i]>=h else DELAY if b[i]>=h else None
                row['updated']=bool(ok[i])
                row['ordinary_interval']=[v[i] for v in intervals['global']]
                row['uniform_interval']=[v[i] for v in intervals['uniform_width']]
                row['defer']=bool(policies['wait_tail'][2][i] and row['wait_tail']!=0)
                row['band']=[v[i] for v in intervals['tail']]
                export.append(row)
            Path('replay_'+group+'.json').write_text(json.dumps(export,default=pack))
    return result

periods={'main':['2025-07-01','2026-01-01','2026-07-01','2027-01-01'],
         'prior':['2025-01-01','2025-07-01','2026-01-01','2026-07-01']}
results={k:run(k,cuts) for k,cuts in periods.items()}
assert results['main']['all']['policies']['slope']['0.1']['pos']==192
assert results['main']['non_tidal']['policies']['slope']['0.1']['pos']==67
Path('results.json').write_text(json.dumps(results,indent=2,default=pack))

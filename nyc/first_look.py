"""Compare first looks at minute 2 or 5 on a common FloodNet cohort."""
import argparse
import csv
import hashlib
import json
import math
from bisect import bisect_right
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

WET = 10/25.4
SCHEDULES = {'2':(2,), '2+3':(2,5), '5':(5,), '5+3':(5,8)}
PERIODS = {'main':('2025-07-01','2026-01-01','2026-07-01','2027-01-01'),
           'prior':('2025-01-01','2025-07-01','2026-01-01','2026-07-01')}
FMT = '%m/%d/%Y %I:%M:%S %p'

def records(path):
    with path.open(newline='') as file:
        return list(csv.DictReader(file))

def write_rows(path, rows):
    with path.open('w', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

@dataclass
class Look:
    reason:str
    last_time:int
    projection:float = 0

def snapshot(t, d, minute):
    cut=60*minute
    j=bisect_right(t,cut)-1
    if max(d[:j+1])>=4:
        return Look('already_crossed',t[j])
    if t[j]==0:
        return Look('no_distinct_second_reading',t[j])
    if cut-t[j]>180 or d[j]<=WET:
        return Look('stale_or_dry',t[j])
    rate=(d[j]-d[0])/(t[j]/60)
    return Look('ok',t[j],d[j]+(35-minute)*max(0,rate))

def load_events(folder):
    sites={r['Sensor ID']:r for r in records(folder/'sites.csv')}
    key='Flood Start Datetime (GMT)'
    raw=sorted(records(folder/'events.csv'),key=lambda r:datetime.strptime(r[key],FMT))
    rows=[]; skipped=Counter(); block=-1; end_of_block=datetime.min
    for r in raw:
        start=datetime.strptime(r[key],FMT)
        end=datetime.strptime(r['Flood End Datetime (GMT)'],FMT)
        if start-end_of_block>timedelta(hours=24):
            block+=1
        end_of_block=max(end_of_block,end)
        times=json.loads(r['Time Series Depth Timestamps (seconds)'])
        depths=json.loads(r['Time Series Depth Values (inches)'])
        first=next((i for i,x in enumerate(depths) if x>WET),None)
        if first is None:
            skipped['no_wet']+=1
            continue
        t=[s-times[first] for s in times[first:]]
        d=depths[first:]
        j=bisect_right(t,2100)
        if (t[-1]<2100 and d[-1]!=0) or max(np.diff(t[:j]+[min(t[-1],2100)]),default=0)>300:
            skipped['no_label_support']+=1
            continue
        cross=next((i for i,x in enumerate(d[:j]) if x>=4),None)
        # If the very first wet reading crosses, it cannot be warned in advance.
        last_low=-1 if cross is None or cross==0 else t[cross-1]/60
        sensor=r['Sensor ID']
        eid=sensor+'|'+start.isoformat()
        rows.append(dict(key=eid,site=r['Sensor Name'],date=start.date().isoformat(),
            tidal=sites[sensor]['Tidally Influenced']=='Yes',block=block,positive=cross is not None,
            last_low=last_low,peak=max(d[:j]),cross=None if cross is None else t[cross]/60,
            looks={m:snapshot(t,d,m) for m in (2,5,8)},t=t[:j],d=d[:j]))
    return rows,dict(skipped)

def basic_metrics(index, time, positive, last_low):
    alert=np.isfinite(time); pos=positive[index]; timely=alert & pos & (last_low[index]-time>=5)
    return dict(n=len(index),pos=int(sum(pos)),fp=int(sum(alert&~pos)),timely=int(sum(timely)),
                late=int(sum(alert&pos&~timely)),miss=int(sum(~alert&pos)))

def cutoff(scores, budget, locked=False):
    # -inf indicates that a policy cannot act. Targets never exceed the finite count.
    k=math.floor(len(scores)*budget)
    finite=np.sort(scores[np.isfinite(scores)])[::-1]
    if k<=0 or not len(finite):return np.inf
    if k>=len(finite):return -1e20
    if locked:
        if finite[k-1]==finite[k]:return np.nextafter(finite[k],np.inf)
        return (finite[k-1]+finite[k])/2
    return finite[k-1]

def run(data, period, export=None):
    dates=np.array([r['date'] for r in data])
    pos=np.array([r['positive'] for r in data])
    tide=np.array([r['tidal'] for r in data])
    low=np.array([r['last_low'] for r in data])
    block=np.array([r['block'] for r in data])
    jitter=np.array([int(hashlib.sha256(r['key'].encode()).hexdigest()[:12],16)/16**12*1e-9 for r in data])
    train_end,valid_start,test_start,test_end=PERIODS[period]
    train=dates<train_end
    valid=(dates>=valid_start)&(dates<test_start)
    test=(dates>=test_start)&(dates<test_end)
    assert not set(block[test])&(set(block[train])|set(block[valid]))
    assert not set(block[train])&set(block[valid])
    eligible={m:np.array([r['looks'][m].reason=='ok' for r in data]) for m in (2,5,8)}
    features={m:np.column_stack([[r['looks'][m].projection for r in data],tide]) for m in eligible}
    plans={}
    for name,schedule in SCHEDULES.items():
        values=[]
        if export is not None and len(schedule)==2:
            export[name]={'schedule':list(schedule),'params':[],'cutoffs':[],'precision':8}
        for stage,m in enumerate(schedule):
            ok=eligible[m].copy()
            if stage:
                ok &= eligible[schedule[0]] & np.array([r['looks'][m].last_time>60*schedule[0] for r in data])
            fit=train & ok & (~pos | (low>=m+5))
            model=make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000)).fit(features[m][fit],pos[fit])
            score=model.decision_function(features[m])-(math.log(2) if len(schedule)>1 and stage==0 else 0)
            if export is not None and name in export:
                scaler, logistic = model.steps[0][1], model.steps[1][1]
                weights = logistic.coef_[0] / scaler.scale_
                bias = float(logistic.intercept_[0] - weights @ scaler.mean_)
                if stage == 0: bias -= math.log(2)
                export[name]['params'].append({'depth':float(weights[0]),'tide':float(weights[1]),'bias':bias})
            values.append(np.where(ok,np.round(score,8),-np.inf))
        plans[name]=np.column_stack(values)
    metrics=[]; decision_rows=[]; ranges=[]
    test_ids=np.flatnonzero(test)
    for scope,base_mask in [('population',np.ones(len(pos),bool)),('both_first_looks_available',eligible[2]&eligible[5])]:
        target=test&base_mask
        for name,matrix in plans.items():
            schedule=np.array(SCHEDULES[name])
            for mode in ['matched','frozen']:
                scores=matrix+(jitter[:,None] if mode=='matched' else 0)
                ranks=scores.max(axis=1)
                for budget in ([.05,.10,.15] if mode=='matched' else [.1]):
                    limits=np.empty(len(pos))
                    for group in (False,True):
                        # Frozen thresholds always come from the whole validation population.
                        neg=(valid if mode=='frozen' else target)&(tide==group)&~pos
                        limits[tide==group]=cutoff(ranks[neg],budget,locked=mode=='frozen')
                    if export is not None and name in export and mode=='frozen' and scope=='population':
                        export[name]['cutoffs']=[float(limits[np.flatnonzero(tide==g)[0]]) for g in (False,True)]
                    when=np.where((scores>=limits[:,None])&np.isfinite(scores),schedule,np.inf).min(axis=1)
                    for group,mask in [('all',target),('non_tidal',target&~tide),('tidal',target&tide)]:
                        ids=np.flatnonzero(mask)
                        metrics.append(dict(period=period,scope=scope,policy=name,mode=mode,budget=budget,group=group,
                            **basic_metrics(ids,when[ids],pos,low)))
                    if scope=='population' and budget==.1:
                        for i in test_ids:
                            if mode=='matched' or period=='main':
                                decision_rows.append(dict(period=period,key=data[i]['key'],policy=name,mode=mode,
                                    time=None if not np.isfinite(when[i]) else int(when[i])))
    # Paired block bootstrap. Match the budget within each stratum again on each replicate.
    def sufficient(matrix,schedule,index):
        scores=matrix[index]+jitter[index,None]
        high=scores.max(axis=1)
        total=0.
        for group in (False,True):
            g=tide[index]==group
            if not np.any(g):continue
            neg=high[g&~pos[index]]
            if not len(neg):return np.nan
            h=cutoff(neg,.1)
            ties=sum(neg==h)
            weight=min(1,max(0,(math.floor(.1*len(neg))-sum(neg>h))/ties)) if ties and np.isfinite(h) else 0
            for equal,part in [(True,weight),(False,1-weight)]:
                if not part:continue
                triggered=(scores>=h if equal else scores>h)&np.isfinite(scores)
                when=np.where(triggered,np.array(schedule),np.inf).min(axis=1)
                total+=part*np.sum(g&pos[index]&(low[index]-when>=5))
        return total
    rng=np.random.default_rng(179)
    clusters=[test_ids[block[test_ids]==b] for b in np.unique(block[test])]
    for label,include in [('all',np.ones(len(pos),bool)),('non_tidal',~tide)]:
        delta=[]
        for _ in range(1500):
            idx=np.concatenate([clusters[k] for k in rng.integers(len(clusters),size=len(clusters))])
            idx=idx[include[idx]]
            if not np.any(pos[idx]):continue
            a=sufficient(plans['2+3'],SCHEDULES['2+3'],idx)
            b=sufficient(plans['5+3'],SCHEDULES['5+3'],idx)
            if np.isfinite(a+b):delta.append((a-b)/sum(pos[idx]))
        q=np.quantile(delta,[.025,.975])
        ranges.append(dict(period=period,group=label,low=q[0],high=q[1],valid_replicates=len(delta)))
    availability=[]
    for group,mask in [('all',test),('non_tidal',test&~tide)]:
        for m in (2,5):
            ii=np.flatnonzero(mask)
            reasons=Counter(data[i]['looks'][m].reason for i in ii)
            availability.append(dict(period=period,group=group,minute=m,n=len(ii),pos=sum(pos[ii]),
                eligible=sum(eligible[m][ii]),reachable=sum(pos[ii]&(low[ii]>=m+5)),
                reachable_and_eligible=sum(pos[ii]&eligible[m][ii]&(low[ii]>=m+5)),
                no_second=reasons['no_distinct_second_reading'],crossed=reasons['already_crossed'],stale_dry=reasons['stale_or_dry'],
                blocks=len(set(block[ii])),positive_blocks=len(set(block[ii[pos[ii]]]))))
    return metrics,decision_rows,ranges,availability

def main():
    arg=argparse.ArgumentParser();arg.add_argument('--data-dir',type=Path,default=Path('.'))
    arg.add_argument('--out',type=Path,default=Path('result'));args=arg.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    rows,excluded=load_events(args.data_dir)
    exported_models={}
    by_type=[[] for _ in range(4)]
    for period in PERIODS:
        for target,new in zip(by_type,run(rows,period,exported_models if period=='main' else None)):target.extend(new)
    cases=[]
    for key in ['Q-188th-st-58th-ave-1zbc0d|2026-07-18T16:30:35','BK-dewitt-ave-williams-ave-215zzc|2026-07-15T22:39:07']:
        r=next(r for r in rows if r['key']==key)
        cases.append({'site':r['site'],'date':r['date'],'key':key,'tidal':bool(r['tidal']),'points':list(zip(r['t'],r['d']))})
    with (args.out/'compare.json').open('w') as f:
        json.dump({'models':exported_models,'cases':cases},f,ensure_ascii=False,indent=2)
    for name,items in zip(['metrics','decisions','paired_intervals','availability'],by_type):
        write_rows(args.out/(name+'.csv'),items)
    Path(args.out/'cohort.json').write_text(json.dumps({'scorable':len(rows),'excluded':excluded,
        'sources':{n:hashlib.sha256((args.data_dir/n).read_bytes()).hexdigest() for n in ('events.csv','sites.csv')}},indent=2))
    write_rows(args.out/'truth.csv',[dict(key=r['key'],site=r['site'],date=r['date'],tidal=r['tidal'],
        block=r['block'],positive=r['positive'],last_low=r['last_low'],peak=r['peak'],cross=r['cross'],
        first2=r['looks'][2].reason,first5=r['looks'][5].reason) for r in rows])
if __name__=='__main__':main()

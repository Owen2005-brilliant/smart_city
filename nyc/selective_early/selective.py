"""Optional early alarm with a shared false-alarm budget. No target-period refitting."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import numpy as np
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from first_look import load_events, PERIODS, basic_metrics, write_rows, run

def limit(values,k,matched):
    if k==0:return np.inf
    finite=np.sort(values[np.isfinite(values)])[::-1]
    if k>=len(finite):return -1e20
    if matched:return finite[k-1]
    if finite[k-1]==finite[k]:return np.nextafter(finite[k],np.inf)
    return (finite[k-1]+finite[k])/2

def scores(rows, model):
    result=[]
    for i,(minute,p) in enumerate(zip(model['schedule'],model['params'])):
        values=[]
        for r in rows:
            looks=r['looks'];point=looks[minute]
            ok=point.reason=='ok'
            if i:
                first=model['schedule'][0]
                ok=ok and looks[first].reason=='ok' and point.last_time>60*first
            s=p['depth']*point.projection+p['tide']*r['tidal']+p['bias']
            values.append(round(s,8) if ok else -np.inf)
        result.append(np.array(values))
    return np.column_stack(result)

def get_alarm(two, five, tiebreak, y, tides, membership, fraction, mode, policy):
    matched=mode=='matched'
    jitter=tiebreak[:,None] if matched else 0.
    a=two+jitter;b=five+jitter
    out=np.full(len(y),np.inf); limits=[]
    for tide in (False,True):
        group=tides==tide
        neg=membership&group&~y
        budget=math.floor(.1*sum(neg))
        early=np.zeros(len(y),bool)
        cut2=np.inf
        if not tide and policy=='exception':
            cut2=limit(a[neg,0],math.floor(fraction*sum(neg)),matched)
            early=np.isfinite(a[:,0])&(a[:,0]>=cut2)
        replacement=not tide and policy=='replace'
        matrix=a if replacement else b
        schedule=[2,5] if replacement else [5,8]
        main=limit(matrix[neg&~early].max(axis=1),budget-sum(neg&early),matched)
        accepted=(matrix>=main)&np.isfinite(matrix)
        times=np.where(accepted,schedule,np.inf).min(axis=1)
        out[group]=np.where(early,2,times)[group]
        limits.append([cut2,main])
    return out,limits

def execute(folder,destination):
    rows,_=load_events(folder)
    dates=np.array([r['date'] for r in rows]);tides=np.array([r['tidal'] for r in rows])
    y=np.array([r['positive'] for r in rows]);low=np.array([r['last_low'] for r in rows]);blocks=np.array([r['block'] for r in rows])
    ties=np.array([int(hashlib.sha256(r['key'].encode()).hexdigest()[:12],16)/16**12*1e-9 for r in rows])
    rising=np.array([r['looks'][2].projection>r['d'][0] for r in rows])
    metrics=[]; cases=[]; cis=[]; changes=[]; cuts=[]
    for period,(_,start,split,end) in PERIODS.items():
        models={}; run(rows,period,models)
        two=scores(rows,models['2+3']); five=scores(rows,models['5+3'])
        valid=(dates>=start)&(dates<split);test=(dates>=split)&(dates<end)
        for mode,sample in [('matched',test),('frozen',valid)]:
            alarms={}
            for name,policy,fraction in [('5/8','base',0),('replace','replace',0),('reserve1','exception',.01),('reserve2','exception',.02),('reserve3','exception',.03)]:
                early_scores=two.copy()
                if policy=='exception': early_scores[~rising,0]=-np.inf
                when,limits=get_alarm(early_scores,five,ties,y,tides,sample,fraction,mode,policy)
                alarms[name]=when
                for g,(c2,c58) in enumerate(limits):
                    cuts.append(dict(period=period,mode=mode,policy=name,tidal=g,early_cutoff=c2,later_cutoff=c58))
                for group,keep in [('all',np.ones(len(y),bool)),('non_tidal',~tides),('tidal',tides)]:
                    idx=np.flatnonzero(test&keep); m=basic_metrics(idx,when[idx],y,low)
                    metrics.append(dict(period=period,mode=mode,policy=name,group=group,early_calls=int(sum(when[idx]==2)),**m))
                if mode=='matched':
                    for g in (False,True):
                        neg=test&(tides==g)&~y
                        assert sum(neg&np.isfinite(when))==int(.10*sum(neg))
            base=alarms['5/8'];candidate=alarms['reserve2']
            assert np.all(base[test&tides]==candidate[test&tides])
            accepted=lambda alarm: y&(low-alarm>=5)
            for group,mask in [('all',test),('non_tidal',test&~tides)]:
                changes.append(dict(period=period,mode=mode,group=group,
                   gained=int(sum(mask&accepted(candidate)&~accepted(base))),lost=int(sum(mask&accepted(base)&~accepted(candidate))),
                   new_fp=int(sum(mask&~y&np.isfinite(candidate)&~np.isfinite(base))),
                   avoided_fp=int(sum(mask&~y&np.isfinite(base)&~np.isfinite(candidate)))))
            for i in np.flatnonzero(test&~tides):
                cases.append(dict(period=period,mode=mode,key=rows[i]['key'],positive=bool(y[i]),
                    low=low[i],base_min=base[i],candidate_min=candidate[i]))
            if mode=='frozen':
                ix=np.flatnonzero(test&~tides); groups=[ix[blocks[ix]==k] for k in np.unique(blocks[ix])]
                rng=np.random.default_rng(317);diff=[]
                for _ in range(2000):
                    ids=np.concatenate([groups[k] for k in rng.integers(len(groups),size=len(groups))])
                    if sum(y[ids]) and sum(~y[ids]):
                        diff.append([(sum(accepted(candidate)[ids])-sum(accepted(base)[ids]))/sum(y[ids]),
                            (sum(~y[ids]&np.isfinite(candidate[ids]))-sum(~y[ids]&np.isfinite(base[ids])))/sum(~y[ids])])
                q=np.quantile(diff,[.025,.975],axis=0)
                cis.append(dict(period=period,group='non_tidal',reps=len(diff),recall_low=q[0,0],recall_high=q[1,0],fpr_low=q[0,1],fpr_high=q[1,1]))
    destination.mkdir(exist_ok=True,parents=True)
    for name,records in [('metrics',metrics),('event_decisions',cases),('thresholds',cuts),('paired_changes',changes),('fixed_threshold_ci',cis)]:
        write_rows(destination/(name+'.csv'),records)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data-dir',type=Path,default=Path(__file__).resolve().parents[1]);p.add_argument('--out',type=Path,default=Path('result'))
    args=p.parse_args();execute(args.data_dir,args.out)

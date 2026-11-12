"""Audit and compare two pre-specified minute-5 gates."""
import argparse
import csv
import json
import math
import os
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

PERIODS = {
    'main': ('2025-07-01','2026-01-01','2026-07-01','2027-01-01'),
    'prior': ('2025-01-01','2025-07-01','2026-01-01','2026-07-01'),
}
PENALTY = math.log(2)


def time_gate(record):
    """Observed prefix only, with second timestamps and depths in inches."""
    cut = record['cut']
    prefix = [(t,d) for t,d in zip(record['t'],record['d']) if cut-300 <= t <= cut]
    t0,d0 = prefix[0]
    t1,d1 = prefix[-1]
    if t1 == t0 or d1 <= d0:
        return False
    slope = (d1-d0)*60/(t1-t0)
    gaps = np.diff(np.unique([t for t,_ in prefix]))/60
    last_low_eta = (4-d1)/slope - (cut-t1)/60 - np.median(gaps)
    return 5 <= last_low_eta < 8


def historical_cut(scores,cal,y):
    neg = np.sort(scores[cal & ~y])[::-1]
    return np.nextafter(neg[int(.1*len(neg))],np.inf)


def decisions(pair,h):
    a,b=pair
    return np.where(a>=h,0.,np.where(b>=h,3.,np.inf))


def summarize(when,idx,y,lead):
    pos=y[idx]
    alerted=np.isfinite(when[idx])
    timely=pos & (lead[idx]-when[idx]>=5)
    return dict(n=len(idx),positive=int(sum(pos)),fp=int(sum(alerted & ~pos)),
                timely=int(sum(timely)),late=int(sum(alerted & pos & ~timely)),
                missed=int(sum(pos & ~alerted)))


def write(path,rows):
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=rows[0])
        w.writeheader()
        w.writerows(rows)


def paired_bootstrap(ranked,idx,v,seed=123):
    """Re-match each negative budget; fractionally count cutoff ties in repeated blocks."""
    y,lead,blocks=v['y'],v['lead'],v['blocks']
    chunks=[idx[blocks[idx]==b] for b in np.unique(blocks[idx])]
    rng=np.random.default_rng(seed)
    delta={k:[] for k in ranked if k!='original'}
    for _ in range(1500):
        sub=np.concatenate([chunks[i] for i in rng.integers(len(chunks),size=len(chunks))])
        pos=y[sub]
        k=int(.10*sum(~pos))
        if not k or not sum(pos):
            continue
        recalls={}
        for name,(a,b) in ranked.items():
            early,late=a[sub],b[sub]
            neg=np.maximum(early,late)[~pos]
            h=np.partition(neg,len(neg)-k)[-k]
            fraction=(k-sum(neg>h))/sum(neg==h)
            def recall(first,second):
                w=np.where(first,0.,np.where(second,3.,np.inf))
                return np.sum(pos&(lead[sub]-w>=5))/sum(pos)
            recalls[name]=fraction*recall(early>=h,late>=h)+(1-fraction)*recall(early>h,late>h)
        for name in delta:
            delta[name].append(recalls[name]-recalls['original'])
    return [dict(rule=name,blocks=len(chunks),used=len(values),
                 low_pp=100*np.quantile(values,.025),high_pp=100*np.quantile(values,.975))
            for name,values in delta.items()]


def run(data,dest):
    os.chdir(data)
    v={}
    exec(Path('validate.py').read_text().split('def run(period,cuts):')[0],v)
    y,lead,nt,ok,dates,x=[v[k] for k in ('y','lead','nt','ok','dates','X')]
    eta=np.array([time_gate(r) for r in v['cohort']])
    # Appending a future suffix cannot change the ETA gate.
    assert all(time_gate({**r,'t':[s for s in r['t'] if s<=r['cut']],
                             'd':[d for s,d in zip(r['t'],r['d']) if s<=r['cut']]})==g
               for r,g in zip(v['cohort'],eta))
    subset=x[:,[0,1,3,4,5]]
    urgent=y & (lead>=5) & ((lead<8) | ~ok)
    all_events=np.ones(len(y),bool)
    metrics,ledger,paired,intervals,diagnostics=[],[],[],[],[]
    deployed=json.loads(Path('model.json').read_text())

    for period,(end_train,start_val,start_test,end_test) in PERIODS.items():
        train=dates<end_train
        cal=(dates>=end_train)&(dates<start_val)
        val=(dates>=start_val)&(dates<start_test)
        test=(dates>=start_test)&(dates<end_test)
        masks=[train,cal,val,test]
        for i,mask in enumerate(masks):
            for other in masks[i+1:]:
                assert not set(v['blocks'][mask]) & set(v['blocks'][other])
        clf=make_pipeline(StandardScaler(),LogisticRegression(max_iter=2000))
        clf.fit(subset[train],urgent[train])
        score=clf.decision_function(subset)
        limit=np.quantile(score[cal&nt&~y],.90)
        gates={'original':np.zeros(len(y),bool),'relax_all_non_tidal':nt,
               'eta':nt&eta,'learned':nt&(score>limit)}
        scores=[]
        for stage,(xstage,delay) in enumerate([(x,0),(v['X2'],3)]):
            projection=xstage[:,0]+(30-delay)*np.maximum(0,xstage[:,1])
            if period=='main':
                coeff=deployed['params'][stage]
                s=coeff['bias']+coeff['depth']*projection+coeff['tide']*xstage[:,5]
                if not stage:
                    s+=PENALTY  # exported stage 1 already contains the original penalty
            else:
                s=v['odds'](np.column_stack([projection,xstage[:,5]]),train if not delay else train&ok,delay)
            assert np.isfinite(s).all()
            scores.append(s)
        first,second=scores
        plans={name:(first-PENALTY*(~gate),np.where(ok,second,-np.inf)) for name,gate in gates.items()}
        ranked={name:tuple(v['ranked'](s) for s in pair) for name,pair in plans.items()}
        for name,gate in gates.items():
            diagnostics.append(dict(period=period,rule=name,train_urgent=int(sum(train&urgent)),
                train_non_tidal_urgent=int(sum(train&nt&urgent)),cal_non_tidal_neg=int(sum(cal&nt&~y)),
                test_non_tidal_urgent=int(sum(test&nt&urgent)),gate_non_tidal=int(sum(test&gate)),
                gate_non_tidal_urgent=int(sum(test&gate&urgent))))
        for group,mask in [('non_tidal',nt),('all',all_events)]:
            idx=np.flatnonzero(mask&test)
            intervals.extend(dict(period=period,group=group,**r) for r in paired_bootstrap(ranked,idx,v))
            modes=[('matched',b) for b in (.05,.10,.15)]+[('historical',.10)]
            if period=='main':
                modes.append(('product_cut',.10))
            for mode,budget in modes:
                alarms={}
                for name,p in plans.items():
                    if mode=='matched':
                        pair=ranked[name]
                        h=v['threshold'](np.maximum(*pair),idx,budget)
                    else:
                        pair=p
                        if mode=='product_cut':
                            limits=deployed['cutoffs']
                        else:
                            high=np.maximum(*pair)
                            limits=[historical_cut(high,val & g,y) for g in (nt,~nt)]
                        h=np.where(nt,limits[0],limits[1])
                    w=decisions(pair,h)
                    alarms[name]=w
                    fields=dict(period=period,group=group,mode=mode,budget=budget)
                    stats=summarize(w,idx,y,lead)
                    if mode=='matched':
                        assert stats['fp']==int((stats['n']-stats['positive'])*budget)
                    metrics.append(dict(**fields,rule=name,**stats))
                ref=alarms['original']
                for name,w in alarms.items():
                    t0=y&(lead-ref>=5)
                    t1=y&(lead-w>=5)
                    paired.append(dict(**fields,rule=name,gained=int(sum((~t0&t1)[idx])),
                                       lost=int(sum((t0&~t1)[idx]))))
                    if budget==.10:
                        for i in idx:
                            ledger.append(dict(**fields,rule=name,key=v['cohort'][i]['key'],block=v['blocks'][i],
                                positive=int(y[i]),urgent_truth=int(urgent[i]),gate=int(gates[name][i]),
                                original_alarm=None if not np.isfinite(ref[i]) else 5+int(ref[i]),
                                alarm=None if not np.isfinite(w[i]) else 5+int(w[i]),timely=int(t1[i]),
                                lead_if_warn_at_five=lead[i]))
    dest.mkdir(exist_ok=True,parents=True)
    for path,items in [('metrics',metrics),('decisions',ledger),('paired',paired),
                       ('intervals',intervals),('diagnostics',diagnostics)]:
        write(dest/(path+'.csv'),items)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('nyc',type=Path)
    p.add_argument('--out',type=Path,default=Path('result'))
    a=p.parse_args()
    run(a.nyc.resolve(),a.out.resolve())

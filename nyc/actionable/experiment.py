"""Reproduce the prespecified two-period historical comparison."""
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from detector import NAMES, detect, features, samples, score

HERE = Path(__file__).resolve().parent
NYC = HERE.parent
sys.path.insert(0,str(NYC))
from first_look import PERIODS, basic_metrics, cutoff, load_events, write_rows


def fit(rows, labels, weights):
    scaler = StandardScaler().fit(rows, sample_weight=weights)
    model = LogisticRegression(max_iter=2000).fit(scaler.transform(rows), labels, sample_weight=weights)
    w = model.coef_[0] / scaler.scale_
    return dict(intercept=float(model.intercept_[0]-w@scaler.mean_), weights=w.tolist())


def raw(history, minute):
    (t0,d0),(t1,d1) = history[0],history[-1]
    rate = (d1-d0)*60/(t1-t0) if t1>t0 else 0.
    return d1 + (35-minute)*max(0.,rate)


def replay(event):
    observations = list(samples(zip(event['t'],event['d'])))
    rolling = [(m, features(h,m,event['tidal']),raw(h,m)) for m,h in observations]
    scheduled = []
    if event['looks'][5].reason != 'ok':
        return rolling, scheduled
    for stage,m in enumerate((5,8)):
        look = event['looks'][m]
        if look.reason!='ok' or (stage and look.last_time<=300):
            continue
        h = next(h for t,h in reversed(observations) if t<=m)
        scheduled.append((m,features(h,m,event['tidal']),look.projection))
    return rolling, scheduled


def compare(data, all_paths, period):
    train_end,val_start,test_start,test_end = PERIODS[period]
    dates = np.array([r['date'] for r in data])
    train = dates<train_end
    valid = (dates>=val_start)&(dates<test_start)
    test = (dates>=test_start)&(dates<test_end)
    block = np.array([r['block'] for r in data])
    for left,right in [(train,valid),(valid,test),(train,test)]:
        assert not set(block[left])&set(block[right])
    positive = np.array([r['positive'] for r in data])
    low = np.array([r['last_low'] for r in data])
    tidal = np.array([r['tidal'] for r in data])
    x,y,w = [],[],[]
    for i in np.flatnonzero(train):
        rolling,_ = all_paths[i]
        for minute,row,_ in rolling:
            x.append(row)
            y.append(positive[i] and low[i]>=minute+5)
            w.append(1/len(rolling))
    candidate = fit(x,y,w)
    candidate['features'] = NAMES
    old = []
    for stage,minute in enumerate((5,8)):
        sx,sy = [],[]
        for i in np.flatnonzero(train):
            for m,_,projection in all_paths[i][1]:
                if m==minute and (not positive[i] or low[i]>=m+5):
                    sx.append([projection,int(tidal[i])]);sy.append(positive[i])
        model = fit(sx,sy,np.ones(len(sx)))
        model['intercept'] -= 0 if stage else np.log(2)
        old.append(model)

    product = json.loads((NYC/'model.json').read_text())
    plans = {k:[] for k in ('rolling_candidate','rolling_raw','scheduled_candidate','scheduled_reference')}
    for i,(rolling,scheduled) in enumerate(all_paths):
        plans['rolling_candidate'].append([(m,score(row,candidate)) for m,row,_ in rolling])
        plans['rolling_raw'].append([(m,p) for m,_,p in rolling])
        plans['scheduled_candidate'].append([(m,score(row,candidate)) for m,row,_ in scheduled])
        base = []
        for m,_,p in scheduled:
            stage = int(m==8)
            if period=='main':
                f = product['params'][stage]
                value = f['bias'] + f['depth']*p + f['tide']*int(tidal[i])
            else:
                value = score([p,int(tidal[i])],old[stage])
            base.append((m,round(value,8)))
        plans['scheduled_reference'].append(base)

    # Deterministic tie-breaker for retrospective equal-FP comparisons only.
    jitter=np.array([int(hashlib.sha256(r['key'].encode()).hexdigest()[:12],16)/16**12*1.e-9 for r in data])
    metrics, decisions = [],[]
    for name,paths in plans.items():
        maxima=np.array([max((s for _,s in p),default=-np.inf) for p in paths])
        maximum=maxima.round(8)
        for mode in ('matched','historical'):
            matched=mode=='matched'
            calibration=test if matched else valid
            h=[float(cutoff((maximum+jitter if matched else maxima)[calibration&~positive&(tidal==g)],
                            .1,locked=not matched)) for g in (False,True)]
            if period=='main' and not matched and name=='scheduled_reference':
                h=product['cutoffs']
            if not matched and name=='rolling_candidate':
                candidate['thresholds']=h
            when=np.full(len(data),np.inf)
            for i in np.flatnonzero(test):
                limit=h[int(tidal[i])]
                when[i]=next((m for m,s in paths[i] if (round(s,8)+jitter[i] if matched else s)>=limit),np.inf)
                if name=='rolling_candidate' and not matched:
                    check=detect(zip(data[i]['t'],data[i]['d']),bool(tidal[i]),candidate)
                    assert check==(None if np.isinf(when[i]) else when[i])
                decisions.append(dict(period=period,key=data[i]['key'],policy=name,mode=mode,
                                      alarm_min=None if np.isinf(when[i]) else when[i],
                                      positive=int(positive[i]),tidal=int(tidal[i]),last_low=low[i],block=block[i]))
            for label,mask in [('all',test),('non_tidal',test&~tidal),('tidal',test&tidal)]:
                ids=np.flatnonzero(mask)
                metrics.append(dict(period=period,group=label,policy=name,mode=mode,
                                    **basic_metrics(ids,when[ids],positive,low)))
    if period=='main':
        (HERE/'candidate.json').write_text(json.dumps(candidate,indent=2,allow_nan=False)+'\n')
    return metrics,decisions


def main():
    data,_=load_events(NYC)
    paths=[replay(r) for r in data]
    metrics,decisions=[],[]
    for period in PERIODS:
        m,d=compare(data,paths,period)
        metrics.extend(m);decisions.extend(d)
    write_rows(HERE/'metrics.csv',metrics)
    write_rows(HERE/'decisions.csv',decisions)


if __name__=='__main__':
    main()

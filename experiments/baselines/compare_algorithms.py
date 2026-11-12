"""Run with the path to the nyc directory of midterm-freeze-v1."""
import argparse
import csv
import math
import os
from pathlib import Path

import numpy as np
from sklearn.ensemble import RandomForestClassifier


def evaluate(path, dest):
    dest.mkdir(parents=True, exist_ok=True)
    os.chdir(path)
    # Reuse the archived cohort, raw scoring, tie breaks and time definitions.
    v = {}
    exec(Path('validate.py').read_text().split('def run(period,cuts):')[0], v)
    features, later_features = v['X'], v['X2']
    positive, lead, ok, dates = (v[key] for key in ('y','lead','ok','dates'))
    both = np.ones(len(lead), dtype=bool)
    results, pairs = [], []
    for period, train_end, test_start, test_end in [
        ('main','2025-07-01','2026-07-01','2027-01-01'),
        ('prior','2025-01-01','2026-01-01','2026-07-01')]:
        train = dates < train_end
        test = (dates >= test_start) & (dates < test_end)
        assert not set(v['blocks'][train]) & set(v['blocks'][test])
        learn, forest, projections = [], [], []
        for x, delay, valid in [(features, 0, train), (later_features, 3, train & ok)]:
            ext = x[:,0] + (30-delay) * np.maximum(0,x[:,1])
            xx = np.column_stack((ext,x[:,5]))
            learn.append(v['odds'](xx,valid,delay))
            # Same two inputs, training labels, first-look odds penalty and two looks.
            good = valid & (~positive | (lead >= 5+delay))
            rf = RandomForestClassifier(n_estimators=200, min_samples_leaf=10, random_state=42, n_jobs=1)
            rf.fit(xx[good], positive[good])
            p = np.clip(rf.predict_proba(xx)[:,1], 1e-6, 1-1e-6)
            forest.append(np.log(p/(1-p)))
            projections.append(ext)
        plan = v['plan']
        plans = {'raw_once':plan(projections[0]),'raw_twice':plan(*projections),
                 'logistic_once':plan(learn[0]),'logistic_twice':plan(*learn,both,math.log(2)),
                 'random_forest_twice':plan(*forest,both,math.log(2))}
        for group, mask in [('all',both),('non_tidal',v['nt'])]:
            idx = np.flatnonzero(mask & test)
            obs = positive[idx]
            times = {}
            for method,(a,b,_) in plans.items():
                threshold = v['threshold'](np.maximum(a,b),idx,.1)
                delay = np.where(a[idx]>=threshold,0.,np.where(b[idx]>=threshold,3.,np.inf))
                times[method] = delay
                alert = np.isfinite(delay)
                tp = int(np.sum(alert & obs))
                fp = int(np.sum(alert & ~obs))
                tn = int(np.sum(~alert & ~obs))
                timely = int(np.sum(obs & (lead[idx]-delay>=5)))
                results.append(dict(period=period,group=group,method=method,n=len(idx),pos=int(obs.sum()),
                                    tp=tp,fp=fp,tn=tn,fn=int(obs.sum())-tp,timely=timely,
                                    accuracy=(tp+tn)/len(idx),precision=tp/(tp+fp) if tp+fp else None,
                                    timely_recall=timely/obs.sum()))
            ref = times['logistic_once']
            new = times['logistic_twice']
            shared = obs & np.isfinite(ref) & np.isfinite(new)
            pairs.append(dict(period=period,group=group,shared_hits=int(shared.sum()),
                              earlier=int(np.sum(new[shared]<ref[shared])),same=int(np.sum(new[shared]==ref[shared])),
                              later=int(np.sum(new[shared]>ref[shared])),
                              gained_timely=int(np.sum(obs&(lead[idx]-new>=5)&(lead[idx]-ref<5))),
                              lost_timely=int(np.sum(obs&(lead[idx]-new<5)&(lead[idx]-ref>=5)))))
    for fname,rows in [('metrics.csv',results),('paired.csv',pairs)]:
        with (dest/fname).open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=rows[0]);writer.writeheader();writer.writerows(rows)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('nyc',type=Path)
    parser.add_argument('--out',type=Path,default=Path('.'))
    args=parser.parse_args()
    evaluate(args.nyc.resolve(),args.out.resolve())

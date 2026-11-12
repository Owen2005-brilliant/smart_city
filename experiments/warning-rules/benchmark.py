"""Adapt the probability threshold/persistence decision rule to two NYC street forecasts."""
import argparse
import csv
import math
import os
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


def evaluate(data):
    os.chdir(data)
    v = {}
    exec(Path('validate.py').read_text().split('def run(period,cuts):')[0], v)
    y, dates, ok, lead = [v[k] for k in ('y','dates','ok','lead')]
    rows = []
    for period, train_end, validation_start, test_start, test_end in [
        ('main','2025-07-01','2026-01-01','2026-07-01','2027-01-01'),
        ('prior','2025-01-01','2025-07-01','2026-01-01','2026-07-01')]:
        train = dates < train_end
        valid = (dates>=validation_start) & (dates<test_start)
        test = (dates>=test_start) & (dates<test_end)
        for a,b in [(train,valid),(valid,test),(train,test)]:
            assert not set(v['blocks'][a]) & set(v['blocks'][b])
        for objective in ('timely','any_upgrade'):
            scores = []
            for x,delay,mask in [(v['X'],0,train),(v['X2'],3,train&ok)]:
                columns = np.column_stack((x[:,0]+(30-delay)*np.maximum(0,x[:,1]),x[:,5]))
                if objective=='timely':
                    s = v['odds'](columns,mask,delay)
                else:
                    model = make_pipeline(StandardScaler(),LogisticRegression(max_iter=2000))
                    s = model.fit(columns[mask], y[mask]).decision_function(columns)
                scores.append(s)
            first, second = scores
            second = np.where(ok,second,-np.inf)
            never = np.full(len(y),-np.inf)
            policies = {'any_one':(first,second),
                        'confirm_both':(never,np.minimum(first,second)),
                        'higher_first':(first-math.log(2),second)}
            for name,(s5,s8) in policies.items():
                for group,mask in [('all',np.ones(len(y),dtype=bool)),('non_tidal',v['nt'])]:
                    i = np.flatnonzero(test & mask)
                    vi = np.flatnonzero(valid & mask)
                    for mode in ('matched','historical'):
                        if mode=='matched':
                            a,b = v['ranked'](s5),v['ranked'](s8)
                            h = v['threshold'](np.maximum(a,b),i,.10)
                        else:
                            a,b = s5,s8
                            negatives = np.sort(np.maximum(a,b)[vi[~y[vi]]])[::-1]
                            budget = int(.10*len(negatives))
                            boundary = negatives[budget]
                            # Exclusive at the first disallowed score; ties stay together.
                            h = np.nextafter(boundary,np.inf)
                        times = np.where((a[i]>=h)&np.isfinite(a[i]),0,
                                         np.where((b[i]>=h)&np.isfinite(b[i]),3,np.inf))
                        alerts = np.isfinite(times)
                        tp = int(sum(alerts & y[i]))
                        fp = int(sum(alerts & ~y[i]))
                        timely = int(sum(y[i] & (lead[i]-times>=5)))
                        if mode=='matched':
                            assert fp==int(.1*sum(~y[i]))
                        rows.append(dict(period=period,group=group,objective=objective,
                                         rule=name,threshold_mode=mode,n=len(i),upgrades=int(sum(y[i])),
                                         false_alarms=fp,timely=timely,late=tp-timely,
                                         missed=int(sum(y[i]))-tp))
    return rows


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('nyc',type=Path)
    parser.add_argument('--out',type=Path,default=Path('metrics.csv'))
    args=parser.parse_args()
    out=args.out.resolve()
    rows=evaluate(args.nyc.resolve())
    with out.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)

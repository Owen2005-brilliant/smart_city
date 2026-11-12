"""Reconcile scoring totals, common event IDs and the previous paper result."""
import csv
from collections import defaultdict
from pathlib import Path
import sys
data=Path(sys.argv[1])
with (data/'metrics.csv').open() as f: metrics=list(csv.DictReader(f))
with (data/'decisions.csv').open() as f: ledger=list(csv.DictReader(f))
by=defaultdict(dict)
keys=['period','group','mode','method']
for r in ledger:
    k=tuple(r[t] for t in keys)
    assert r['event'] not in by[k]
    by[k][r['event']]=r
for r in metrics:
    p,g,mode,method=k=tuple(r[t] for t in keys)
    d=by[k].values()
    assert len(d)==int(r['n'])
    assert sum(int(x['timely']) for x in d)==int(r['timely'])
    assert sum(x['positive']=='0' and x['alarm_min']!='' for x in d)==int(r['fp'])
    assert int(r['timely'])+int(r['missed'])+int(r['late'])==int(r['pos'])
    assert set(by[k])==set(by[p,g,'matched','ours'])
    if mode=='matched': assert int(r['fp'])==(int(r['n'])-int(r['pos']))//10
ref={('main','all'):(83,74,70),('main','non_tidal'):(10,12,4),
     ('prior','all'):(54,54,49),('prior','non_tidal'):(0,0,0)}
for (p,g),counts in ref.items():
    for method,expected in zip(['ours','EFAS_any','EFAS_both'],counts):
        assert sum(int(x['timely']) for x in by[p,g,'matched',method].values())==expected
print('Verified paired event IDs, FP budgets, method totals and previous results.')

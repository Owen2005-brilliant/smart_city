import csv
from collections import defaultdict
from pathlib import Path
import sys

out=Path(sys.argv[1])
def rows(name):
    with (out/(name+'.csv')).open() as f:
        return list(csv.DictReader(f))
metrics=rows('metrics')
dec=defaultdict(dict)
for r in rows('decisions'):
    k=tuple(r[i] for i in ('period','group','mode','rule'))
    assert r['key'] not in dec[k]
    dec[k][r['key']]=r
for r in metrics:
    n,pos,timely,fp,late,miss=[int(r[i]) for i in ('n','positive','timely','fp','late','missed')]
    assert timely+late+miss==pos
    if r['mode']=='matched':
        assert fp==int((n-pos)*float(r['budget']))
    if r['budget']!='0.1':
        continue
    k=tuple(r[i] for i in ('period','group','mode','rule'))
    d=dec[k]
    assert d.keys()==dec[(*k[:3],'original')].keys()
    assert len(d)==n and sum(int(i['timely']) for i in d.values())==timely
    assert sum(i['alarm']!='' and i['positive']=='0' for i in d.values())==fp
    for i in d.values():
        if i['alarm']:
            assert (i['timely']=='1')==(i['positive']=='1' and float(i['lead_if_warn_at_five'])-(int(i['alarm'])-5)>=5)
for group,expected in [('all',(97,121)),('non_tidal',(15,49))]:
    r=next(r for r in metrics if (r['period'],r['group'],r['mode'],r['rule'])==('main',group,'product_cut','original'))
    assert (int(r['timely']),int(r['fp']))==expected
print('Verified cohort, budgets, event decisions, product and timely labels.')

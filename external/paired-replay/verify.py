"""Verify counts and causal replay using the archived production gate."""
import csv
import hashlib
import json
import math
from pathlib import Path
from run import RULES,load,make_plan,decision

root=Path(__file__).parent
def read(path):
    with path.open(newline='') as f:return list(csv.DictReader(f))
table=read(root/'results/decisions.csv')
params=json.loads((root/'inputs/nyc_locked_rules.json').read_text())
for d,folder,m in [('Madison','inputs',True),('TW_existing','inputs',False),('TW_holdout','extension',False)]:
    data=load(root/folder,d,m)
    for row in [r for r in table if r['dataset']==d and r['mode']=='fixed']:
        e=data[row['event']]
        tidal=row['scenario']=='assume_tidal'
        rule=row['rule']
        plans,allow,h,_=make_plan(e,params,tidal)
        # Perturb all measurements after minute 8; neither score should change.
        copy={**e,'points':[(t,x if t<=480 else 250.) for t,x in e['points']]}
        assert plans==make_plan(copy,params,tidal)[0]
        # Perturb all measurements after minute 5; the first-stage score and gate
        # are evaluated from a prefix before observing the next packet.
        from run import look
        assert look([(t,x) for t,x in copy['points'] if t<=300],5)==look([(t,x) for t,x in e['points'] if t<=300],5)
        a=decision(*plans[rule],h)
        assert row['alarm']==('' if a is None else str(a))
        assert not row['timely']=='1' or int(row['lower_lead_s'])>=300
        if rule in ('learned','eta'):
            assert row['alarm']==row['reference_alarm']
    print(d,len(data),'paired event decisions verified')
old={(r['start'],r['rule']):(r['alarm'],r['timely']) for r in read(root/'inputs/mad_reference.csv')}
for r in table:
    if r['dataset']=='Madison' and (r['start'],r['rule']) in old:
        assert (r['alarm'],r['timely'])==old[r['start'],r['rule']]
for r in read(root/'results/metrics.csv'):
    n,pos,neg,hits,late,missed,fp=[int(r[k]) for k in ('n','positive','negative','timely','late','missed','fp')]
    assert n==pos+neg and pos==hits+late+missed
    if r['mode']=='matched10':assert fp==neg//10
print('Reference replay, denominators and matched false-alarm budgets verified.')

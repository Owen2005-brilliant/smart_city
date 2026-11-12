"""Replay fixed policies and compute paired event counts. Python standard library."""
import argparse
import csv
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import median

RULES=('frozen','learned','eta','relax_all','first_only')


def read(path):
    with path.open(encoding='utf-8-sig',newline='') as f:
        return list(csv.DictReader(f))


def write(path,rows):
    with path.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def load(folder,tag,mad):
    station,stream,start=('site','site','start_utc') if mad else ('station','stream','start')
    prefix='mad' if mad else 'tw'
    def key(r):
        return r[station],r[stream],r[start]
    curves=defaultdict(list)
    for r in read(folder/(prefix+'_curves.csv')):
        t=int(r['elapsed_seconds'])
        if t>=0:
            d=float(r['depth_cm' if mad else 'raw_depth_cm'])
            curves[key(r)].append((t,d))
    events={}
    for r in read(folder/(prefix+'_events.csv')):
        if r['status']!='scored':
            continue
        site,series,stamp=key(r)
        eid='|'.join((site,series,stamp))
        assert eid not in events
        points=sorted(curves.pop(key(r)))
        assert points[0][0]==0 and len(set(t for t,_ in points))==len(points)
        assert all(0<=t<=2100 and math.isfinite(d) and d>=0 for t,d in points)
        cross=next((i for i,(_,d) in enumerate(points) if d>=10.16),None)
        positive=cross is not None
        last_low=points[cross-1][0] if positive else None
        assert positive==bool(int(r['positive']))
        events[eid]=dict(dataset=tag,site=site,name=r.get('name',site),start=stamp,
                         zero_gap=int(r['since_zero_sec']),positive=positive,last_low=last_low,
                         cross=points[cross][0] if positive else None,
                         annotated_review=bool(int(r['review'])),
                         urgent=bool(int(r['urgent' if mad else 'urgent_truth'])),points=points)
    assert not curves
    return events


def look(prefix,minute):
    """Accept only observations already received, in seconds/cm from the first wet reading."""
    assert all(t<=60*minute for t,_ in prefix)
    if len(prefix)<2:
        return None
    t,d=prefix[-1]
    if d<=1 or max(h for _,h in prefix)>=10.16 or minute*60-t>180:
        return None
    if minute==8 and t<=300:
        return None
    depth=d/2.54
    rate=(d-prefix[0][1])/2.54/(t/60)
    age=minute-t/60
    gaps=[(b[0]-a[0])/60 for a,b in zip(prefix,prefix[1:])]
    eta=(4-depth)/rate-age-median(gaps) if rate>0 else math.inf
    return depth+(35-minute)*max(0,rate),[depth,rate,age,len(prefix)],eta


def make_plan(e,rules,tidal):
    plans={}
    outlines=[look([(t,d) for t,d in e['points'] if t<=m*60],m) for m in (5,8)]
    first,later=outlines
    assert first is not None
    assert (later is not None)==e['annotated_review']
    can5=e['positive'] and e['last_low']>=600
    assert e['urgent']==(can5 and (later is None or e['last_low']<780))
    base=rules['base']
    h=base['cutoffs'][int(tidal)]
    def score(stage,projection):
        p=base['params'][stage]
        return p['bias']+p['tide']*int(tidal)+p['depth']*projection
    raw=score(0,first[0])
    gate=rules['gate']
    gate_score=sum(w*x for w,x in zip(gate['w'],[*first[1],int(tidal)]))+gate['b']
    allow={'frozen':False,'first_only':False,'relax_all':not tidal,
           'learned':not tidal and gate_score>gate['cut'],
           'eta':not tidal and 5<=first[2]<8}
    for rule in RULES:
        a=raw+math.log(2)*allow[rule]
        b=score(1,later[0]) if later is not None and rule!='first_only' else -math.inf
        plans[rule]=(a,b)
    return plans,allow,h,raw<h<=raw+math.log(2)


def decision(a,b,threshold):
    return 5 if a>=threshold else (8 if b>=threshold else None)


def timely(alarm,e):
    return bool(alarm is not None and e['positive'] and e['last_low']-alarm*60>=300)


def replay(events,model,scenario,rows,ledger):
    tidal=scenario=='assume_tidal'
    prepared={k:make_plan(e,model,tidal) for k,e in events.items()}
    for cohort in ('all','recent_zero'):
        keys=[k for k,e in events.items() if cohort=='all' or e['zero_gap']<=300]
        if not keys:
            continue
        neg=[k for k in keys if not events[k]['positive']]
        for mode in (['fixed','matched10'] if len(neg)>=20 else ['fixed']):
            ref={}
            for rule in RULES:
                values={k:prepared[k][0][rule] for k in keys}
                h=prepared[keys[0]][2]
                if mode=='matched10':
                    # Stable ordering among equal numerical scores, as in the NYC benchmark.
                    def rank(s,k):
                        return (round(s,8),hashlib.sha256(k.encode()).hexdigest())
                    values={k:tuple(rank(s,k) for s in p) for k,p in values.items()}
                    h=sorted((max(values[k]) for k in neg),reverse=True)[len(neg)//10-1]
                alarms={k:decision(*values[k],h) for k in keys}
                if rule=='frozen':
                    ref=alarms
                gains=losses=added_fp=saved_fp=hits=tp=fp=flagged=detected_urgent=0
                for k,a in alarms.items():
                    e=events[k];hit=timely(a,e);old=timely(ref[k],e);p=e['positive']
                    gains+=hit and not old;losses+=old and not hit
                    added_fp+=not p and a is not None and ref[k] is None
                    saved_fp+=not p and a is None and ref[k] is not None
                    hits+=hit;tp+=p and a is not None;fp+=not p and a is not None
                    gate=prepared[k][1][rule]
                    flagged+=gate;detected_urgent+=e['urgent'] and gate
                    if cohort=='all':
                        ledger.append(dict(dataset=e['dataset'],scenario=scenario,mode=mode,rule=rule,
                            event=k,site=e['site'],name=e['name'],start=e['start'],zero_gap=e['zero_gap'],
                            positive=int(p),review=int(e['annotated_review']),urgent=int(e['urgent']),
                            gate=int(gate),in_relaxation_band=int(prepared[k][3]),
                            alarm=a,reference_alarm=ref[k],timely=int(hit),last_low_s=e['last_low'],
                            crossing_s=e['cross'],lower_lead_s=e['last_low']-60*a if a and p else None))
                if mode=='matched10':
                    assert fp==len(neg)//10
                rows.append(dict(dataset=events[keys[0]]['dataset'],scenario=scenario,cohort=cohort,
                    mode=mode,rule=rule,n=len(keys),positive=len(keys)-len(neg),negative=len(neg),
                    urgent=sum(events[k]['urgent'] for k in keys),reviews=sum(events[k]['annotated_review'] for k in keys),
                    timely=hits,late=tp-hits,missed=len(keys)-len(neg)-tp,fp=fp,gained=gains,lost=losses,
                    added_fp=added_fp,saved_fp=saved_fp,flagged=flagged,flagged_urgent=detected_urgent))


def run(original,extension,out):
    model=json.loads((original/'nyc_locked_rules.json').read_text())
    rows=[];ledger=[]
    for path,tag,mad in [(original,'TW_existing',False),(original,'Madison',True),(extension,'TW_holdout',False)]:
        events=load(path,tag,mad)
        for scenario in (['inland'] if mad else ['assume_non_tidal','assume_tidal']):
            replay(events,model,scenario,rows,ledger)
    out.mkdir(parents=True,exist_ok=True)
    write(out/'metrics.csv',rows);write(out/'decisions.csv',ledger)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--original',type=Path,default=Path('inputs'))
    p.add_argument('--extension',type=Path,default=Path('extension'))
    p.add_argument('--out',type=Path,default=Path('results'))
    a=p.parse_args()
    run(a.original,a.extension,a.out)

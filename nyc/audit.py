"""Audit FloodNet NYC event exports and run a fixed-time, event-conditional pilot.
See README for input file names. Run from the directory containing the snapshots.
"""
import csv
import hashlib
import json
import math
from bisect import bisect
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

def read_csv(name):
    with open(name, newline='') as file:
        return list(csv.DictReader(file))

def quantiles(values):
    return np.round(np.quantile(list(values), [0,.1,.25,.5,.75,.9,1]),3).tolist()

def parse_date(value):
    return datetime.strptime(value, '%m/%d/%Y %I:%M:%S %p')

def conformal_score(values):
    values=np.sort(values)
    k=math.ceil(.9*(len(values)+1))
    return float(values[k-1]) if k<=len(values) else math.inf

def as_text(value):
    if isinstance(value,np.generic): return value.item()
    raise TypeError(type(value))

boundary=[datetime(2025,7,1),datetime(2026,1,1),datetime(2026,7,1)]
events=read_csv('events.csv')
sites={r['Sensor ID']:r for r in read_csv('sites.csv')}
counts=Counter()
gaps=[]
qc_examples=[]
n_prefix=defaultdict(list)
summary=defaultdict(list)
flags=Counter()
risks=defaultdict(Counter)
blocks=[]
year=Counter()
threshold_timing=defaultdict(list)
samples=[]
threshold_support=defaultdict(lambda:[[0,0] for _ in range(4)])
start_key='Flood Start Datetime (GMT)'
for row in sorted(events,key=lambda r:parse_date(r[start_key])):
    sensor=row['Sensor ID']
    site=sites[sensor]
    start=parse_date(row[start_key])
    end=parse_date(row['Flood End Datetime (GMT)'])
    year[start.year]+=1
    if not blocks or start-blocks[-1][1]>timedelta(hours=24):
        blocks.append([start,end])
    else:
        blocks[-1][1]=max(blocks[-1][1],end)
    block=len(blocks)-1
    t=json.loads(row['Time Series Depth Timestamps (seconds)'])
    d=json.loads(row['Time Series Depth Values (inches)'])
    assert len(t)==len(d) and len(t)>1 and all(math.isfinite(v) for v in t+d)
    delta=np.diff(t)
    assert min(delta)>=0
    gaps.extend(delta.tolist())

    peak=float(row['Maximum Flood Depth (inches)'])
    onset=float(row['Time to Maximum Flood Depth (minutes)'])
    duration=float(row['Total Duration (minutes)'])
    if onset>duration+.02:
        qc_examples.append(dict(site=sensor,start=str(start),duration=duration,official_peak_min=onset,profile_peak_min=t[d.index(max(d))]/60))
    flags['before_deployment_calendar_date']+=start.date()<datetime.strptime(site['Date Installed'],'%m/%d/%Y').date()
    summary['first_profile_peak_min'].append(t[d.index(max(d))]/60)
    summary['points'].append(len(t))
    summary['duration_min'].append(duration)
    summary['first_official_peak_min'].append(onset)
    summary['peak_inches'].append(peak)
    flags['peak_depth_diff_over_0.01']+=abs(max(d)-peak)>.010001
    flags['first_argmax_time_diff_over_1min']+=abs(t[d.index(max(d))]/60-onset)>1
    flags['nonzero_first_offset']+=t[0]!=0
    flags['end_diff_over_2s']+=abs(t[-1]-(end-start).total_seconds())>2
    flags['repeated_timestamp']+=min(delta)==0
    flags['official_peak_by_5min']+=onset<=5
    flags['official_peak_by_10min']+=onset<=10
    flags['official_peak_by_15min']+=onset<=15
    flags['any_gap_over_5min']+=max(delta)>300
    tide=int(site['Tidally Influenced']=='Yes')
    for h in [4,12,24]:
        risks[str(h)]['official']+=peak>=h
        risks[str(h)]['profile']+=max(d)>=h
        risks[str(h)]['disagree']+=(peak>=h)!=(max(d)>=h)
        risks[str(h)]['tidal_yes']+=tide and peak>=h
        crosses=[ti for ti,di in zip(t,d) if di>=h]
        if crosses: threshold_timing[str(h)].append(crosses[0]/60)
    for minutes in (5,10,15):
        n_prefix[minutes].append(bisect(t,60*minutes))
    wet=next((i for i,v in enumerate(d) if v>10/25.4),None)
    if wet is None: counts['no_wet']+=1;continue
    cut=t[wet]+300
    j=bisect(t,cut)
    last=j-1
    if cut-t[last]>180 or d[last]<=10/25.4:
        counts['stale_or_no_longer_wet']+=1;continue
    under4=max(d[:j])<4
    counts['issuable_below_4in' if under4 else 'already_at_4in']+=1
    horizon=cut+1800
    stop=bisect(t,horizon)
    future=d[j:stop]
    # Require observed support up to the end of the window or a recorded zero
    # at the event end. Use the observation gap bridging the issue time too.
    right=min(horizon,t[-1])
    checks=[t[last]]+t[j:stop]+[right]
    if not future or max(np.diff(checks))>300 or (right<horizon and d[-1]!=0):
        if under4: counts['future_insufficient']+=1
        continue
    which_fold=bisect(boundary,start)
    for h in (4,12,24):
        if max(d[:j])<h:
            threshold_support[str(h)][which_fold][0]+=1
            threshold_support[str(h)][which_fold][1]+=int(max(future)>=h)
    if not under4: continue
    slope=(d[last]-d[wet])/max((t[last]-t[wet])/60,1/60)
    age=(cut-t[last])/60
    height=site['Sensor Ground Height Above Local Low Point (inches)']
    x=[d[last],slope,d[wet],age,j-wet,tide,float(height or 0),int(not height)]
    target=max(future)
    crossing=next((idx for idx in range(j,stop) if d[idx]>=4),None)
    lead=(t[crossing]-cut)/60 if crossing is not None else 0
    lead_low=max(0,(t[crossing-1]-cut)/60) if crossing is not None else 0
    samples.append((x,target,bisect(boundary,start),sensor,block,lead,lead_low,start,start+timedelta(seconds=cut)))
assert not any(s<b<=e for s,e in blocks for b in boundary)
assert len({(r['Sensor ID'],r[start_key]) for r in events})==len(events)
ids=Counter(r['Sensor ID'] for r in events)
result=dict(events=len(events),sites=len(sites),event_sites=len(ids),matched_rows=sum(ids.values()),
    oldest=str(min(parse_date(r[start_key]) for r in events)), latest_start=str(max(parse_date(r[start_key]) for r in events)),
    latest_end=str(max(parse_date(r['Flood End Datetime (GMT)']) for r in events)),year=year,
    most_frequent=ids.most_common(5),tide_sites=Counter(r['Tidally Influenced'] for r in sites.values()),
    tide_events=Counter(sites[r['Sensor ID']]['Tidally Influenced'] for r in events),
    quantiles={k:quantiles(v) for k,v in summary.items()},n_points=sum(summary['points']),
    n_gaps=len(gaps),gap_seconds=quantiles(gaps),gap_gt120=sum(x>120 for x in gaps),gap_gt300=sum(x>300 for x in gaps),
    prefix_points={k:quantiles(v) for k,v in n_prefix.items()},
    first_threshold_min={k:quantiles(v) for k,v in threshold_timing.items()},
    at_risk_n_positive_by_threshold=threshold_support,invalid_peak_examples=qc_examples,flags=flags,risks=risks,n_blocks=len(blocks),selection=counts)
X=np.array([s[0] for s in samples]); depth=np.array([s[1] for s in samples]); y=(depth>=4).astype(int)
fold=np.array([s[2] for s in samples]); sensor=np.array([s[3] for s in samples])
block=np.array([s[4] for s in samples]); lead=np.array([s[5] for s in samples]); lead_low=np.array([s[6] for s in samples])
train,valid,cal,test=[fold==i for i in range(4)]
# Mask the entire target site. Count only prior reported wet observations
# within ten minutes, ignoring colocated replacements (<30 m). No event row
# from a neighbor never establishes dryness or uptime.
from bisect import bisect_left, bisect_right
from math import radians, sin, cos, atan2, sqrt
wet_times=defaultdict(list)
for row in events:
    origin=parse_date(row[start_key])
    ts=json.loads(row['Time Series Depth Timestamps (seconds)'])
    depths=json.loads(row['Time Series Depth Values (inches)'])
    wet_times[row['Sensor ID']].extend(origin+timedelta(seconds=tt) for tt,dd in zip(ts,depths) if dd>10/25.4)
for times in wet_times.values(): times.sort()
def distance_km(a,b):
    lat1,lon1=map(radians,[float(sites[a]['Latitude']),float(sites[a]['Longitude'])])
    lat2,lon2=map(radians,[float(sites[b]['Latitude']),float(sites[b]['Longitude'])])
    z=sin((lat2-lat1)/2)**2+cos(lat1)*cos(lat2)*sin((lon2-lon1)/2)**2
    return 12742*atan2(sqrt(z),sqrt(1-z))
neighbors={a:[(b,distance_km(a,b)) for b in wet_times if b!=a] for a in set(sensor)}
distances=[]
for sample in samples:
    site_id=sample[3]; issue=sample[8]
    nearby=[]
    for b,km in neighbors[site_id]:
        if not .03<=km<=3: continue
        times=wet_times[b]
        left=bisect_left(times,issue-timedelta(minutes=10))
        if left<bisect_right(times,issue): nearby.append(km)
    distances.append(min(nearby,default=999))
result['neighbor_support']={}
for name,mask in [('all',np.ones(len(y),dtype=bool)),('test',test),('test_nontidal',test&(X[:,5]==0))]:
    result['neighbor_support'][name]={str(km):dict(n=int(mask.sum()),with_wet_neighbor=int(sum(mask&(np.array(distances)<=km)))) for km in [1,3]}
result['splits']=[dict(n=int(f.sum()),pos=int(y[f].sum()),pos12=int((depth[f]>=12).sum()),blocks=len(set(block[f])),pos_blocks=len(set(block[f&(y==1)])),sites=len(set(sensor[f]))) for f in (train,valid,cal,test)]
def logistic(features):
    model=make_pipeline(StandardScaler(),LogisticRegression(max_iter=2000))
    model.fit(features[train],y[train])
    return model.decision_function(features),model.predict_proba(features)[:,1]
def calibrate(score):
    model=LogisticRegression(C=10,max_iter=2000)
    model.fit(score[cal,None],y[cal])
    return model.predict_proba(score[:,None])[:,1]
rich_score,rich=logistic(X)
level_score,level=logistic(X[:,:1])
slope_score,slope=logistic((X[:,0]+30*np.maximum(X[:,1],0))[:,None])
p_rich=calibrate(rich_score)
predictions={'training_rate':np.repeat(y[train].mean(),len(y)), 'depth_only':calibrate(level_score),
             'linear_extrapolation_score':calibrate(slope_score), 'all_features_uncal':rich, 'all_features_platt':p_rich}
def classification(mask,p):
    return dict(n=int(mask.sum()),pos=int(y[mask].sum()),AP=average_precision_score(y[mask],p[mask]),Brier=brier_score_loss(y[mask],p[mask]))
result['classification']={k:classification(test,v) for k,v in predictions.items()}
result['subgroups']={}
for name,mask in [('tidal',X[:,5]==1),('nontidal',X[:,5]==0),('new_to_training',~np.isin(sensor,sensor[train]))]:
    result['subgroups'][name]=classification(test&mask,p_rich)
# Compare pooled vs non-tidal-only training on the same non-tidal test events.
nt=X[:,5]==0
model=make_pipeline(StandardScaler(),LogisticRegression(max_iter=2000))
model.fit(X[train&nt],y[train&nt])
score_nt=model.decision_function(X)
sigmoid=LogisticRegression(C=10,max_iter=2000).fit(score_nt[cal&nt,None],y[cal&nt])
result['nontidal_training_ablation']=dict(
    splits=[dict(n=int(sum(mask&nt)),pos=int(sum(mask&nt&(y==1)))) for mask in (train,valid,cal,test)],
    nontidal_only=classification(test&nt,sigmoid.predict_proba(score_nt[:,None])[:,1]),
    depth_only=classification(test&nt,predictions['depth_only']),
    extrapolation=classification(test&nt,predictions['linear_extrapolation_score']),
    pooled=classification(test&nt,p_rich))
# Choose the threshold using the independent validation period, on raw model
# scores. Platt's monotone mapping does not change this alarm decision.
candidates=np.unique(rich_score[valid])
neg=valid&(y==0)
threshold=min(v for v in candidates if (rich_score[neg]>=v).mean()<=.15)
alarm=rich_score>=threshold
pos=test&(y==1)
tp=pos&alarm
result['alarm']=dict(tp=int(tp.sum()),fp=int(sum(test&(y==0)&alarm)),
     precision=y[test&alarm].mean(),recall=alarm[pos].mean(),FPR=alarm[test&(y==0)].mean(),
     lead_median=float(np.median(lead[tp])),conservative_lead_median=float(np.median(lead_low[tp])),
     conservative_lead_at_least_5min_recall=(tp&(lead_low>=5)).sum()/pos.sum())
# Cluster bootstrap compares paired model scores; clusters are temporal proxies.
rng=np.random.default_rng(72)
clusters=[np.flatnonzero(test&(block==b)) for b in np.unique(block[test])]
diff=[]
for _ in range(1200):
    idx=np.concatenate([clusters[i] for i in rng.integers(len(clusters),size=len(clusters))])
    if len(np.unique(y[idx]))<2: continue
    diff.append([average_precision_score(y[idx],p_rich[idx])-average_precision_score(y[idx],predictions['depth_only'][idx]),
        np.mean((predictions['depth_only'][idx]-y[idx])**2-(p_rich[idx]-y[idx])**2),
        average_precision_score(y[idx],p_rich[idx])-average_precision_score(y[idx],predictions['linear_extrapolation_score'][idx])])
result['bootstrap_AP_vs_depth_Brier_gain_vs_depth_AP_vs_extrapolation']=np.quantile(diff,[.025,.5,.975],axis=0).tolist()
# Compare two sparse readings (first wet & last available) with one reading.
# No membership/count features beyond the measurement protocol in this model.
def interval_metrics(mask,lo,hi):
    zz=depth[mask];l=lo[mask];u=hi[mask]
    return dict(n=int(mask.sum()),coverage=np.mean((zz>=l)&(zz<=u)),width=np.mean(u-l),
          interval_score=np.mean(u-l+20*(np.maximum(l-zz,0)+np.maximum(zz-u,0))))
result['intervals']={}
for name,columns in [('one_reading',[0]),('one_plus_static_age',[0,3,5,6,7]),('two_readings',[0,1,2,3,5,6,7])]:
    feats=X[:,columns]
    def forecast(q):
        model=GradientBoostingRegressor(loss='quantile',alpha=q,n_estimators=75,max_depth=2,min_samples_leaf=20,random_state=42)
        model.fit(feats[train],depth[train])
        return model.predict(feats)
    lower,upper=forecast(.05),forecast(.95)
    lo,hi=np.minimum(lower,upper),np.maximum(lower,upper)
    scores=np.maximum(lo-depth,depth-hi)
    global_q=max(0.,conformal_score(scores[cal]))
    group_q={i:max(0.,conformal_score(scores[cal&(X[:,5]==i)])) for i in (0,1)}
    result['intervals'][name]={}
    # Use a fixed training-only risk cut point and information available at issue.
    # The two-reading quantile model itself supplies this risk ordering.
    risk_bin=hi>=np.quantile(hi[train],.75)
    risk_q={b:max(0.,conformal_score(scores[cal&(risk_bin==b)])) for b in (False,True)}
    for label,adj in [('raw',0),('pooled',global_q),('tide_strata',np.array([group_q[i] for i in X[:,5]])),('risk_strata',np.where(risk_bin,risk_q[True],risk_q[False]))]:
        l=np.maximum(0,lo-adj);u=hi+adj
        result['intervals'][name][label]={k:interval_metrics(m,l,u) for k,m in [('all',test),('non_tidal',test&(X[:,5]==0)),('tidal',test&(X[:,5]==1)),('depth_ge_4',pos)]}
resid=conformal_score(np.abs(depth[cal]-X[cal,0]))
result['persistence_interval']=interval_metrics(test,np.maximum(0,X[:,0]-resid),X[:,0]+resid)
result['hashes']={f:hashlib.sha256(Path(f).read_bytes()).hexdigest() for f in ('events.csv','sites.csv')}
Path('audit_results.json').write_text(json.dumps(result,indent=2,default=as_text))

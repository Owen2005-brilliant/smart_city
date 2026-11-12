"""Frozen FloodNet detector. Run here with model.json, mad/*.csv, beaufort.csv and shenzhen_grid.npz."""
import bisect,csv,datetime as dt,json,math,statistics,hashlib
from collections import Counter
from pathlib import Path
import numpy as np
MODEL=json.loads(Path('model.json').read_text())
WET=10/25.4
ledger=[]
def first_pass(d,i,j,t,cut,stage,tide):
    last=j-1
    slope=(d[last]-d[i])/max((t[last]-t[i])/60,1/60)
    projected=d[last]+(30-3*stage)*max(0,slope)
    p=MODEL['params'][stage]
    return p['depth']*projected+p['tide']*tide+p['bias']>=MODEL['cutoffs'][tide]
def replay(t,d,i,tide,source,key):
    wet=t[i];cut=wet+300;h=cut+1800
    out={'source':source,'case':key,'first_wet_s':int(wet)}
    j=bisect.bisect_right(t,cut)
    if max(d[i:j])>=4:out['reason']='already_crossed';return out
    if cut-t[j-1]>180 or d[j-1]<=WET:out['reason']='stale_or_dry';return out
    if min(d[i:j])<=0:out['reason']='ended_before_issue';return out
    k=bisect.bisect_right(t,h)
    final=next((a+1 for a in range(j,k) if d[a]<=0),k)
    gap=[t[j-1]]+list(t[j:final])
    closed=final>j and d[final-1]<=0
    if not closed:gap.append(h)
    if final==j or (not closed and t[-1]<h) or max(np.diff(gap))>300:
        out['reason']='inadequate_future';return out
    first=first_pass(d,i,j,t,cut,0,tide)
    q=min(final,bisect.bisect_right(t,cut+180));ok=q>j and t[q-1]>=cut and cut+180-t[q-1]<=180 and d[q-1]>WET and max(d[j:q])<4 and min(d[j:q])>0
    alarm=0 if first else (3 if ok and first_pass(d,i,q,t,cut+180,1,tide) else None)
    hit=next((a for a in range(j,final) if d[a]>=4),None)
    lead=None if hit is None or alarm is None else max(0,(t[hit-1]-cut)/60-alarm)
    out.update(reason='scored',positive=hit is not None,alarm=alarm,review_available=bool(ok),timely=bool(lead is not None and lead>=5),lead=lead,peak=round(float(max(d[j:final])),4))
    return out
def ts(s):return dt.datetime.fromisoformat(s).timestamp()
def field(rows,name,flag):
    rows=sorted(rows)
    assert len(set(a for a,b in rows))==len(rows)
    t=[a for a,b in rows];d=[max(0,b) for a,b in rows]
    # Start only after 30 minutes with no wet readings, supported by observations no more than 12 minutes apart.
    lastwet=-math.inf; segment=t[0]
    for i in range(len(t)):
        if i and t[i]-t[i-1]>720:segment=t[i]
        if d[i]<=WET:continue
        if t[i]-max(lastwet,segment)>=1800:
            ledger.append(replay(t,d,i,flag,name,dt.datetime.fromtimestamp(t[i],dt.timezone.utc).isoformat()))
        lastwet=t[i]
    return {'valid_rows':len(t),'median_gap_sec':statistics.median(np.diff(t)),'first_utc':dt.datetime.fromtimestamp(t[0],dt.timezone.utc).isoformat(),'last_utc':dt.datetime.fromtimestamp(t[-1],dt.timezone.utc).isoformat(),'over_4in_rows':sum(x>=4 for x in d),'peak_inches':max(d)}
stats={}
B=list(csv.DictReader(open('beaufort.csv')))
stats['Beaufort']=field([(ts(x['date']),float(x['road_water_level_adj'])*12) for x in B if x['qa_qc_flag']=='FALSE' and x['road_water_level_adj']!='NA'],'Beaufort',1)
stats['Beaufort']['raw_rows']=len(B)
M=[x for f in sorted(Path('mad').glob('*.csv')) for x in csv.DictReader(f.open())]
stats['Madison']=field([(ts(x['time']),12*(float(x['value'])-3.9)) for x in M if x['unit_of_measure']=='ft' and x['value'] and not x['qualifier']],'Madison',0)
stats['Madison']['raw_rows']=len(M)
meters=np.load('shenzhen_grid.npz')['meters'];assert meters.shape==(360,25,25)
t=list(range(0,360*60,60))
grid=meters/.0254
stats['Shenzhen']={'scenario':'test/flood/location2/G1166_intensity_246','n_cells':625,'sample_shape':[360,1,500,500]}
for y in range(grid.shape[1]):
    for x in range(grid.shape[2]):
        d=grid[:,y,x];key=f'r{10+y*20}-c{10+x*20}'
        if not np.isfinite(d).all() or np.any(d<0):ledger.append(dict(source='Shenzhen',case=key,reason='invalid_cell'));continue
        wet=np.flatnonzero(d>WET)
        if len(wet)==0:ledger.append(dict(source='Shenzhen',case=key,reason='never_wet'));continue
        ledger.append(replay(t,d,int(wet[0]),0,'Shenzhen',key))
for name,o in stats.items():
    a=[r for r in ledger if r['source']==name];o['selection']=dict(Counter(r['reason'] for r in a));s=[r for r in a if r['reason']=='scored']
    o['n']=len(s);o['pos']=sum(r['positive'] for r in s);o['fp']=sum(not r['positive'] and r['alarm'] is not None for r in s);o['timely']=sum(r['timely'] for r in s)
    o['review_available']=sum(r['review_available'] for r in s);o['early_alarms']=sum(r['alarm']==0 for r in s);o['later_alarms']=sum(r['alarm']==3 for r in s)
    o['timely_first']=sum(r['timely'] and r['alarm']==0 for r in s);o['TP']=sum(r['positive'] and r['alarm'] is not None for r in s)
with open('case_ledger.csv','w') as f:
    w=csv.DictWriter(f,fieldnames=['source','case','first_wet_s','reason','positive','alarm','review_available','timely','lead','peak']);w.writeheader();w.writerows(ledger)
Path('external_results.json').write_text(json.dumps(stats,indent=2))
print(json.dumps(stats,indent=1))

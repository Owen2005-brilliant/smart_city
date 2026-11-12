from pathlib import Path
from collections import defaultdict,Counter
from datetime import datetime,timedelta
from bisect import bisect_right
import csv, io, zipfile, math,json,statistics
def save(name,rows,fields):
 with open(name,'w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
levels=defaultdict(dict);meta={}; counts=Counter()
for f in sorted(Path('tw').glob('*.zip')):
 with zipfile.ZipFile(f) as z:
  for n in z.namelist():
   with io.TextIOWrapper(z.open(n),encoding='utf-8-sig') as inp:
    for r in csv.DictReader(inp):
     counts['rows']+=1
     if r['PQ_unit']!='cm' or r['PQ_name'] not in ('水深','淹水深度'):continue
     counts['depth_rows']+=1
     if '路面' not in (r['PQ_fullname']+r['PQ_description']):continue
     counts['explicit_road_rows']+=1
     try:val=float(r['value']);t=int((datetime.fromisoformat(r['timestamp'])-datetime(1970,1,1)).total_seconds())
     except (ValueError,TypeError):continue
     if not math.isfinite(val) or val<0:continue
     if r['timestamp'][:7].replace('-','') != f.stem[-8:-2]:continue
     key=(r['station_id'],r['PQ_id'],f.stem[-8:-2]);a=levels[key]
     if t in a:
      counts['duplicate_keys']+=1
      if val!=a[t]:a[t]=None;counts['conflict_records']+=1
     else:a[t]=val
     meta[key]=(r['PQ_fullname'],r['PQ_description'])
events=[]; inventory=[]; gaps=Counter(); curves=[]
with open('sensors.csv',encoding='utf-8-sig') as f:
 lookup={(r['station_id'],r['PQ_id']):r for r in csv.DictReader(f)}
def ts(t):return (datetime(1970,1,1)+timedelta(seconds=t)).isoformat()
for k,a in sorted(levels.items()):
 rec=sorted((t,d) for t,d in a.items() if d is not None)
 if not rec:continue
 t,d=map(list,zip(*rec));diff=[b-a for a,b in zip(t,t[1:])]
 for i in range(1,len(t)):
  if d[i-1]>1 and d[i]>1:gaps[t[i]-t[i-1]]+=1
 inventory.append(dict(month=k[2],station=k[0],stream=k[1],lon=lookup.get(k[:2],{}).get('Longitude',''),lat=lookup.get(k[:2],{}).get('Latitude',''),name=meta[k][0],description=meta[k][1],n=len(t),median_gap_sec=statistics.median(diff) if diff else None,max_cm=max(d)))
 # First wet reading >1 cm after a documented zero. For restart require a confirmed zero,
 # so transmission outages cannot manufacture extra events. Keep last pre-wet gap for quality.
 last_zero=None;idle=True
 for i,v in enumerate(d):
  if v==0:last_zero=i;idle=True
  if v<=1 or not idle:continue
  idle=False
  if last_zero is None:continue
  start=t[i];cut=start+300;end=start+2100
  j=bisect_right(t,cut);stop=bisect_right(t,end)
  dry=next((z for z in range(i+1,stop) if d[z]==0),None)
  status='scored';pos=None;early=None;urgent=None;review=None
  if dry is not None and t[dry]<=cut:status='dry_by_first_look'
  elif max(d[i:j])>=10.16:status='crossed_by_first_look'
  elif j-i<2 or cut-t[j-1]>180 or d[j-1]<=1:status='no_fresh_second_wet_reading'
  else:
   boundary=dry+1 if dry is not None else stop
   support=t[j-1:boundary]+([] if dry is not None else [end])
   if j>=boundary or (t[-1]<end and dry is None) or max((b-a for a,b in zip(support,support[1:])),default=0)>300:status='incomplete_future'
   else:
    crossing=next((z for z in range(j,boundary) if d[z]>=10.16),None)
    pos=int(crossing is not None)
    review_ids=[z for z in range(j,boundary) if t[z]<=start+480]
    review=int(bool(review_ids) and max(d[z] for z in review_ids)<10.16 and d[review_ids[-1]]>1)
    early=int(pos and t[crossing-1]-cut>=300)
    urgent=int(early and (not review or t[crossing-1]-(start+480)<300))
  if status=='scored':
   for ix in range(max(i-1,0),boundary):
    curves.append(dict(station=k[0],stream=k[1],start=ts(start),elapsed_seconds=t[ix]-start,raw_depth_cm=d[ix]))
  events.append(dict(station=k[0],stream=k[1],name=meta[k][0],start=ts(start),prewet_gap_sec=start-t[i-1],since_zero_sec=start-t[last_zero],status=status,positive=pos,timely_possible=early,review=review,urgent_truth=urgent))
scored=[e for e in events if e['status']=='scored']
def pack(es):
 return dict(n=len(es),positive=sum(e['positive'] for e in es),urgent=sum(e['urgent_truth'] for e in es),review_possible=sum(e['review'] for e in es))
res=dict(files=len(list(Path('tw').glob('*.zip'))),counts=dict(counts),stations=len(set(r['station'] for r in inventory)),streams=len(set(r['stream'] for r in inventory)),month_streams=len(inventory),wet_to_wet_interval_counts=gaps.most_common(10),events=len(events),reasons=dict(Counter(e['status'] for e in events)),scored=pack(scored),recent_zero_5min=pack([e for e in scored if e['since_zero_sec']<=300]),streams_with_4in=len(set(r['stream'] for r in inventory if r['max_cm']>=10.16)),recent_observation_5min=pack([e for e in scored if e['prewet_gap_sec']<=300]),recent_zero_with_review=pack([e for e in scored if e['since_zero_sec']<=300 and e['review']]),both_looks_possible=pack([e for e in scored if e['review']]),urgent_late=sum(e['urgent_truth'] and e['review'] for e in scored),monthly={m:pack([e for e in scored if e['start'].startswith(m)]) for m in ('2023-08','2023-09')})
save('tw_curves.csv',curves,list(curves[0]));save('tw_streams.csv',inventory,list(inventory[0]));save('tw_events.csv',events,list(events[0]));Path('tw_summary.json').write_text(json.dumps(res,indent=2));print(res)

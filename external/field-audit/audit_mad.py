"""Check Madison road-relative depth from foot-valued USGS station series."""
from datetime import datetime,timezone
from pathlib import Path
from bisect import bisect_right
from collections import Counter
import csv,json,math,statistics
def write(name,rows,fields):
 with open(name,'w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
sites=json.load(open('mad_sites.json'));manifest=json.load(open('mad_manifest.json'))
events=[];summary=[];curves=[]
for s in sites:
 sid=s['id']
 files=[Path('mad')/(sid+'_'+m['month']+'.csv') for m in manifest if m['site']==sid]
 if not files:continue
 records={};raw=0;skip=Counter()
 for f in sorted(files):
  with f.open() as inp:
   for r in csv.DictReader(inp):
    raw+=1
    if r['unit_of_measure']!='ft' or not r['value'] or r['qualifier']:skip['unusable']+=1;continue
    val=float(r['value'])
    if not math.isfinite(val):skip['invalid']+=1;continue
    stamp=int(datetime.fromisoformat(r['time']).timestamp())
    if stamp in records and val!=records[stamp]:records[stamp]=None;skip['conflict']+=1
    else:records[stamp]=val
 rd=sorted((t,max(0,(v-s['threshold_ft'])*30.48)) for t,v in records.items() if v is not None)
 if not rd:summary.append(dict(site=sid,name=s['name'],raw=raw,valid=0));continue
 t,d=map(list,zip(*rd));idle=True;last_zero=None
 for i,value in enumerate(d):
  if value==0:last_zero=i;idle=True
  if value<=1 or not idle:continue
  idle=False
  if last_zero is None:continue
  st=t[i];cut=st+300;end=st+2100;j=bisect_right(t,cut);stop=bisect_right(t,end)
  dry=next((z for z in range(i+1,stop) if d[z]==0),None)
  status='scored';pos=review=urgent=None
  if dry is not None and t[dry]<=cut:status='dry_by_first_look'
  elif max(d[i:j])>=10.16:status='crossed_by_first_look'
  elif j-i<2 or cut-t[j-1]>180 or d[j-1]<=1:status='no_fresh_second_wet_reading'
  else:
   b=dry+1 if dry is not None else stop
   support=t[j-1:b]+([] if dry is not None else [end])
   if j>=b or (t[-1]<end and dry is None) or max((y-x for x,y in zip(support,support[1:])),default=0)>300:status='incomplete_future'
   else:
    cross=next((z for z in range(j,b) if d[z]>=10.16),None);pos=int(cross is not None)
    nxt=[z for z in range(j,b) if t[z]<=st+480]
    review=int(bool(nxt) and max(d[z] for z in nxt)<10.16 and d[nxt[-1]]>1)
    urgent=int(pos and t[cross-1]-cut>=300 and (not review or t[cross-1]-(st+480)<300))
    for ix in range(i-1,b):curves.append(dict(site=sid,start_utc=datetime.fromtimestamp(st,timezone.utc).isoformat(),elapsed_seconds=t[ix]-st,depth_cm=d[ix]))
  events.append(dict(site=sid,start_utc=datetime.fromtimestamp(st,timezone.utc).isoformat(),status=status,positive=pos,review=review,urgent=urgent,since_zero_sec=st-t[last_zero]))
 summary.append(dict(site=sid,name=s['name'],raw=raw,valid=len(d),road_threshold_ft=s['threshold_ft'],median_gap_seconds=statistics.median(y-x for x,y in zip(t,t[1:])),max_depth_cm=max(d),conflicts=skip['conflict'],above_4in=sum(v>=10.16 for v in d)))
write('mad_inventory.csv',summary,['site','name','raw','valid','road_threshold_ft','median_gap_seconds','max_depth_cm','conflicts','above_4in'])
write('mad_events.csv',events,['site','start_utc','status','positive','review','urgent','since_zero_sec'])
write('mad_curves.csv',curves,['site','start_utc','elapsed_seconds','depth_cm'])
es=[r for r in events if r['status']=='scored']
result=dict(sites=len(summary),sites_with_values=sum(bool(r['valid']) for r in summary),raw=sum(r['raw'] for r in summary),valid=sum(r['valid'] for r in summary),counts=dict(Counter(e['status'] for e in events)),n=len(es),pos=sum(e['positive'] for e in es),reviews=sum(e['review'] for e in es),urgent=sum(e['urgent'] for e in es),close_zero=sum(e['since_zero_sec']<=300 for e in es))
Path('mad_summary.json').write_text(json.dumps(result,indent=2));print(result)

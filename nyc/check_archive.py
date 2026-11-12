"""Check two original Zenodo monthly CSV files; see README for download URLs."""
from collections import Counter, defaultdict
import csv
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import hashlib
from statistics import median

def load_csv(name):
    with open(name, newline='') as handle:
        return list(csv.DictReader(handle))

def utc(text):
    return datetime.strptime(text,'%m/%d/%Y %I:%M:%S %p').replace(tzinfo=timezone.utc)

events=load_csv('events.csv')
result={}
for name in ['oct20.csv','sep21.csv']:
    raw=load_csv(name)
    groups=defaultdict(list)
    depths=Counter()
    for row in raw:
        value=row['depth_proc_mm']
        depths['missing' if not value else 'zero' if float(value)==0 else 'nonzero']+=1
        groups[row['deployment_id']].append((datetime.fromisoformat(row['time']),float(value) if value else None,row['sensor_display_name'].removesuffix(' (RETIRED)')))
    by_site={}; gaps=[]; uptime=0
    for item in groups.values():
        item.sort()
        by_site[item[0][2]]=item
        dg=[(b[0]-a[0]).total_seconds() for a,b in zip(item,item[1:])]
        gaps+=dg
        uptime+=sum(x for x in dg if x<=360)
    month_start=min(a[0][0] for a in groups.values())
    pairs=[]
    for event in events:
        start=utc(event['Flood Start Datetime (GMT)'])
        if (start.year,start.month)!=(month_start.year,month_start.month):continue
        end=utc(event['Flood End Datetime (GMT)'])
        sensor=event['Sensor Name']
        if sensor not in by_site: continue
        part=[x for x in by_site[sensor] if start-timedelta(seconds=2)<=x[0]<=end+timedelta(seconds=2) and x[1] is not None]
        if not part:continue
        observed=max(v for _,v,_ in part)/25.4
        pairs.append(dict(sensor=sensor,start=str(start),points=len(part),archive_peak_in=round(observed,3),summary_peak_in=float(event['Maximum Flood Depth (inches)'])))
    result[name]=dict(rows=len(raw),deployments=len(groups),depths=depths,median_gap_seconds=round(median(gaps),2),
        hours_bridged_by_adjacent_pairs_le_360s=round(uptime/3600,1),pairs=pairs,sha256=hashlib.sha256(Path(name).read_bytes()).hexdigest())
Path('archive_results.json').write_text(json.dumps(result,indent=2))

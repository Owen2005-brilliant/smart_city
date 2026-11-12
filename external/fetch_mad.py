from pathlib import Path
import calendar,csv,io,subprocess,concurrent.futures
from urllib.parse import urlencode
def retrieve(start,end):
 q=urlencode(dict(monitoring_location_id='USGS-430548089213101',parameter_code='00065',datetime=start+'T00:00:00Z/'+end+'T23:59:59Z',limit=10000,f='csv',properties='time,value,unit_of_measure,approval_status,qualifier'))
 u='https://api.waterdata.usgs.gov/ogcapi/v0/collections/continuous/items?'+q
 text=subprocess.check_output(['curl','-fLsS','--retry','2','--max-time','75',u]).decode()
 return list(csv.DictReader(io.StringIO(text)))
def fetch(d):
 p=Path('mad')/(d+'.csv');p.parent.mkdir(exist_ok=True)
 if p.exists() and sum(1 for _ in csv.DictReader(p.open()))<10000:return
 y,m=map(int,d.split('-'));last=calendar.monthrange(y,m)[1];rows=[]
 for a,b in [(1,7),(8,14),(15,21),(22,last)]:
  week=retrieve(f'{d}-{a:02d}',f'{d}-{b:02d}');assert len(week)<10000;rows+=week
 with p.open('w') as f:
  w=csv.DictWriter(f,fieldnames=['x','y','time','value','unit_of_measure','approval_status','qualifier']);w.writeheader();w.writerows(rows)
 print(d,len(rows))
months=[f'{y}-{m:02d}' for y in (2025,2026) for m in range(1,13) if '2025-04'<=f'{y}-{m:02d}'<='2026-10']
with concurrent.futures.ThreadPoolExecutor(3) as pool:list(pool.map(fetch,months))

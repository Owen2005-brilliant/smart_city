import csv,json,math
from collections import defaultdict
from pathlib import Path
params=json.load(open('nyc_locked_rules.json'));models=params['base']['params'];h=params['base']['cutoffs'][0];g=params['gate']
curves=defaultdict(list)
for r in csv.DictReader(open('mad_curves.csv')):
 curves[r['site'],r['start_utc']].append((int(r['elapsed_seconds']),float(r['depth_cm'])/2.54))
rows=[]
for r in csv.DictReader(open('mad_events.csv')):
 if r['status']!='scored':continue
 pts=[(t,d) for t,d in curves[r['site'],r['start_utc']] if t>=0]
 def state(m):
  seen=[(t,d) for t,d in pts if t<=60*m]
  t,d=seen[-1];slope=(d-seen[0][1])/(t/60)
  x=(d,slope,m-t/60,len(seen),0)
  return models[int(m==8)]['depth']*(d+(35-m)*max(0,slope))+models[int(m==8)]['bias'],x
 score,x=state(5)
 flag=sum(w*v for w,v in zip(g['w'],x))+g['b']>g['cut']
 cross=next((i for i,(_,d) in enumerate(pts) if d>=4),None)
 assert (cross is not None)==bool(int(r['positive']))
 last_low=pts[cross-1][0] if cross is not None else None
 for rule,allow in [('frozen',False),('learned',flag),('relax_all',True)]:
  minute=5 if score+math.log(2)*allow>=h else None
  if minute is None and int(r['review']) and state(8)[0]>=h:minute=8
  rows.append(dict(site=r['site'],start=r['start_utc'],since_zero_sec=r['since_zero_sec'],rule=rule,gate=int(flag),positive=int(r['positive']),alarm=minute,timely=int(last_low is not None and minute is not None and last_low-60*minute>=300)))
with open('mad_replay.csv','w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=['site','start','since_zero_sec','rule','gate','positive','alarm','timely']);w.writeheader();w.writerows(rows)
summary={}
for rule in ('frozen','learned','relax_all'):
 a=[r for r in rows if r['rule']==rule]
 summary[rule]=dict(n=len(a),pos=sum(r['positive'] for r in a),timely=sum(r['timely'] for r in a),fp=sum(r['alarm'] is not None and not r['positive'] for r in a),alarms=sum(r['alarm'] is not None for r in a))
Path('mad_replay_summary.json').write_text(json.dumps(summary,indent=2));print(summary)

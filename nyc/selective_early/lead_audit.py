"""Describe alternative lead-time requirements without changing any alarms."""
from pathlib import Path
import csv
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from first_look import write_rows

def audit(folder):
    with (folder/'event_decisions.csv').open() as f:
        rows=list(csv.DictReader(f))
    out=[];attribution=[]
    for period in ['main','prior']:
        for mode in ['matched','frozen']:
            subset=[r for r in rows if r['period']==period and r['mode']==mode]
            for metric in [0,1,3,5,8,10]:
                for field in ['base_min','candidate_min']:
                    positive=[r for r in subset if r['positive']=='True']
                    n=sum(r[field]!='inf' and (metric==0 or float(r['low'])-float(r[field])>=metric) for r in positive)
                    out.append(dict(period=period,mode=mode,policy=field,required_minutes=metric,
                                    pos=len(positive),hits=n))
            for r in subset:
                if float(r['candidate_min'])==2:
                    positive=r['positive']=='True'
                    attribution.append(dict(period=period,mode=mode,key=r['key'],positive=positive,
                           lower_lead_min=max(0,float(r['low'])-2) if positive else '',
                           timely=positive and float(r['low'])-2>=5,
                           base_was_timely=positive and float(r['low'])-float(r['base_min'])>=5))
    write_rows(folder/'lead_profile.csv',out)
    write_rows(folder/'early_alarm_breakdown.csv',attribution)
if __name__=='__main__':audit(Path('result'))

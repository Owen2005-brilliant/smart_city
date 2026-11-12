"""One-command independent evaluation. No training imports. No Git writes."""
import argparse
import csv
from collections import Counter
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
from urllib.parse import urlencode

from scoring import DEPTH, TIME, evaluate, window

HERE=Path(__file__).resolve().parent
NYC=HERE.parent
START='Flood Start Datetime (GMT)'
END='Flood End Datetime (GMT)'
ID='Sensor ID'
TIDE='Tidally Influenced'
FMT='%m/%d/%Y %I:%M:%S %p'
DATASETS={'events':'aq7i-eu5q','sites':'kb2e-tjy3'}

def sha(data):
    return hashlib.sha256(data).hexdigest()

def read_csv(data,required):
    reader=csv.DictReader(io.StringIO(data.decode('utf-8-sig'),newline=''))
    if not set(required)<=set(reader.fieldnames or []):
        raise ValueError('CSV columns missing: '+str(required))
    rows=list(reader)
    if not rows: raise ValueError('Empty full-table export; no results produced')
    if any(None in row or None in row.values() for row in rows):
        raise ValueError('Malformed full-table CSV')
    return rows

def get(url):
    return subprocess.check_output(['curl','--fail','--silent','--show-error','--location',
        '--retry','2','--connect-timeout','15','--max-time','120',url])

def official(name):
    dataset=DATASETS[name]
    root='https://data.cityofnewyork.us/'
    meta=root+'api/views/'+dataset
    version=json.loads(get(meta))['rowsUpdatedAt']
    raw=get(meta+'/rows.csv?accessType=DOWNLOAD')
    count_url=root+'resource/'+dataset+'.json?'+urlencode({'$select':'count(*) as n'})
    expected=int(json.loads(get(count_url))[0]['n'])
    size=len(read_csv(raw,[ID]))
    if size!=expected or version!=json.loads(get(meta))['rowsUpdatedAt']:
        raise RuntimeError(f'{name} changed during export or row count mismatch; retry')
    return raw,dict(dataset=dataset,rows=size,rows_updated_at=version)

def stamp(value):
    return datetime.strptime(value,FMT).replace(tzinfo=timezone.utc)

def keyed(rows):
    by_key={}
    for row in rows:
        key=(row[ID].strip(),stamp(row[START]))
        if not key[0]:raise ValueError('Missing sensor ID')
        if key in by_key and by_key[key]!=row:
            raise ValueError(f'Conflicting duplicate event key {key}; inspect source')
        by_key[key]=row
    return by_key

def site_map(rows):
    sites={}
    for row in rows:
        key=row[ID].strip();value=row[TIDE].strip().lower()
        if not key or (key in sites and sites[key]!=value):
            raise ValueError(f'Missing or conflicting deployment ID {key}')
        sites[key]=value
    return sites

def metrics(rows):
    n=len(rows);pos=sum(r['positive'] for r in rows);neg=n-pos
    timely=sum(r['timely'] for r in rows)
    tp=sum(r['positive'] and r['alarm_min'] is not None for r in rows)
    fp=sum(not r['positive'] and r['alarm_min'] is not None for r in rows)
    return dict(n=n,positive=pos,negative=neg,timely=timely,late=tp-timely,
                missed=pos-tp,false_alarm=fp,timely_recall=timely/pos if pos else None,
                event_fpr=fp/neg if neg else None)

def audit(raw_events,raw_sites,base_events,base_sites,config,cutoff,as_of):
    latest=keyed(read_csv(raw_events,[ID,START,END,DEPTH,TIME]))
    old=keyed(read_csv(base_events,[ID,START,END,DEPTH,TIME]))
    sites=site_map(read_csv(raw_sites,[ID,TIDE]))
    known=site_map(read_csv(base_sites,[ID,TIDE]))
    added=[]; predictions=[]
    old_ends={(key[0],stamp(row[END])) for key,row in old.items()}
    counts=Counter()
    for (sid,start),row in sorted(latest.items(),key=lambda kv:(kv[0][1],kv[0][0])):
        if (sid,start) in old:
            counts['historical_revised' if row!=old[(sid,start)] else 'historical_same']+=1
            continue
        key={'sensor_id':sid,'start_utc':start.isoformat()}
        rec={**key,'status':'','site_type':'','product':'','common':''}
        added.append(rec)
        if start<cutoff:
            rec['status']='pre_freeze_backfill';continue
        try:
            end=stamp(row[END])
        except ValueError:
            rec['status']='invalid_or_unfinished_event';continue
        if (sid,end) in old_ends:
            rec['status']='possible_historical_revision';continue
        if end<start or end>as_of:
            rec['status']='invalid_or_unfinished_event';continue
        t=known.get(sid,sites.get(sid))
        if t not in ('yes','no') or (sid in known and sid in sites and known[sid]!=sites[sid]):
            rec['status']='unresolved_site_metadata';continue
        rec['site_type']='tidal' if t=='yes' else 'non_tidal'
        try:
            series=window(row)
        except (ValueError,TypeError) as err:
            rec['status']='invalid_profile';rec['product']=str(err);continue
        scores,excluded=evaluate(series,t=='yes',config)
        rec.update(status='evaluated',product=excluded.get('product','scored'),common=excluded.get('common','scored'))
        for s in scores: predictions.append({**key,'new_deployment':sid not in known,**s})
    counts.update(r['status'] for r in added)
    counts['old_keys_absent']=len(old.keys()-latest.keys())
    groups={}
    policies={'product':['deployed_5_8','single_raw_extrapolation'],
              'common':['deployed_5_8','study_5_8','study_2_5','study_selective','single_raw_extrapolation']}
    for cohort,names in policies.items():
        groups[cohort]={}
        for policy in names:
            subset=[s for s in predictions if s['policy']==policy and s['cohort']==cohort]
            groups[cohort][policy]={g:metrics([s for s in subset if keep(s)]) for g,keep in [
                ('all',lambda s:True),('tidal',lambda s:s['tidal']),('non_tidal',lambda s:not s['tidal']),
                ('new_deployment',lambda s:s['new_deployment'])]}
    nnew=sum(stamp(row[START])>=cutoff for k,row in latest.items() if k not in old)
    status='no_new_events' if not nnew else ('no_scorable_events' if not predictions else 'scored')
    return dict(status=status,post_cutoff_new_keys=nnew,feed_rows=len(latest),audit_counts=dict(counts),
                latest_start_utc=max(k[1] for k in latest).isoformat(),metrics=groups),added,predictions

def save_csv(path,names,rows):
    with path.open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=names);writer.writeheader();writer.writerows(rows)

def persist(root,report,raw_events,raw_sites,added,predictions,version):
    root.mkdir(exist_ok=True,parents=True)
    names=('events','sites')
    hashes={name:sha(data) for name,data in zip(names,(raw_events,raw_sites))}
    # The same export can become eligible later if it includes a future end time.
    identity=[version,report['source'],hashes,report['freeze_digest'],added]
    fingerprint=sha(json.dumps(identity,sort_keys=True).encode())[:24]
    dest=root/fingerprint
    with tempfile.TemporaryDirectory(dir=root) as tmp:
        package=Path(tmp)/'complete';package.mkdir()
        for name,data in zip(names,(raw_events,raw_sites)):(package/(name+'.csv')).write_bytes(data)
        report['input_sha256']=hashes
        save_csv(package/'cohort.csv',['sensor_id','start_utc','status','site_type','product','common'],added)
        save_csv(package/'predictions.csv',['sensor_id','start_utc','new_deployment','cohort','policy','tidal','positive','alarm_min','lower_lead_min','timely'],predictions)
        (package/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        try:package.rename(dest)
        except OSError:
            if not dest.is_dir():raise
            # Same immutable inputs: confirm every archived file; never append or silently overwrite.
            if not all((dest/f.name).is_file() and (dest/f.name).read_bytes()==f.read_bytes()
                       for f in package.iterdir() if f.name!='report.json'):
                raise ValueError('Previous snapshot incomplete or damaged: '+str(dest))
            previous=json.loads((dest/'report.json').read_text())
            if any(previous.get(k)!=v for k,v in report.items() if k not in ('retrieved_utc','feed_version')):
                raise ValueError('Previous report differs for identical input; inspect '+str(dest))
    return dest

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--local-dir',type=Path,help='Replay complete events.csv and sites.csv offline')
    parser.add_argument('--out',type=Path,default=HERE/'runs')
    args=parser.parse_args()
    lockdata=(HERE/'freeze.json').read_bytes();lock=json.loads(lockdata)
    for path,digest in lock['sha256'].items():
        if sha((NYC/path).read_bytes())!=digest:raise ValueError('Frozen file changed: '+path)
    config=json.loads((HERE/'frozen_models.json').read_text())
    if args.local_dir:
        raw=[(args.local_dir/(name+'.csv')).read_bytes() for name in DATASETS]
        versions={}; source='offline'
    else:
        inputs={name:official(name) for name in DATASETS}
        raw=[inputs[name][0] for name in DATASETS]
        versions={name:inputs[name][1] for name in DATASETS};source='official'
    now=datetime.now(timezone.utc)
    summary,added,predictions=audit(*raw,(NYC/'events.csv').read_bytes(),(NYC/'sites.csv').read_bytes(),
        config,datetime.fromisoformat(lock['eligible_start_utc']),now)
    summary.update(rule=lock['version'],eligible_start_utc=lock['eligible_start_utc'],
        freeze_digest=sha(lockdata),retrieved_utc=now.isoformat(),source=source,feed_version=versions)
    dest=persist(args.out/source,summary,*raw,added,predictions,lock['version'])
    label={'no_new_events':'暂无冻结后新增事件','no_scorable_events':'有新记录，暂无可评分事件','scored':'已评分'}
    print(f"{label[summary['status']]}；来源 {source}，总计 {summary['feed_rows']} 个唯一事件。")
    stats=summary['metrics']['product']['deployed_5_8']['all']
    print(f"新增 {summary['post_cutoff_new_keys']}，默认规则可评分 {stats['n']}，及时命中 {stats['timely']}/{stats['positive']}，误报 {stats['false_alarm']}/{stats['negative']}（分母为零时比率未定义）。")
    print(dest.resolve())
if __name__=='__main__':main()

"""Offline regression + prospective selection checks. Run via unittest discovery."""
import csv
from datetime import datetime,timezone
import io
import json
from pathlib import Path
import tempfile
import unittest
from validate_new import (HERE,NYC,START,END,ID,TIDE,TIME,DEPTH,audit,keyed,metrics,persist,read_csv)
from scoring import evaluate,window

UTC=timezone.utc
class FrozenValidation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config=json.loads((HERE/'frozen_models.json').read_text())
        cls.ev=(NYC/'events.csv').read_bytes();cls.sites=(NYC/'sites.csv').read_bytes()
        cls.cut=datetime(2026,11,13,tzinfo=UTC)
    def test_historical_metrics_and_decisions(self):
        known={r[ID]:r[TIDE]=='Yes' for r in read_csv(self.sites,[ID,TIDE])}
        groups={}
        truth={(r['key'],r['policy']):r['time'] for r in csv.DictReader(
            io.StringIO((NYC/'result/decisions.csv').read_text())) if r['period']=='main' and r['mode']=='frozen'}
        selective={r['key']:r['candidate_min'] for r in csv.DictReader(
            io.StringIO((NYC/'selective_early/result/event_decisions.csv').read_text())) if r['period']=='main' and r['mode']=='frozen'}
        for (sid,start),r in keyed(read_csv(self.ev,[ID])).items():
            if start.date().isoformat()<'2026-07-01':continue
            output,_=evaluate(window(r),known[sid],self.config)
            for rec in output:
                groups.setdefault((rec['cohort'],rec['policy']),[]).append(rec)
                key=sid+'|'+start.replace(tzinfo=None).isoformat()
                if rec['policy'] in ('study_2_5','study_5_8'):
                    policy='2+3' if rec['policy']=='study_2_5' else '5+3'
                    self.assertEqual(str(rec['alarm_min'] or ''),truth[(key,policy)])
                if rec['policy']=='study_selective' and not known[sid]:
                    self.assertEqual(float(rec['alarm_min'] or 'inf'),float(selective[key]))
        m=metrics(groups['product','deployed_5_8'])
        self.assertEqual((m['n'],m['positive'],m['timely'],m['false_alarm']),(859,192,97,121))
        m=metrics(groups['common','study_selective'])
        self.assertEqual((m['n'],m['positive'],m['timely'],m['false_alarm']),(985,296,103,128))
    def test_increment_revision_duplicates_and_exclusions(self):
        base=read_csv(self.ev,[ID]); current=[dict(base[0])]
        current[0]['Sensor Name']='revised display name'
        def row(date,hours,sid=None,depth=None):
            r=dict(base[0]);r[START]=date+' '+hours+':00:00 AM';r[END]=date+' '+hours+':35:00 AM'
            r[TIME]=json.dumps([60*i for i in range(36)])
            r[DEPTH]=json.dumps(depth or [0.5+0.2*i for i in range(36)])
            if sid:r[ID]=sid
            return r
        good=row('11/13/2026','01')
        current.extend([good,good.copy(),row('11/12/2026','03'),row('11/13/2026','04','unknown'),
                        row('11/13/2026','05',depth=[5]*36),row('11/13/2026','06',depth=[0]*36)])
        def export(rows):
            buf=io.StringIO();w=csv.DictWriter(buf,fieldnames=base[0].keys());w.writeheader();w.writerows(rows)
            return buf.getvalue().encode()
        now=datetime(2026,11,14,tzinfo=UTC)
        s,ledger,pred=audit(export(current),self.sites,self.ev,self.sites,self.config,self.cut,now)
        self.assertEqual(s['post_cutoff_new_keys'],4)
        self.assertEqual(s['audit_counts']['historical_revised'],1)
        self.assertEqual(s['audit_counts']['pre_freeze_backfill'],1)
        self.assertEqual(s['audit_counts']['unresolved_site_metadata'],1)
        self.assertEqual(s['metrics']['product']['deployed_5_8']['all']['n'],1)
        self.assertEqual(s['metrics']['common']['deployed_5_8']['all']['n'],2)
        self.assertIsNone(s['metrics']['product']['deployed_5_8']['all']['event_fpr'])
        with tempfile.TemporaryDirectory() as tmp:
            s.update(freeze_digest='test',source='offline')
            args=(Path(tmp),s,export(current),self.sites,ledger,pred,'test')
            self.assertEqual(persist(*args),persist(*args))
        bad=good.copy();bad[DEPTH]='[]'
        with self.assertRaisesRegex(ValueError,'duplicate'):
            audit(export([good,bad]),self.sites,self.ev,self.sites,self.config,self.cut,now)
    def test_no_new_is_not_zero_percent(self):
        s,_,pred=audit(self.ev,self.sites,self.ev,self.sites,self.config,self.cut,self.cut)
        self.assertEqual(s['status'],'no_new_events');self.assertFalse(pred)
        self.assertIsNone(s['metrics']['product']['deployed_5_8']['all']['timely_recall'])

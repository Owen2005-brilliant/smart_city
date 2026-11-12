"""Frozen event-conditional evaluation. Times are seconds after first wet reading."""
from bisect import bisect_right
import json
import math

WET = 10 / 25.4
HORIZON = 35 * 60
DEPTH = 'Time Series Depth Values (inches)'
TIME = 'Time Series Depth Timestamps (seconds)'


def window(row):
    t, d = json.loads(row[TIME]), json.loads(row[DEPTH])
    if not isinstance(t, list) or not isinstance(d, list) or not t or len(t) != len(d):
        raise ValueError('unaligned/empty depth and timestamp arrays')
    if not all(type(x) in (int, float) and math.isfinite(x) and x >= 0 for x in t+d):
        raise ValueError('invalid second or depth')
    if any(b < a for a, b in zip(t, t[1:])):
        raise ValueError('timestamps go backwards')
    wet = next((i for i, value in enumerate(d) if value > WET), None)
    if wet is None:
        return None
    return [s-t[wet] for s in t[wet:]], d[wet:]


def support(t, d, minute):
    cut = 60 * minute
    j = bisect_right(t, cut)
    stop = bisect_right(t, HORIZON)
    if stop == j or (t[-1] < HORIZON and d[-1] != 0):
        return False
    points = [t[j-1] if j else 0, *t[j:stop], min(HORIZON, t[-1])]
    return all(b-a <= 300 for a, b in zip(points, points[1:]))


def look(t, d, minute):
    i = bisect_right(t, 60*minute)-1
    if max(d[:i+1]) >= 4:
        return None, 'already_crossed'
    if t[i] == 0 or 60*minute-t[i] > 180 or d[i] <= WET:
        return None, 'insufficient_recent_wet_readings'
    slope = (d[i]-d[0])/(t[i]/60)
    return (d[i]+(35-minute)*max(0., slope), t[i], slope), 'ok'


def score(model, stage, projection, tide):
    p = model['params'][stage]
    raw = p['bias'] + p['depth']*projection + p['tide']*int(tide)
    return round(raw, model['precision']) if 'precision' in model else raw


def alarm(model, first, second, tide, threshold=None):
    if first is None:
        return None
    minutes = model.get('schedule', [5, 8])
    h = model['cutoffs'][int(tide)] if threshold is None else threshold
    if score(model, 0, first[0], tide) >= h:
        return minutes[0]
    if second is not None and second[1] > 60*minutes[0] and score(model, 1, second[0], tide) >= h:
        return minutes[1]
    return None


def evaluate(series, tide, config):
    if series is None:
        return [], {'product':'no_wet', 'common':'no_wet'}
    t, d = series
    a2, _ = look(t, d, 2)
    a5, reason = look(t, d, 5)
    a8, _ = look(t, d, 8)
    cross = next((i for i in range(bisect_right(t,HORIZON)) if d[i]>=4), None)
    last_low = t[cross-1]/60 if cross is not None and cross>0 else -1
    entries = []
    exclusions = {}
    def add(cohort, policy, minute):
        positive = cross is not None
        lead = max(0., last_low-minute) if positive and minute is not None else None
        entries.append(dict(cohort=cohort, policy=policy, tidal=tide, positive=positive,
                            alarm_min=minute, lower_lead_min=lead, timely=lead is not None and lead>=5))

    if a5 is None:
        exclusions['product'] = reason
    elif not support(t,d,5):
        exclusions['product'] = 'inadequate_future'
    else:
        add('product','deployed_5_8',alarm(config['product'],a5,a8,tide))
        add('product','single_raw_extrapolation',5 if a5[0]>=4 else None)

    # Common cohort intentionally retains already-crossed or unissuable windows.
    if (t[-1]<HORIZON and d[-1]!=0) or any(b-a>300 for a,b in zip(t, t[1:]) if b<=HORIZON) or min(HORIZON,t[-1])-t[bisect_right(t,HORIZON)-1]>300:
        exclusions['common']='inadequate_future'
    else:
        # Compare the deployed product and experimental policies on the SAME events.
        add('common','deployed_5_8',alarm(config['product'],a5,a8,tide))
        late,early = config['comparison']['5+3'],config['comparison']['2+3']
        add('common','study_5_8',alarm(late,a5,a8,tide))
        add('common','study_2_5',alarm(early,a2,a5,tide))
        add('common','single_raw_extrapolation',5 if a5 is not None and a5[0]>=4 else None)
        cuts=config['reserve_2pct'][int(tide)]
        urgent=not tide and a2 is not None and a2[2]>0 and score(early,0,a2[0],tide)>=cuts['early']
        add('common','study_selective',2 if urgent else alarm(late,a5,a8,tide,cuts['later']))
    return entries, exclusions

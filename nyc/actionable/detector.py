"""Score a prefix of one street flooding event, without training dependencies."""
import argparse
import json
import math
from pathlib import Path

WET = 10 / 25.4
NAMES = ['depth', 'first_depth', 'mean_rate', 'last_rate', 'minute',
         'single_reading', 'tidal', 'tidal_depth', 'tidal_mean_rate']


def slope(a, b):
    minutes = (b[0] - a[0]) / 60
    return max(-2., min(2., (b[1] - a[1]) / minutes)) if minutes else 0.


def samples(points):
    """Yield (elapsed minutes, distinct-time wet-prefix readings). Input in seconds/inches."""
    first = previous = None
    history = []
    for seconds, depth in points:
        if not all(math.isfinite(v) and v >= 0 for v in (seconds, depth)):
            raise ValueError('Expected finite nonnegative seconds and depth')
        if previous is not None and seconds < previous:
            raise ValueError('Out-of-order reading')
        previous = seconds
        if first is None:
            if depth <= WET:
                continue
            first = seconds
        elapsed = seconds - first
        if elapsed > 480 or depth >= 4:
            break
        if history and elapsed == history[-1][0]:
            continue
        history.append((elapsed, depth))
        if depth > WET:
            yield elapsed/60, tuple(history)


def features(prefix, minute, tidal):
    first, last = prefix[0], prefix[-1]
    rate = slope(first, last)
    recent = slope(prefix[-2], last) if len(prefix) > 1 else 0.
    return [last[1], first[1], rate, recent, minute, int(len(prefix)==1),
            int(tidal), tidal*last[1], tidal*rate]


def score(row, model):
    return model['intercept'] + sum(w*x for w,x in zip(model['weights'],row))


def detect(points, tidal, model):
    threshold = model['thresholds'][int(tidal)]
    for minute, history in samples(points):
        if score(features(history, minute, tidal), model) >= threshold:
            return minute
    return None


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--readings', required=True, help='JSON array of [seconds, inches]')
    parser.add_argument('--site', choices=['tidal','non_tidal'], required=True)
    parser.add_argument('--model', type=Path, default=Path(__file__).with_name('candidate.json'))
    args = parser.parse_args()
    minute = detect(json.loads(args.readings), args.site=='tidal', json.loads(args.model.read_text()))
    print(json.dumps({'first_alarm_minute_after_first_wet':minute}))

"""Export the past-only non-tidal gate from the previous exploratory experiment."""
import os,sys,json
from pathlib import Path
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
out=Path('nyc_locked_rules.json').resolve()
os.chdir(sys.argv[1]);v={};exec(Path('validate.py').read_text().split('def run(period,cuts):')[0],v)
dates=v['dates'];fit=dates<'2025-07-01';cal=(dates>='2025-07-01')&(dates<'2026-01-01')&v['nt']&~v['y']
X=v['X'][:,[0,1,3,4,5]]
target=v['y']&(v['lead']>=5)&((v['lead']<8)|~v['ok'])
model=make_pipeline(StandardScaler(),LogisticRegression(max_iter=2000)).fit(X[fit],target[fit])
sc,logit=[c for _,c in model.steps];w=logit.coef_[0]/sc.scale_
out.write_text(json.dumps(dict(base=json.loads(Path('model.json').read_text()),gate=dict(w=w.tolist(),b=float(logit.intercept_[0]-w@sc.mean_),cut=float(np.quantile(model.decision_function(X[cal]),.90)))),indent=2))

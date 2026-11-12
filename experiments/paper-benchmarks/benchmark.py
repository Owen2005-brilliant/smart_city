"""Compare published stopping strategies on the same NYC event cohort."""
import argparse
from bisect import bisect_right
import csv
import json
import math
import os
from pathlib import Path

import numpy as np
import torch
from torch import nn
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.model_selection import GroupKFold, cross_val_predict
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import FunctionTransformer
from aeon.classification.early_classification import TEASER


def flatten(x):
    return x.reshape(len(x),-1)


def forest():
    return make_pipeline(FunctionTransformer(flatten),
                         RandomForestClassifier(n_estimators=100,min_samples_leaf=10,
                                                random_state=42,n_jobs=1))


class PrefixForest(ClassifierMixin,BaseEstimator):
    # aeon 1.3.0 supplies full series to its out-of-fold hook. Keep precisely
    # the prefix length used by the fitted stage, including in its inner CV.
    _save_train_predictions=True

    def __init__(self,groups,random_state=42):
        self.groups=groups
        self.random_state=random_state

    def fit(self,x,y):
        self.width_=x.shape[2]
        self.model_=forest().fit(x,y)
        self.classes_=self.model_.classes_
        return self

    def predict_proba(self,x):
        return self.model_.predict_proba(x[:,:,:self.width_])

    def _get_train_probs(self,x,y):
        folds=GroupKFold(n_splits=5)
        return cross_val_predict(forest(),x[:,:,:self.width_],y,cv=folds,
                                 groups=self.groups,method='predict_proba')


def get_sequences(v):
    sequences, targets = [], []
    for r in v['cohort']:
        wet=r['cut']-300
        times, depths=r['t'],r['d']
        frames=[]
        for minute in range(9):
            index=bisect_right(times,wet+60*minute)-1
            assert times[index]<=wet+60*minute
            frames.append([depths[index], (wet+60*minute-times[index])/60, r['x'][5]])
        # Invalid second looks cannot make decisions or supply post-crossing readings.
        if not r['eligible']:
            frames[6:]=[frames[5]]*3
        sequences.append(frames)
        peaks=[]
        for stage in (5,8):
            spans=zip((stage,15,25),(15,25,35))
            peaks.append([max(depths[bisect_right(times,wet+60*a):bisect_right(times,wet+60*b)],default=0)
                          for a,b in spans])
        targets.append(peaks)
    return np.array(sequences).transpose(0,2,1).copy(),np.array(targets)


class AttentionLSTM(nn.Module):
    def __init__(self):
        super().__init__()
        self.lstm=nn.LSTM(3,12,batch_first=True)
        self.attention=nn.Linear(12,1)
        self.output=nn.Linear(12,3)

    def forward(self,x):
        states,_=self.lstm(x)
        weights=self.attention(states).softmax(dim=1)
        return self.output((states*weights).sum(dim=1))


def predicted_peaks(x,targets,positive_train):
    x=x.transpose(0,2,1)
    subset=x[positive_train]
    mean,sd=subset.mean(axis=(0,1)),subset.std(axis=(0,1))
    inputs=torch.tensor((x-mean)/np.maximum(sd,1.e-6),dtype=torch.float32)
    y=torch.tensor(np.log1p(targets[positive_train]),dtype=torch.float32)
    train_x=inputs[positive_train]
    forecasts=[]
    for seed in (17,29,41):
        torch.manual_seed(seed)
        net=AttentionLSTM()
        opt=torch.optim.Adam(net.parameters(),lr=.01)
        for _ in range(30):
            for batch in torch.randperm(len(y)).split(64):
                loss=nn.functional.mse_loss(net(train_x[batch]),y[batch])
                opt.zero_grad()
                loss.backward()
                opt.step()
        with torch.no_grad():
            forecasts.append(torch.expm1(net(inputs)).clamp_min(0).numpy())
    return np.mean(forecasts,axis=0).max(axis=1)


def paper_models(x,targets,y,train,ok,blocks):
    # 3, 6 and 9 frames count the first wet minute as frame 1.
    early=TEASER(estimator=PrefixForest(blocks[train]),classification_points=[3,6,9],random_state=42,n_jobs=1)
    early.fit(x[train],y[train].astype(int))
    p5,stop5=early.predict_proba(x[:,:,:6])
    p8,stop8=early.predict_proba(x)
    assert stop8.all() and early._consecutive_predictions==2
    assert np.all(early.state_info[:,3]>=6)
    assert np.allclose(p5[stop5],p8[stop5])
    labels,_=early.predict(x)
    native=np.where((labels==1)&stop5,0.,np.where((labels==1)&~stop5&ok,3.,np.inf))
    raw=[e.predict_proba(x[:,:,:m])[:,1] for e,m in zip(early._estimators[1:],(6,9))]
    teaser=(np.where(stop5,p5[:,1],-np.inf),np.where(~stop5 & ok,p8[:,1],-np.inf))
    two_stage=[]
    rf_only=[]
    for i,length in enumerate((6,9)):
        fit=train if i==0 else train&ok
        points=x[:,:,:length]
        model=forest().fit(points[fit],y[fit])
        p=model.predict_proba(points)[:,1]
        peak=predicted_peaks(points,targets[:,i],fit&y)
        allowed=np.ones(len(x),bool) if i==0 else ok
        assert np.isfinite(peak).all() and np.isfinite(p).all()
        two_stage.append(np.where(allowed,p*peak,-np.inf))
        rf_only.append(np.where(allowed,p,-np.inf))
    return {'TEASER':teaser,'TEASER_without_stop':(raw[0],np.where(ok,raw[1],-np.inf)),
            'Taiwan_single_site_proxy':two_stage, 'Taiwan_RF_only':rf_only},stop5,native


def decisions(v,plan,cal,group,mode):
    a,b=plan
    if mode=='matched':
        a,b=v['ranked'](a),v['ranked'](b)
        h=v['threshold'](np.maximum(a,b),np.flatnonzero(cal&group),.10)
    elif mode=='historical':
        neg=np.sort(np.maximum(a,b)[cal & group & ~v['y']])[::-1]
        h=np.nextafter(neg[int(len(neg)*.1)],np.inf)
    else:
        h=.5
    when=np.where((a>=h)&np.isfinite(a),0.,np.where((b>=h)&np.isfinite(b),3.,np.inf))
    return when


def count(y,lead,when,mask):
    pos=y[mask]
    alert=np.isfinite(when[mask])
    tp=int(sum(alert&pos))
    timely=int(sum(pos&(lead[mask]-when[mask]>=5)))
    return dict(n=len(pos),pos=int(sum(pos)),fp=int(sum(alert&~pos)),timely=timely,
                late=tp-timely,missed=int(sum(pos))-tp)


def resampled_timely(scores,indices,y,lead):
    a,b=scores[0][indices],scores[1][indices]
    pos=y[indices]
    neg=np.maximum(a,b)[~pos]
    k=int(.1*len(neg))
    if not k or not pos.any():
        return np.nan
    h=np.partition(neg,len(neg)-k)[-k]
    if not np.isfinite(h):
        return np.nan
    # Bootstrap may include the same storm twice. Share boundary ties to
    # maintain exactly k false alarms in expectation in each resample.
    share=(k-np.sum(neg>h))/np.sum(neg==h)
    def timely(first,later):
        delays=np.where(first,0,np.where(later,3,np.inf))
        return np.sum(pos&(lead[indices]-delays>=5))/np.sum(pos)
    return share*timely(a>=h,b>=h)+(1-share)*timely(a>h,b>h)


def uncertainty(plans,v,test,period):
    scores={name:tuple(v['ranked'](s) for s in pair) for name,pair in plans.items()}
    output=[]
    for group,mask in [('all',test),('non_tidal',test&v['nt'])]:
        ids=np.flatnonzero(mask)
        chunks=[ids[v['blocks'][ids]==b] for b in np.unique(v['blocks'][ids])]
        rng=np.random.default_rng(42)
        diffs={k:[] for k in plans if k!='ours'}
        for _ in range(1000):
            ix=np.concatenate([chunks[j] for j in rng.integers(len(chunks),size=len(chunks))])
            vals={k:resampled_timely(p,ix,v['y'],v['lead']) for k,p in scores.items()}
            for name in diffs:
                delta=vals['ours']-vals[name]
                if np.isfinite(delta):
                    diffs[name].append(delta)
        for name,d in diffs.items():
            lo,hi=np.quantile(d,[.025,.975])
            output.append(dict(period=period,group=group,reference='ours',against=name,
                               low_pp=100*lo,high_pp=100*hi,replicates=len(d),blocks=len(chunks)))
    return output


def run(nyc,out):
    torch.set_num_threads(1)
    os.chdir(nyc)
    v={}
    exec(Path('validate.py').read_text().split('def run(period,cuts):')[0],v)
    x,targets=get_sequences(v)
    ok,y,dates,lead,nt=[v[k] for k in ('ok','y','dates','lead','nt')]
    all_sites=np.ones(len(y),bool)
    rows,ledger,diagnostics,intervals=[],[],{},[]
    for period,start_val,start_test,end_test,end_train in [
        ('main','2026-01-01','2026-07-01','2027-01-01','2025-07-01'),
        ('prior','2025-07-01','2026-01-01','2026-07-01','2025-01-01')]:
        train,valid,test=dates<end_train,(dates>=start_val)&(dates<start_test),(dates>=start_test)&(dates<end_test)
        for a,b in [(train,valid),(train,test),(valid,test)]:
            assert not set(v['blocks'][a])&set(v['blocks'][b])
        scores=[]
        for stage,delay in [('X',0),('X2',3)]:
            features=v[stage]
            projection=features[:,0]+(30-delay)*np.maximum(0,features[:,1])
            scores.append(v['odds'](np.column_stack((projection,features[:,5])),train if not delay else train&ok,delay))
        assert all(np.isfinite(s).all() for s in scores)
        first,second=scores
        second=np.where(ok,second,-np.inf)
        plans={'ours':(first-math.log(2),second),'EFAS_any':(first,second),
               'EFAS_both':(np.full(len(y),-np.inf),np.minimum(first,second))}
        quality={}
        for name in ('ours','EFAS_any'):
            when=decisions(v,plans[name],valid,nt,'matched')
            quality[name]=count(y,lead,when,valid&nt)['timely']
        use_any=quality['EFAS_any']>quality['ours']
        plans['val_selected_non_tidal']=(np.where(nt & use_any,first,plans['ours'][0]),second)
        models,stop5,native=paper_models(x,targets,y,train,ok,v['blocks'])
        plans.update(models)
        diagnostics[period]=dict(validation_non_tidal_timely=quality,selected_non_tidal='any' if use_any else 'ours',
                                 teaser_stop5=int(sum(test&stop5)),test_n=int(sum(test)))
        for name,p in plans.items():
            for group,group_mask in [('all',all_sites),('non_tidal',nt)]:
                mask=test&group_mask
                for mode in (['matched','historical','native'] if name=='TEASER' else ['matched','historical']):
                    when=native if mode=='native' else decisions(v,p,test if mode=='matched' else valid,group_mask,mode)
                    stats=count(y,lead,when,mask)
                    if mode=='matched':
                        assert stats['fp']==int(.10*(stats['n']-stats['pos'])),(name,stats)
                    entry=dict(period=period,group=group,method=name,mode=mode)
                    rows.append(dict(**entry,**stats))
                    for i in np.flatnonzero(mask):
                        ledger.append(dict(**entry,event=v['cohort'][i]['key'],positive=int(y[i]),
                                           block=v['blocks'][i],alarm_min=(int(5+when[i]) if np.isfinite(when[i]) else ''),
                                           timely=int(y[i] and lead[i]-when[i]>=5)))
        intervals.extend(uncertainty(plans,v,test,period))
        print(period,diagnostics[period],flush=True)
    out.mkdir(exist_ok=True,parents=True)
    for fname,items in [('metrics.csv',rows),('decisions.csv',ledger),('paired_intervals.csv',intervals)]:
        with (out/fname).open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=items[0]);writer.writeheader();writer.writerows(items)
    (out/'diagnostics.json').write_text(json.dumps(diagnostics,indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('nyc',type=Path)
    parser.add_argument('--out',type=Path,default=Path('result'))
    args=parser.parse_args()
    run(args.nyc.resolve(),args.out.resolve())

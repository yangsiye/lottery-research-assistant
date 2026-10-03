from __future__ import annotations
import numpy as np
from scipy.stats import t as student_t
from .models import build_dataset, fit_models, FEATURE_KEYS

NAMES = ('uniform', 'bayes', 'logistic', 'hist_gb')
PROTOCOL = 'walk-forward-v1.5-refit30-holdout20pct-block10-bonferroni6'


def probability_metrics(y, p, pick_n):
    y = np.asarray(y, dtype=float)
    p = np.clip(np.asarray(p, dtype=float), 1e-6, 1-1e-6)
    hits = float(y[np.argsort(p, kind='stable')[-pick_n:]].sum())
    return {'brier':float(np.mean((p-y)**2)),
            'logloss':float(-np.mean(y*np.log(p)+(1-y)*np.log(1-p))),
            'topk_recall':hits/pick_n, 'mean_hits':hits,
            'calibration_gap':float(abs(p.mean()-y.mean()))}


def _summary(values):
    return {**{k:float(np.mean([v[k] for v in values])) for k in values[0] if k!='index'},
            'n_eval':len(values)} if values else None


def _evidence(model, baseline):
    """Paired loss uncertainty uses non-overlapping blocks, six comparisons total.

    This is a conservative approximate test, not proof of predictive power.
    The protocol and model hyperparameters are fixed before the holdout.
    """
    result = {}
    for key in ('brier','logloss'):
        delta=np.array([m[key]-b[key] for m,b in zip(model,baseline)])
        blocks=np.array([delta[i:i+10].mean() for i in range(0,len(delta)-9,10)])
        upper=None
        if len(blocks)>=3:
            se=float(blocks.std(ddof=1)/np.sqrt(len(blocks)))
            upper=float(blocks.mean()+student_t.ppf(1-.05/6,len(blocks)-1)*se)
        result[key]={'mean_delta':float(delta.mean()) if len(delta) else None,
                     'upper_confidence_bound':upper,'blocks':len(blocks)}
    result['stable']=bool(len(model)>=30 and all(
        np.mean([m[k]-b[k] for m,b in zip(model[-w:],baseline[-w:])])<0
        for w in (10,30,50,100) if len(model)>=w for k in ('brier','logloss')))
    result['passed']=result['stable'] and all(
        result[k]['upper_confidence_bound'] is not None and
        result[k]['upper_confidence_bound']<0 for k in ('brier','logloss'))
    return result


def walk_forward_metrics(draw_sets,max_n,pick_n,min_train=80,step=1,refit_every=30):
    acc={n:[] for n in NAMES}
    n=len(draw_sets)
    if n<=min_train:
        return {name:None for name in NAMES}
    # Build each row once from <t; training slices exclude the current and all future draws.
    X,y=build_dataset(draw_sets,max_n,pick_n)
    holdout_start=max(min_train, n-max(30,int((n-min_train)*.20)))
    validation_count=holdout_start-min_train
    models={}; last_fit=-refit_every
    for idx in range(min_train,n,step):
        cutoff=(idx-40)*max_n
        if idx-last_fit>=refit_every or idx==holdout_start:
            models=fit_models(draw_sets[:idx],max_n,pick_n,dataset=(X[:cutoff],y[:cutoff]))
            last_fit=idx
        current=X[cutoff:cutoff+max_n]
        target=y[cutoff:cutoff+max_n]
        probs={'uniform':np.full(max_n,pick_n/max_n),
               'bayes':current[:,FEATURE_KEYS.index('bayes_mean')]}
        probs.update({name:model.predict_proba(current)[:,1] for name,model in models.items()})
        for name,p in probs.items():
            acc[name].append({'index':idx,**probability_metrics(target,p,pick_n)})
    out={}
    for name,values in acc.items():
        if not values:
            out[name]=None; continue
        valid=[v for v in values if v['index']<holdout_start]
        hold=[v for v in values if v['index']>=holdout_start]
        base_valid=[v for v in acc['uniform'] if v['index']<holdout_start]
        base_hold=[v for v in acc['uniform'] if v['index']>=holdout_start]
        evidence_valid=_evidence(valid,base_valid)
        evidence_hold=_evidence(hold,base_hold)
        out[name]={**_summary(values),'validation':_summary(valid),'holdout':_summary(hold),
                   'rolling':{str(w):_summary(values[-w:]) for w in (10,30,50,100) if len(values)>=w},
                   'validation_evidence':evidence_valid,'holdout_evidence':evidence_hold,
                   'eligible':name=='uniform' or (validation_count>=30 and evidence_valid['passed'] and evidence_hold['passed']),
                   'protocol':PROTOCOL,'holdout_start_index':holdout_start,'refit_every':refit_every}
    return out


def weights_from_metrics(metrics, min_uniform_weight=0.6):
    # Selection uses validation; untouched holdout can veto, never increase weights.
    weights={}
    base=metrics.get('uniform')
    if not base or not base.get('validation'):
        return {'uniform':1.0}
    for name,m in metrics.items():
        if name=='uniform' or not m or not m.get('eligible'): continue
        gain=(base['validation']['brier']-m['validation']['brier'])/base['validation']['brier']
        weights[name]=min(.05,max(0.,gain))
    weights={k:v for k,v in weights.items() if v>0}
    weights['uniform']=1-sum(weights.values())
    return weights


def walk_forward_scores(draw_sets,max_n,pick_n,min_train=80,step=1):
    return {k:v['brier'] if v else None for k,v in walk_forward_metrics(draw_sets,max_n,pick_n,min_train,step).items()}


def weights_from_scores(scores):
    # Legacy Brier-only values carry no holdout/stability evidence.
    return {'uniform':1.0}

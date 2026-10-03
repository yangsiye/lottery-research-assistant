from __future__ import annotations
import math
import numpy as np
from sklearn.metrics import brier_score_loss, log_loss
from .models import fit_models, predict_probs


def _topk_recall(y, p, k):
    idx=np.argsort(p)[-k:]
    return float(y[idx].sum()/max(1,y.sum()))


def walk_forward_metrics(draw_sets,max_n,pick_n,min_train=80,step=1):
    names=['uniform','bayes','logistic','hist_gb']
    acc={n:{'brier':[],'logloss':[],'topk':[],'hits':[]} for n in names}
    if len(draw_sets)<=min_train:
        return {n:None for n in names}

    for t in range(min_train,len(draw_sets),step):
        models=fit_models(draw_sets[:t],max_n,pick_n)
        probs=predict_probs(models,draw_sets[:t],max_n,pick_n)
        y=np.array([1 if n in draw_sets[t] else 0 for n in range(1,max_n+1)],dtype=int)
        for name,p in probs.items():
            p=np.clip(np.asarray(p,float),1e-6,1-1e-6)
            acc[name]['brier'].append(brier_score_loss(y,p))
            acc[name]['logloss'].append(log_loss(y,p,labels=[0,1]))
            acc[name]['topk'].append(_topk_recall(y,p,pick_n))
            idx=np.argsort(p)[-pick_n:]
            acc[name]['hits'].append(float(y[idx].sum()))

    out={}
    for name,d in acc.items():
        if not d['brier']:
            out[name]=None
            continue
        out[name]={
            'brier':float(np.mean(d['brier'])),
            'logloss':float(np.mean(d['logloss'])),
            'topk_recall':float(np.mean(d['topk'])),
            'mean_hits':float(np.mean(d['hits'])),
            'n_eval':len(d['brier']),
        }
    return out


def walk_forward_scores(draw_sets,max_n,pick_n,min_train=80,step=1):
    """Backward-compatible Brier-only view."""
    metrics=walk_forward_metrics(draw_sets,max_n,pick_n,min_train,step)
    return {k:(v['brier'] if v else None) for k,v in metrics.items()}


def weights_from_metrics(metrics, min_uniform_weight=0.15):
    """Build conservative ensemble weights from OOS metrics only.

    Directional folklore never gets a manual weight. A model earns weight only by
    improving calibrated probability loss vs uniform; top-k is a small tie-breaker.
    """
    valid={k:v for k,v in metrics.items() if v}
    if not valid or 'uniform' not in valid:
        return {'uniform':1.0}
    base=valid['uniform']
    raw={'uniform':min_uniform_weight}
    for name,m in valid.items():
        if name=='uniform':
            continue
        brier_gain=max(0.0,(base['brier']-m['brier'])/max(base['brier'],1e-12))
        log_gain=max(0.0,(base['logloss']-m['logloss'])/max(base['logloss'],1e-12))
        top_gain=max(0.0,m['topk_recall']-base['topk_recall'])
        # Calibration dominates; ranking contributes only lightly.
        raw[name]=0.55*brier_gain+0.35*log_gain+0.10*top_gain
    # Models with no measured gain do not receive ceremonial weight.
    if sum(v for k,v in raw.items() if k!='uniform') <= 1e-12:
        return {'uniform':1.0}
    s=sum(raw.values())
    return {k:v/s for k,v in raw.items() if v>0}


def weights_from_scores(scores):
    """Compatibility helper for legacy callers."""
    valid={k:v for k,v in scores.items() if v is not None and v>0}
    if not valid:
        return {'uniform':1.0}
    baseline=valid.get('uniform',min(valid.values()))
    raw={'uniform':0.20}
    for k,v in valid.items():
        if k=='uniform':
            continue
        raw[k]=max(0.0,(baseline-v)/baseline)
    if sum(v for k,v in raw.items() if k!='uniform')<=1e-12:
        return {'uniform':1.0}
    s=sum(raw.values())
    return {k:v/s for k,v in raw.items() if v>0}

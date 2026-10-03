from __future__ import annotations
import json, math
from datetime import datetime, date
from .lifecycle import TZ, PUBLICATION_DEADLINE, digest
from .rules import draw_status, previous_draw_day
from .governance import record_training
from pathlib import Path
import numpy as np
from .db import DB
from .fetchers import fetch_ssq, fetch_dlt
from .models import fit_models, predict_probs
from .backtest import walk_forward_metrics, weights_from_metrics
from .features import historical_structure, structure_features

ROOT=Path(__file__).resolve().parents[1]
CONFIG=json.loads((ROOT/'config/lotteries.json').read_text())
DB_PATH=ROOT/'data/lottery.db'
VERSION='unified-v1.5-frozen-oos-holdout'


def sync(lottery,periods=200):
    rows=fetch_ssq(periods) if lottery=='ssq' else fetch_dlt(periods)
    db=DB(DB_PATH)
    for r in rows:
        db.upsert_draw(lottery,r['issue'],r['draw_date'],r['main'],r['bonus'],r['source'],r.get('prize_data'))
    db.log('sync',{'rows':len(rows),'source':rows[0]['source'],'version':VERSION},lottery)
    return len(rows)


def _zone(draws,key):
    return [set(d[key]) for d in draws]


def _ensemble(probs,weights):
    arr=np.zeros_like(next(iter(probs.values())),dtype=float)
    used=0.0
    for k,w in weights.items():
        if k in probs:
            arr += w*probs[k]
            used += w
    if used==0:
        return probs['uniform']
    return arr/used


def train_zone(draws,key,max_n,pick_n):
    sets=_zone(draws,key)
    metrics=walk_forward_metrics(sets,max_n,pick_n)
    weights=weights_from_metrics(metrics)
    models=fit_models(sets,max_n,pick_n)
    probs=predict_probs(models,sets,max_n,pick_n)
    return _ensemble(probs,weights),metrics,weights,probs


def _soft_structure_score(nums, history_stats, max_n, previous_numbers=None):
    """Structural profile is a low-weight plausibility tie-breaker only.

    It cannot veto candidates and therefore cannot encode contradictory hard rules.
    """
    f=structure_features(nums,max_n,previous_numbers)
    score=0.0; parts={}
    keys=(
        'sum','span','odd','big','consecutive_pairs','same_tail_pairs',
        'r0','r1','r2','zone1','zone2','zone3','prime','ac','repeat_prev','neighbor_prev'
    )
    for k in keys:
        if k not in history_stats:
            continue
        h=history_stats[k]
        x=f[k]
        sd=max(h['std'],1.0)
        closeness=math.exp(-abs(x-h['median'])/sd)
        parts[k]=round(closeness,3)
        score+=closeness
    return score/max(1,len(parts)),parts


def _sample_combo(probs,pick_n,rng):
    p=np.asarray(probs,float)
    p=np.maximum(p,1e-9)
    p=p/p.sum()
    return sorted(rng.choice(np.arange(1,len(p)+1),size=pick_n,replace=False,p=p).tolist())


def recommend(lottery,seed=None,candidates=5000,now=None,clock=None):
    if now is None and clock is None: clock=lambda:datetime.now(TZ)
    now=(now or datetime.now(TZ)).astimezone(TZ)
    target=now.date()
    if draw_status(lottery,target)['status']!='WAITING_DRAW':
        raise RuntimeError('当日不是可开奖日，不能发布推荐')
    db=DB(DB_PATH)
    existing=db.get_frozen_recommendation(lottery,target.isoformat())
    if existing:
        return existing
    if now.time().replace(tzinfo=None)>=PUBLICATION_DEADLINE:
        raise RuntimeError('已超过推荐发布时间，禁止事后补预测')
    draws=db.get_draws(lottery)[-500:]
    expected=previous_draw_day(lottery,target).isoformat()
    if not draws or draws[-1]['draw_date']!=expected:
        raise RuntimeError(f'数据未更新到上一开奖日 {expected}，停止推荐')
    if candidates<1:
        raise ValueError('candidates must be positive')
    if len(draws)<80:
        raise RuntimeError(f'Need at least 80 historical draws, found {len(draws)}. Run sync with a larger archive/import.')
    cfg=CONFIG[lottery]
    rng=np.random.default_rng(seed)

    # Main and bonus zones are independent engines but share one governance protocol.
    pm,mm,wm,models_main=train_zone(draws,'main_numbers',cfg['main_max'],cfg['main_pick'])
    pb,mb,wb,models_bonus=train_zone(draws,'bonus_numbers',cfg['bonus_max'],cfg['bonus_pick'])

    hist_main=historical_structure(draws,'main_numbers',cfg['main_max'])
    hist_bonus=historical_structure(draws,'bonus_numbers',cfg['bonus_max'])
    prev_main=draws[-1]['main_numbers']
    prev_bonus=draws[-1]['bonus_numbers']

    baseline_only=wm=={'uniform':1.0} and wb=={'uniform':1.0}
    best=None
    for _ in range(1 if baseline_only else candidates):
        main=_sample_combo(pm,cfg['main_pick'],rng)
        bonus=_sample_combo(pb,cfg['bonus_pick'],rng)
        ps=float(np.mean([pm[n-1] for n in main])+np.mean([pb[n-1] for n in bonus]))/2
        ss1,p1=_soft_structure_score(main,hist_main,cfg['main_max'],prev_main)
        ss2,p2=_soft_structure_score(bonus,hist_bonus,cfg['bonus_max'],prev_bonus)
        # Probability layer dominates; structure never becomes a hard filter.
        combined=ps if baseline_only else 0.90*ps+0.10*((ss1+ss2)/2)
        if best is None or combined>best[0]:
            best=(combined,main,bonus,ps,ss1,ss2,p1,p2)

    latest_issue=str(draws[-1]['issue'])
    issue=f'NEXT_AFTER_{latest_issue}'
    rationale={
        'architecture':'six-module unified system',
        'baseline_fallback':baseline_only,
        'score_is_probability':False,
        'governance':{
            'main':record_training(db,lottery,'main',mm,wm,draws,VERSION),
            'bonus':record_training(db,lottery,'bonus',mb,wb,draws,VERSION),
        },
        'main_weights':wm,
        'bonus_weights':wb,
        'main_oos_metrics':mm,
        'bonus_oos_metrics':mb,
        'structure_main':best[6],
        'structure_bonus':best[7],
        'policy':(
            'frequency/omission/hot/cold/repeat/neighbor/transition are observations or learned features; '
            'no contradictory directional rules are applied; structure is soft-only'
        ),
    }
    finished=(clock() if clock else now).astimezone(TZ)
    if finished.date()!=target or finished.time().replace(tzinfo=None)>=PUBLICATION_DEADLINE:
        raise RuntimeError('训练完成时已过发布时间，不发布、不冻结')
    now=finished
    prediction_id=db.add_prediction(lottery,issue,best[1],best[2],VERSION,best[0],rationale)
    payload={
        'prediction_id':prediction_id,
        'lottery':lottery,
        'basis_issue':latest_issue,
        'target_draw_date':target.isoformat(),
        'frozen_at':now.isoformat(),
        'main':best[1], 'bonus':best[2],
        'model_version':VERSION, 'model_score':best[0],
        'bet':{'type':'single','multiplier':1,'additional':False,'cost':2},
        'model_probabilities':{
            'main':{k:np.asarray(v).tolist() for k,v in models_main.items()},
            'bonus':{k:np.asarray(v).tolist() for k,v in models_bonus.items()},
        },
        'rationale':rationale,
    }
    db.freeze_prediction(prediction_id,digest(payload),payload,target.isoformat(),latest_issue,now.isoformat())
    db.log('recommend-frozen',{'prediction_id':prediction_id,'sha256':digest(payload),'target':target.isoformat()},lottery)
    db.checkpoint()
    return payload

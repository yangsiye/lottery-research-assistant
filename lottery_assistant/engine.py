from __future__ import annotations
import json, math
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
VERSION='unified-v1.3-github-cloud-six-module'


def sync(lottery,periods=200):
    rows=fetch_ssq(periods) if lottery=='ssq' else fetch_dlt(periods)
    db=DB(DB_PATH)
    for r in rows:
        db.upsert_draw(lottery,r['issue'],r['draw_date'],r['main'],r['bonus'],r['source'])
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
    return _ensemble(probs,weights),metrics,weights


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


def recommend(lottery,seed=None,candidates=5000):
    db=DB(DB_PATH)
    draws=db.get_draws(lottery)
    if len(draws)<80:
        raise RuntimeError(f'Need at least 80 historical draws, found {len(draws)}. Run sync with a larger archive/import.')
    cfg=CONFIG[lottery]
    rng=np.random.default_rng(seed)

    # Main and bonus zones are independent engines but share one governance protocol.
    pm,mm,wm=train_zone(draws,'main_numbers',cfg['main_max'],cfg['main_pick'])
    pb,mb,wb=train_zone(draws,'bonus_numbers',cfg['bonus_max'],cfg['bonus_pick'])

    hist_main=historical_structure(draws,'main_numbers',cfg['main_max'])
    hist_bonus=historical_structure(draws,'bonus_numbers',cfg['bonus_max'])
    prev_main=draws[-1]['main_numbers']
    prev_bonus=draws[-1]['bonus_numbers']

    best=None
    for _ in range(candidates):
        main=_sample_combo(pm,cfg['main_pick'],rng)
        bonus=_sample_combo(pb,cfg['bonus_pick'],rng)
        ps=float(np.mean([pm[n-1] for n in main])+np.mean([pb[n-1] for n in bonus]))/2
        ss1,p1=_soft_structure_score(main,hist_main,cfg['main_max'],prev_main)
        ss2,p2=_soft_structure_score(bonus,hist_bonus,cfg['bonus_max'],prev_bonus)
        # Probability layer dominates; structure never becomes a hard filter.
        combined=0.90*ps+0.10*((ss1+ss2)/2)
        if best is None or combined>best[0]:
            best=(combined,main,bonus,ps,ss1,ss2,p1,p2)

    latest_issue=str(draws[-1]['issue'])
    issue=f'NEXT_AFTER_{latest_issue}'
    rationale={
        'architecture':'six-module unified system',
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
    db.add_prediction(lottery,issue,best[1],best[2],VERSION,best[0],rationale)
    db.log('recommend',{'main':best[1],'bonus':best[2],'score':best[0],'rationale':rationale},lottery)
    return {
        'lottery':lottery,
        'basis_issue':latest_issue,
        'main':best[1],
        'bonus':best[2],
        'model_version':VERSION,
        'model_score':best[0],
        'rationale':rationale,
    }

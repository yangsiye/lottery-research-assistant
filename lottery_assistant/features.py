from __future__ import annotations
import math
from collections import Counter
import numpy as np

WINDOWS=(10,20,30,50,100)

# Prime sets are fixed because SSQ/DLT number pools are small and stable.
_PRIMES={2,3,5,7,11,13,17,19,23,29,31}


def omission(history_sets, n):
    """Number of completed draws since n last appeared."""
    for i,s in enumerate(reversed(history_sets), start=0):
        if n in s:
            return i
    return len(history_sets)


def exp_frequency(history_sets, n, half_life=20):
    """Recency-weighted inclusion frequency; no hot/cold direction is imposed."""
    if not history_sets:
        return 0.0
    weights=[]; vals=[]
    for age,s in enumerate(reversed(history_sets)):
        w=0.5**(age/half_life)
        weights.append(w)
        vals.append(w*(n in s))
    return float(sum(vals)/sum(weights)) if sum(weights) else 0.0


def _window_z(freq_count, window_n, p):
    if window_n <= 0:
        return 0.0
    var=max(window_n*p*(1-p),1e-9)
    return (freq_count-window_n*p)/math.sqrt(var)


def _gap_stats(history_sets, n):
    idx=[i for i,s in enumerate(history_sets) if n in s]
    if len(idx)<2:
        return 0.0,0.0
    gaps=np.diff(idx)
    mean=float(np.mean(gaps))
    cv=float(np.std(gaps)/mean) if mean>0 else 0.0
    return mean,cv


def _neighbor_last(history_sets, n):
    if not history_sets:
        return 0.0
    prev=history_sets[-1]
    return float(((n-1) in prev) or ((n+1) in prev))


def _same_tail_last(history_sets, n):
    if not history_sets:
        return 0.0
    prev=history_sets[-1]
    return float(sum(1 for x in prev if x != n and x%10==n%10))


def _transition_lift(history_sets, n, max_n, pick_n):
    """Average one-step lift from numbers present in the latest draw to candidate n.

    This absorbs 'follow-number' / Markov-style ideas without turning them into a hard rule.
    Positive/negative direction is learned by downstream models.
    """
    if len(history_sets)<3:
        return 1.0
    prev=history_sets[-1]
    p0=pick_n/max_n
    lifts=[]
    for m in prev:
        denom=0; hits=0
        for t in range(1,len(history_sets)):
            if m in history_sets[t-1]:
                denom+=1
                if n in history_sets[t]:
                    hits+=1
        if denom>=3:
            # Beta-Binomial smoothing toward unconditional theoretical inclusion.
            alpha=2.0*p0; beta=2.0*(1-p0)
            cond=(hits+alpha)/(denom+alpha+beta)
            lifts.append(cond/max(p0,1e-9))
    return float(np.mean(lifts)) if lifts else 1.0


def number_features(history_sets, n, max_n, pick_n):
    """Unified per-number feature vector.

    Important: features encode observations only. 'Hot', 'cold', 'overdue', 'repeat',
    'neighbor' and 'mean reversion' are NOT separate decision rules.
    """
    theoretical=pick_n/max_n
    feats={}
    for w in WINDOWS:
        h=history_sets[-w:]
        count=sum(n in s for s in h)
        freq=count/max(1,len(h))
        feats[f'freq_{w}']=freq
        feats[f'freq_ratio_{w}']=freq/theoretical if theoretical else 0.0
        feats[f'freq_z_{w}']=_window_z(count,len(h),theoretical)

    long_n=max(1,len(history_sets))
    count=sum(n in s for s in history_sets)
    p=theoretical
    expected=long_n*p
    var=max(long_n*p*(1-p),1e-9)
    feats['zscore']=(count-expected)/math.sqrt(var)

    om=omission(history_sets,n)
    expected_om=(1-p)/p if p else 0.0
    # Geometric failures-before-success variance q/p^2.
    om_sd=math.sqrt(max(1-p,1e-9))/max(p,1e-9)
    feats['omission']=float(om)
    feats['omission_scaled']=om/max(1,long_n)
    feats['omission_ratio']=om/max(expected_om,1e-9)
    feats['omission_z']=(om-expected_om)/max(om_sd,1e-9)

    feats['exp_freq_10']=exp_frequency(history_sets,n,10)
    feats['exp_freq_20']=exp_frequency(history_sets,n,20)
    feats['exp_freq_50']=exp_frequency(history_sets,n,50)
    feats['trend_10_50']=feats['freq_10']-feats['freq_50']
    feats['trend_20_100']=feats['freq_20']-feats['freq_100']

    # Empirical-Bayes shrinkage toward the theoretical inclusion probability.
    prior_strength=12.0
    alpha=prior_strength*p
    beta=prior_strength*(1-p)
    feats['bayes_mean']=(count+alpha)/(long_n+alpha+beta)

    feats['last_draw']=1.0 if history_sets and n in history_sets[-1] else 0.0
    feats['neighbor_last']=_neighbor_last(history_sets,n)
    feats['same_tail_last']=_same_tail_last(history_sets,n)
    feats['transition_lift']=_transition_lift(history_sets,n,max_n,pick_n)
    gap_mean,gap_cv=_gap_stats(history_sets,n)
    feats['gap_mean']=gap_mean
    feats['gap_cv']=gap_cv
    return feats


def ac_value(numbers):
    """Arithmetic Complexity (AC): distinct positive pairwise differences - (k-1)."""
    xs=sorted(set(numbers))
    if len(xs)<2:
        return 0
    diffs={b-a for i,a in enumerate(xs) for b in xs[i+1:]}
    return max(0,len(diffs)-(len(xs)-1))


def structure_features(numbers, max_n, previous_numbers=None):
    xs=sorted(numbers)
    if not xs:
        return {}
    previous_numbers=set(previous_numbers or [])
    odd=sum(x%2 for x in xs)
    big=sum(x > (max_n+1)//2 for x in xs)
    span=max(xs)-min(xs) if len(xs)>1 else 0
    consecutive=sum(1 for a,b in zip(xs,xs[1:]) if b-a==1)
    tails=Counter(x%10 for x in xs)
    same_tail_pairs=sum(v*(v-1)//2 for v in tails.values())
    residues=[sum(1 for x in xs if x%3==r) for r in range(3)]
    # Equal-width 3-zone partition, deterministic for both SSQ and DLT pools.
    z1=max_n//3
    z2=(2*max_n)//3
    zones=[sum(1 for x in xs if 1<=x<=z1),
           sum(1 for x in xs if z1<x<=z2),
           sum(1 for x in xs if z2<x<=max_n)]
    repeat=sum(1 for x in xs if x in previous_numbers)
    neighbor=sum(1 for x in xs if ((x-1) in previous_numbers or (x+1) in previous_numbers))
    prime=sum(1 for x in xs if x in _PRIMES)
    return {
        'sum':sum(xs),
        'odd':odd,
        'big':big,
        'span':span,
        'consecutive_pairs':consecutive,
        'distinct_tails':len(tails),
        'same_tail_pairs':same_tail_pairs,
        'r0':residues[0],'r1':residues[1],'r2':residues[2],
        'zone1':zones[0],'zone2':zones[1],'zone3':zones[2],
        'prime':prime,
        'ac':ac_value(xs),
        'repeat_prev':repeat,
        'neighbor_prev':neighbor,
    }


def historical_structure(draws, key='main_numbers', max_n=None):
    rows=[]
    prev=[]
    for d in draws:
        nums=d[key]
        if not nums:
            continue
        local_max=max_n or max(nums)
        rows.append(structure_features(nums,local_max,prev))
        prev=nums
    if not rows:
        return {}
    out={}
    for k in rows[0]:
        vals=np.array([r[k] for r in rows],dtype=float)
        out[k]={
            'p10':float(np.quantile(vals,.1)),
            'p20':float(np.quantile(vals,.2)),
            'p80':float(np.quantile(vals,.8)),
            'p90':float(np.quantile(vals,.9)),
            'median':float(np.median(vals)),
            'mean':float(vals.mean()),
            'std':float(vals.std()),
        }
    return out

from __future__ import annotations
from dataclasses import dataclass
from itertools import combinations
from .rules import prize_tier, fixed_prize, bet_count, bet_cost

def evaluate_single(lottery, predicted_main, predicted_bonus, actual_main, actual_bonus, *, pool_ge_800m=False, ssq_special=False):
    mh=len(set(predicted_main)&set(actual_main)); bh=len(set(predicted_bonus)&set(actual_bonus))
    tier=prize_tier(lottery,mh,bh,ssq_special=ssq_special)
    return {'main_hits':mh,'bonus_hits':bh,'tier':tier,'fixed_prize':fixed_prize(lottery,tier,pool_ge_800m=pool_ge_800m,ssq_special=ssq_special) if tier else None}

def expand_bet(lottery, main_numbers, bonus_numbers):
    mp=5 if lottery=='dlt' else 6; bp=2 if lottery=='dlt' else 1
    for m in combinations(sorted(set(main_numbers)),mp):
        for b in combinations(sorted(set(bonus_numbers)),bp):
            yield m,b

def evaluate_multiple(lottery, main_numbers, bonus_numbers, actual_main, actual_bonus, *, multiplier=1, additional=False, pool_ge_800m=False, ssq_special=False):
    tiers={}; fixed_total=0; floating=False
    for m,b in expand_bet(lottery,main_numbers,bonus_numbers):
        r=evaluate_single(lottery,m,b,actual_main,actual_bonus,pool_ge_800m=pool_ge_800m,ssq_special=ssq_special)
        if r['tier']:
            tiers[r['tier']]=tiers.get(r['tier'],0)+1
            if r['fixed_prize'] is None: floating=True
            else: fixed_total += r['fixed_prize']*multiplier
    return {'bet_count':bet_count(lottery,len(set(main_numbers)),len(set(bonus_numbers))),
            'cost':bet_cost(lottery,len(set(main_numbers)),len(set(bonus_numbers)),multiplier,additional),
            'winning_tiers':tiers,'fixed_prize_total':fixed_total,
            'contains_floating_prize':floating,
            'note':'一、二等奖为浮动奖，实际奖金必须以当期官方公告为准' if floating else None}

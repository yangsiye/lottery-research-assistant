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


def _amount(value):
    from decimal import Decimal, InvalidOperation
    try:
        amount=Decimal(str(value).replace(',',''))
        return float(amount) if amount.is_finite() and amount>=0 else None
    except (InvalidOperation, ValueError): return None


def evaluate_official(lottery, main, bonus, actual):
    """Use the same draw's published prize table; missing metadata stays explicit."""
    record=(actual.get('prize_data') or {}).get('official_record',{})
    table=record.get('prizegrades') if lottery=='ssq' else record.get('lotteryDrawPrize')
    table=table if isinstance(table,list) else []
    names={1:'一等奖',2:'二等奖',3:'三等奖',4:'四等奖',5:'五等奖',6:'六等奖',7:'福运奖' if lottery=='ssq' else '七等奖'}
    prizes={}
    special=None
    for row in table:
        raw_type=row.get('type') if lottery=='ssq' else row.get('prizeLevel')
        label=row.get('name') or row.get('prizeName')
        try: label=label or names[int(raw_type)]
        except (ValueError,TypeError,KeyError): pass
        # Only an explicit official label verifies the special SSQ award.
        if label=='福运奖': special=True
        if label:
            value=row.get('typemoney') if lottery=='ssq' else row.get('stakeAmount')
            prizes[label]=_amount(value)
    if lottery=='ssq' and table and record.get('prize_table_complete',True) and special is None: special=False
    mh=len(set(main)&set(actual['main_numbers'])); bh=len(set(bonus)&set(actual['bonus_numbers']))
    cutoff='2026-02-02' if lottery=='dlt' else '2026-02-01'
    if actual['draw_date']<cutoff:
        return {'main_hits':mh,'bonus_hits':bh,'tier':None,'prize_amount':None,'prize_status':'RULES_UNVERIFIED',
                'note':'历史规则不同，需按历史规则单独对奖'}
    tier=prize_tier(lottery,mh,bh,ssq_special=special is True)
    unknown_special=lottery=='ssq' and mh==3 and bh==0 and special is None
    amount=prizes.get(tier)
    if not tier and not unknown_special: amount=0
    if amount is None and lottery=='ssq' and tier not in ('一等奖','二等奖') and not unknown_special:
        amount=fixed_prize(lottery,tier,ssq_special=special is True)
    out={'main_hits':mh,'bonus_hits':bh,'tier':tier,'prize_amount':amount,
         'prize_status':'VERIFIED' if amount is not None else 'OFFICIAL_PRIZE_PENDING',
         'cost':2,'net_return':amount-2 if amount is not None else None}
    if unknown_special:
        out['possible_tier']='福运奖'; out['note']='当期福运奖状态缺失，不推定奖金'
    elif lottery=='dlt' and tier and amount is None and tier not in ('一等奖','二等奖'):
        out['prize_range']=[fixed_prize(lottery,tier),fixed_prize(lottery,tier,pool_ge_800m=True)]
        out['note']='需核验当期官方奖表；不把开奖后奖池误当本期奖金阈值'
    elif amount is None: out['note']='浮动奖金以当期官方公告为准'
    return out


def dantuo_count(lottery, main_dan, main_tuo, bonus_dan, bonus_tuo):
    from math import comb
    pools={'dlt':(35,12,5,2),'ssq':(33,16,6,1)}
    if lottery not in pools: raise ValueError('unknown lottery')
    max_m,max_b,mp,bp=pools[lottery]
    for dan,tuo,maximum,pick in ((main_dan,main_tuo,max_m,mp),(bonus_dan,bonus_tuo,max_b,bp)):
        if len(set(dan))!=len(dan) or len(set(tuo))!=len(tuo) or set(dan)&set(tuo):
            raise ValueError('胆码拖码不能重复或交叉')
        if any(not isinstance(n,int) or isinstance(n,bool) or not 1<=n<=maximum for n in [*dan,*tuo]):
            raise ValueError('number out of range')
        if len(dan)>=pick or len(dan)+len(tuo)<pick: raise ValueError('invalid dantuo counts')
    if not main_dan and not bonus_dan: raise ValueError('at least one zone needs 胆码')
    if main_dan and len(main_dan)+len(main_tuo)<=mp: raise ValueError('main dantuo needs multiple combinations')
    if bonus_dan and len(bonus_tuo)<2: raise ValueError('bonus dantuo needs at least 2 拖码')
    return comb(len(main_tuo),mp-len(main_dan))*comb(len(bonus_tuo),bp-len(bonus_dan))

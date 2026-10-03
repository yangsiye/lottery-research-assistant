from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from math import comb

DRAW_DAYS = {"dlt": {0, 2, 5}, "ssq": {1, 3, 6}}

# Official Ministry of Finance 2026 nationwide lottery-market closures.
# During these windows (inclusive), non-instant games stop sales, draws and prize redemption.
CLOSURES = {
    2026: (
        (date(2026, 2, 14), date(2026, 2, 23), "春节休市"),
        (date(2026, 10, 1), date(2026, 10, 4), "国庆休市"),
    )
}

def closure_reason(day: date) -> str | None:
    for start, end, reason in CLOSURES.get(day.year, ()):
        if start <= day <= end:
            return reason
    return None

def draw_status(lottery: str, day: date) -> dict:
    if lottery not in DRAW_DAYS:
        raise ValueError(f"unknown lottery: {lottery}")
    reason = closure_reason(day)
    scheduled = day.weekday() in DRAW_DAYS[lottery]
    if reason:
        return {"status": "HOLIDAY_SUSPENDED", "scheduled_weekday": scheduled, "reason": reason}
    if not scheduled:
        return {"status": "NO_DRAW_TODAY", "scheduled_weekday": False, "reason": "非该彩种常规开奖日"}
    return {"status": "WAITING_DRAW", "scheduled_weekday": True, "reason": "常规开奖日，等待官方开奖结果"}

def bet_count(lottery: str, main_count: int, bonus_count: int) -> int:
    if lottery == "dlt":
        if main_count < 5 or bonus_count < 2: return 0
        return comb(main_count, 5) * comb(bonus_count, 2)
    if lottery == "ssq":
        if main_count < 6 or bonus_count < 1: return 0
        return comb(main_count, 6) * bonus_count
    raise ValueError(f"unknown lottery: {lottery}")

def bet_cost(lottery: str, main_count: int, bonus_count: int, multiplier: int = 1, additional: bool = False) -> int:
    n = bet_count(lottery, main_count, bonus_count)
    unit = 3 if lottery == "dlt" and additional else 2
    return n * unit * multiplier

def prize_tier(lottery: str, main_hits: int, bonus_hits: int, *, ssq_special: bool = False) -> str | None:
    if lottery == "dlt":
        mapping = {
            (5,2): "一等奖", (5,1): "二等奖",
            (5,0): "三等奖", (4,2): "三等奖",
            (4,1): "四等奖",
            (4,0): "五等奖", (3,2): "五等奖",
            (3,1): "六等奖", (2,2): "六等奖",
        }
        if (main_hits, bonus_hits) in mapping: return mapping[(main_hits, bonus_hits)]
        if (main_hits == 3 and bonus_hits == 0) or (main_hits == 2 and bonus_hits == 1) or (main_hits == 1 and bonus_hits == 2) or (main_hits == 0 and bonus_hits == 2):
            return "七等奖"
        return None
    if lottery == "ssq":
        if main_hits == 6 and bonus_hits == 1: return "一等奖"
        if main_hits == 6: return "二等奖"
        if main_hits == 5 and bonus_hits == 1: return "三等奖"
        if main_hits == 5 or (main_hits == 4 and bonus_hits == 1): return "四等奖"
        if main_hits == 4 or (main_hits == 3 and bonus_hits == 1): return "五等奖"
        if bonus_hits == 1: return "六等奖"
        if ssq_special and main_hits == 3: return "福运奖"
        return None
    raise ValueError(f"unknown lottery: {lottery}")

def fixed_prize(lottery: str, tier: str, *, pool_ge_800m: bool = False, ssq_special: bool = False) -> int | None:
    if lottery == "dlt":
        low = {"三等奖":5000,"四等奖":300,"五等奖":150,"六等奖":15,"七等奖":5}
        high = {"三等奖":6666,"四等奖":380,"五等奖":200,"六等奖":18,"七等奖":7}
        return (high if pool_ge_800m else low).get(tier)
    if lottery == "ssq":
        fixed = {"三等奖":3000,"四等奖":200,"五等奖":10,"六等奖":5}
        if ssq_special: fixed["福运奖"] = 5
        return fixed.get(tier)
    raise ValueError(f"unknown lottery: {lottery}")

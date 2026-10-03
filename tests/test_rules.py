from datetime import date
from lottery_assistant.rules import draw_status, bet_count, bet_cost, prize_tier, fixed_prize

def test_2026_national_day_closure_overrides_dlt_saturday():
    s=draw_status("dlt", date(2026,10,3))
    assert s["status"]=="HOLIDAY_SUSPENDED"
    assert s["scheduled_weekday"] is True

def test_regular_draw_days():
    assert draw_status("dlt", date(2026,10,5))["status"]=="WAITING_DRAW"
    assert draw_status("ssq", date(2026,10,5))["status"]=="NO_DRAW_TODAY"
    assert draw_status("ssq", date(2026,10,6))["status"]=="WAITING_DRAW"

def test_bet_math():
    assert bet_count("dlt",7,3)==63
    assert bet_cost("dlt",7,3)==126
    assert bet_cost("dlt",7,3,additional=True)==189
    assert bet_count("ssq",7,2)==14
    assert bet_cost("ssq",7,2)==28

def test_dlt_2026_seven_tiers():
    assert prize_tier("dlt",5,2)=="一等奖"
    assert prize_tier("dlt",4,2)=="三等奖"
    assert prize_tier("dlt",0,2)=="七等奖"
    assert fixed_prize("dlt","七等奖",pool_ge_800m=False)==5
    assert fixed_prize("dlt","七等奖",pool_ge_800m=True)==7

def test_ssq_2026_special_fuyun():
    assert prize_tier("ssq",6,1)=="一等奖"
    assert prize_tier("ssq",3,0,ssq_special=False) is None
    assert prize_tier("ssq",3,0,ssq_special=True)=="福运奖"
    assert fixed_prize("ssq","福运奖",ssq_special=True)==5

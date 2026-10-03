import pytest
from lottery_assistant.fetchers import validate_archive, FetchError
from lottery_assistant.evaluator import evaluate_official,dantuo_count
from lottery_assistant.rules import bet_cost,draw_status
from datetime import date


def row(issue='26113',day='2026-09-30'):
    return {'issue':issue,'draw_date':day,'main':[1,2,3,4,5],'bonus':[1,2],'source':'TEST_FIXTURE'}


def test_archive_never_silently_discards_bad_or_missing_data():
    with pytest.raises(FetchError,match='历史不足'): validate_archive([row()],'dlt',500)
    invalid=row();invalid['main']=[1,1,2,3,4]
    with pytest.raises(FetchError,match='number'): validate_archive([invalid],'dlt',1)
    with pytest.raises(FetchError,match='gap'): validate_archive([row('26111','2026-09-28'),row()],'dlt',2)
    with pytest.raises(FetchError,match='calendar'): validate_archive([row(day='2026-10-03')],'dlt',1)


def test_missing_official_prize_is_not_zero_or_assumed_low_pool():
    actual={'draw_date':'2026-10-05','main_numbers':[1,2,3,4,9],'bonus_numbers':[1,2]}
    result=evaluate_official('dlt',[1,2,3,4,5],[1,2],actual)
    assert result['tier']=='三等奖' and result['prize_range']==[5000,6666]
    assert result['prize_amount'] is None and result['net_return'] is None
    actual={'draw_date':'2026-10-06','main_numbers':[1,2,3,10,11,12],'bonus_numbers':[9]}
    result=evaluate_official('ssq',[1,2,3,4,5,6],[1],actual)
    assert result['possible_tier']=='福运奖' and result['prize_amount'] is None


def test_bet_validation_and_dantuo():
    assert dantuo_count('dlt',[1,2],[3,4,5,6,7],[],[1,2,3])==30
    assert dantuo_count('ssq',[1,2,3],[4,5,6,7,8],[],[1,2])==20
    with pytest.raises(ValueError): dantuo_count('dlt',[1,2],[2,3,4,5,6],[],[1,2])
    for multiplier in (-1,0,100,1.2):
        with pytest.raises(ValueError): bet_cost('dlt',5,2,multiplier)
    with pytest.raises(ValueError): bet_cost('ssq',6,1,additional=True)
    assert draw_status('dlt',date(2027,10,2))['status']=='RULES_UNVERIFIED'

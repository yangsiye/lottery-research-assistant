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


def test_provincial_official_html_parser_and_incomplete_awards():
    from lottery_assistant.official_fallbacks import parse_shanghai_ssq
    html='''<table><tr><td>2026113</td><td>2026-09-29(二)</td>
    <td><i>03</i><i>04</i><i>20</i><i>24</i><i>29</i><i>30</i></td><td><i>11</i></td>
    <td>338536676</td><td>10</td><td>6845689</td><td>973407364</td></tr></table>'''
    rows=parse_shanghai_ssq(html)
    assert rows[0]['main']==[3,4,20,24,29,30] and rows[0]['source']=='swlc.net.cn'
    actual={'draw_date':'2026-10-06','main_numbers':[1,2,3,10,11,12],'bonus_numbers':[9],
            'prize_data':rows[0]['prize_data']}
    outcome=evaluate_official('ssq',[1,2,3,4,5,6],[1],actual)
    assert outcome['possible_tier']=='福运奖' and outcome['prize_amount'] is None


def test_fallback_requires_verified_official_archive(monkeypatch):
    from lottery_assistant.fetchers import _with_official_fallback
    def primary(periods): raise FetchError('official HTTP 403')
    def fallback(periods): return [{**row(),'prize_data':{}}]
    result=_with_official_fallback(primary,fallback,1)
    assert '403' in result[0]['prize_data']['primary_source_error']
    def failed(periods): raise FetchError('not enough official rows')
    with pytest.raises(FetchError,match='provincial official fallback failed'):
        _with_official_fallback(primary,failed,500)


def test_audited_correction_requires_exact_signature_and_keeps_provenance():
    from lottery_assistant.official_fallbacks import apply_audited_correction
    draw={'source':'gstc.org.cn','lottery':'dlt','issue':'25092','draw_date':'2025-09-04',
          'main':[4,10,17,25,32],'bonus':[5,7],'prize_data':{'official_record':{'prize_time':'2025-09-04'}}}
    fixed=apply_audited_correction(draw)
    assert fixed['draw_date']=='2025-08-13'
    assert fixed['prize_data']['official_record']['prize_time']=='2025-09-04'
    assert len(fixed['prize_data']['date_correction']['evidence_urls'])==3
    validate_archive([fixed],'dlt',1)
    bad={**draw,'draw_date':'2025-09-04','main':[1,10,17,25,32]}
    with pytest.raises(ValueError,match='signature mismatch'): apply_audited_correction(bad)

import pytest
from lottery_assistant.fetchers import validate_archive, FetchError
from lottery_assistant.evaluator import evaluate_official,dantuo_count
from lottery_assistant.rules import bet_cost,draw_status
from datetime import date,datetime
from lottery_assistant.lifecycle import TZ


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


def ssq_row(issue='2026123',day='2026-10-27',main=None):
    return {'lottery':'ssq','issue':issue,'draw_date':day,'main':main or [4,5,20,21,26,30],
            'bonus':[12],'source':'swlc.net.cn','prize_data':{}}


def test_archive_validates_lottery_issue_year_and_calendar_gaps():
    for invalid in (ssq_row(issue='26123'),ssq_row(issue='2025123'),ssq_row(issue='2026000')):
        with pytest.raises(FetchError,match='issue/date'): validate_archive([invalid],'ssq',1)
    invalid=ssq_row();invalid['main'][0]=True
    with pytest.raises(FetchError,match='number'): validate_archive([invalid],'ssq',1)
    # Consecutive issue labels must not disguise a missing draw date.
    with pytest.raises(FetchError,match='date gap'):
        validate_archive([ssq_row('2026122','2026-10-22'),ssq_row()],'ssq',2)


def test_sync_rejects_stale_conflicting_and_regressed_official_data():
    from lottery_assistant.fetchers import validate_sync_archive
    now=datetime(2026,10,29,16,tzinfo=TZ)
    old={**ssq_row(),'main_numbers':[4,5,20,21,26,30],'bonus_numbers':[12]}
    assert validate_sync_archive([ssq_row()],[old],'ssq',1,now)[0]['issue']=='2026123'
    with pytest.raises(FetchError,match='conflicts with persisted'):
        validate_sync_archive([ssq_row(main=[1,5,20,21,26,30])],[old],'ssq',1,now)
    with pytest.raises(FetchError,match='regressed'):
        validate_sync_archive([ssq_row('2026122','2026-10-25')],[old],'ssq',1,now)
    with pytest.raises(FetchError,match='source stale'):
        validate_sync_archive([ssq_row('2026122','2026-10-25')],[],'ssq',1,now)
    with pytest.raises(FetchError,match='before its scheduled draw'):
        validate_sync_archive([ssq_row('2026124','2026-10-29')],[],'ssq',1,now)
    # Oct 1-4 is the verified closure, so Sep 29 remains the valid basis on Oct 6.
    assert validate_sync_archive([ssq_row('2026113','2026-09-29')],[],'ssq',1,
                                 datetime(2026,10,6,16,tzinfo=TZ))


def test_sync_batch_is_preflighted_and_rolls_back_on_write_failure(tmp_path,monkeypatch):
    from lottery_assistant import engine
    from lottery_assistant.db import DB
    from lottery_assistant.fetchers import validate_sync_archive
    path=tmp_path/'db';db=DB(path)
    now=datetime(2026,10,29,16,tzinfo=TZ)
    records=[ssq_row('2026122','2026-10-25'),ssq_row()]
    monkeypatch.setattr(engine,'DB_PATH',path)
    monkeypatch.setattr(engine,'fetch_ssq',lambda n:records)
    monkeypatch.setattr(engine,'validate_sync_archive',lambda rows,old,lot,n:
                        validate_sync_archive(rows,old,lot,n,now))
    original=DB.upsert_draw;calls=[]
    def interrupted(self,*args,**kwargs):
        original(self,*args,**kwargs);calls.append(args[1])
        if len(calls)==2: raise RuntimeError('injected storage failure')
    monkeypatch.setattr(DB,'upsert_draw',interrupted)
    with pytest.raises(RuntimeError,match='storage failure'): engine.sync('ssq',2)
    assert db.get_draws('ssq')==[]


def test_shanghai_pagination_never_discards_conflicting_overlap(monkeypatch):
    from lottery_assistant import official_fallbacks
    from types import SimpleNamespace
    batches=[[ssq_row(),ssq_row('2026122','2026-10-25')],
             [ssq_row('2026122','2026-10-25',main=[1,5,20,21,26,30]),ssq_row('2026121','2026-10-22')]]
    class Session:
        headers={}
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def mount(self,*args): pass
        def get(self,*args,**kwargs):
            return SimpleNamespace(text='fixture',raise_for_status=lambda:None)
    monkeypatch.setattr(official_fallbacks.requests,'Session',Session)
    monkeypatch.setattr(official_fallbacks,'parse_shanghai_ssq',lambda html:batches.pop(0))
    with pytest.raises(FetchError,match='conflicting duplicate'):
        official_fallbacks.fetch_shanghai_ssq(3)


def test_fallback_sync_preserves_existing_complete_prize_table(tmp_path,monkeypatch):
    from lottery_assistant import engine
    from lottery_assistant.db import DB
    from lottery_assistant.fetchers import validate_sync_archive
    path=tmp_path/'db';db=DB(path);r=ssq_row()
    full={'prizegrades':[{'type':1,'typemoney':'5000000'},{'type':2,'typemoney':'100000'}]}
    db.upsert_draw('ssq',r['issue'],r['draw_date'],r['main'],r['bonus'],'cwl.gov.cn',{'official_record':full})
    r['prize_data']={'official_record':{'prizegrades':[{'type':1,'typemoney':'5000000'}],'prize_table_complete':False},
                     'primary_source_error':'HTTP 403'}
    monkeypatch.setattr(engine,'DB_PATH',path)
    monkeypatch.setattr(engine,'fetch_ssq',lambda n:[r])
    monkeypatch.setattr(engine,'validate_sync_archive',lambda rows,old,lot,n:
                        validate_sync_archive(rows,old,lot,n,datetime(2026,10,29,16,tzinfo=TZ)))
    assert engine.sync('ssq',1)==1
    meta=db.get_draws('ssq')[0]['prize_data']
    assert meta['official_record']==full and meta['official_record_source']=='cwl.gov.cn'
    assert meta['latest_source_official_record']['prize_table_complete'] is False
    assert '403' in meta['primary_source_error']


def test_real_persisted_conflict_is_durable_and_never_silently_cleared(tmp_path,monkeypatch):
    from lottery_assistant import engine
    from lottery_assistant.db import DB
    from lottery_assistant.fetchers import ArchiveConflictError,validate_sync_archive
    path=tmp_path/'db';db=DB(path);original=ssq_row()
    db.upsert_draw('ssq',original['issue'],original['draw_date'],original['main'],original['bonus'],original['source'])
    bad=ssq_row(main=[1,5,20,21,26,30]);calls=[]
    monkeypatch.setattr(engine,'DB_PATH',path)
    def fetch(n): calls.append(n);return [bad]
    monkeypatch.setattr(engine,'fetch_ssq',fetch)
    monkeypatch.setattr(engine,'validate_sync_archive',lambda rows,old,lot,n:
                        validate_sync_archive(rows,old,lot,n,datetime(2026,10,29,16,tzinfo=TZ)))
    with pytest.raises(ArchiveConflictError,match='conflicts with persisted'): engine.sync('ssq',1)
    flag=db.get_data_quality_flag('ssq')
    assert flag['status']=='BLOCKED' and flag['evidence']['issue']=='2026123'
    assert db.get_draws('ssq')[0]['main_numbers']==original['main']
    bad=original
    with pytest.raises(ArchiveConflictError,match='unresolved'): engine.sync('ssq',1)
    assert calls==[1]  # A later clean response cannot silently override an unresolved conflict.
    assert DB(path).get_data_quality_flag('ssq')['status']=='BLOCKED'
    assert db.get_data_quality_flag('dlt') is None
    with pytest.raises(ValueError,match='evidence URLs'):
        db.resolve_data_quality_flag('ssq',resolution='checked',evidence_urls=[])
    db.resolve_data_quality_flag('ssq',resolution='Source correction independently audited; persisted record is correct',
                                 evidence_urls=['https://www.swlc.net.cn/lottery/ssq.html'])
    assert engine.sync('ssq',1)==1
    assert db.get_data_quality_flag('ssq')['status']=='RESOLVED'


def test_primary_unavailable_or_stale_source_does_not_create_conflict_flag(tmp_path,monkeypatch):
    from lottery_assistant import engine
    from lottery_assistant.db import DB
    path=tmp_path/'db';db=DB(path)
    monkeypatch.setattr(engine,'DB_PATH',path)
    def unavailable(n): raise FetchError('HTTP 403')
    monkeypatch.setattr(engine,'fetch_ssq',unavailable)
    with pytest.raises(FetchError,match='403'): engine.sync('ssq',1)
    assert db.get_data_quality_flag('ssq') is None

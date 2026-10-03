"""Synthetic fixtures are isolated in tmp_path and never enter production data."""
import json
import sqlite3
from datetime import datetime, date, timedelta
import pytest
from lottery_assistant.db import DB
from lottery_assistant.lifecycle import TZ, digest
from lottery_assistant import engine, cloud
from lottery_assistant.rules import draw_status
from chatgpt_bridge import build_bridge


def seed_archive(db,lottery,n=82):
    target=date(2026,10,5) if lottery=='dlt' else date(2026,10,6)
    day=target-timedelta(days=1);days=[]
    while len(days)<n:
        if draw_status(lottery,day)['status']=='WAITING_DRAW': days.append(day)
        day-=timedelta(days=1)
    mp,bp,maxm,maxb=(5,2,35,12) if lottery=='dlt' else (6,1,33,16)
    for i,day in enumerate(reversed(days),1):
        main=sorted({(i+j*3)%maxm+1 for j in range(mp)})
        bonus=sorted({(i+j*2)%maxb+1 for j in range(bp)})
        db.upsert_draw(lottery,f'2026{i:03}',day.isoformat(),main,bonus,'TEST_FIXTURE')
    return target


@pytest.mark.parametrize('lottery',['ssq','dlt'])
def test_real_models_freeze_review_bridge_and_restart(tmp_path,monkeypatch,lottery):
    path=tmp_path/'data/lottery.db';db=DB(path)
    monkeypatch.setattr(engine,'DB_PATH',path)
    target=seed_archive(db,lottery)
    now=datetime.combine(target,datetime.min.time(),TZ).replace(hour=15,minute=30)
    rec=engine.recommend(lottery,seed=7,candidates=20,now=now)
    freeze=db.get_prediction_freeze(rec['prediction_id'])
    assert freeze['payload_sha256']==digest(rec)
    assert rec['model_probabilities']['main']['uniform']
    assert rec['rationale']['baseline_fallback'] is True
    assert engine.recommend(lottery,seed=999,now=now)==rec
    assert db.conn.execute('SELECT count(*) FROM predictions').fetchone()[0]==1
    assert cloud._review_new_predictions(db,lottery,now)==[]
    # Test lottery draw deliberately matches fixture; no claim about actual winning numbers.
    record={'prizegrades':[{'type':1,'typemoney':'5000000'}]} if lottery=='ssq' else {
        'lotteryDrawPrize':[{'prizeLevel':1,'stakeAmount':'10000000'}]}
    db.upsert_draw(lottery,'2026083',target.isoformat(),rec['main'],rec['bonus'],'TEST_FIXTURE',{'official_record':record})
    night=now.replace(hour=23)
    reviews=cloud._review_new_predictions(db,lottery,night)
    assert len(reviews)==1 and reviews[0]['tier']=='一等奖'
    assert reviews[0]['prize_status']=='VERIFIED'
    assert reviews[0]['model_attribution']['main']['uniform']['brier']>0
    assert cloud._review_new_predictions(db,lottery,night)==[]
    db.checkpoint();db.conn.close()
    reports=tmp_path/'reports';reports.mkdir()
    (reports/'latest_cloud_run.json').write_text(json.dumps({'now':night.isoformat(),'actions':[]}))
    (reports/'latest_review.json').write_text(json.dumps({'as_of':night.isoformat(),lottery:{'draw_state':'DRAW_COMPLETED','reviews':reviews}}))
    bridge=build_bridge(tmp_path,night)
    assert bridge['draw_states'][lottery]['status']=='DRAW_COMPLETED'
    assert len(bridge['recent_reviews'])==1 and bridge[lottery] is None
    tomorrow=night+timedelta(days=1)
    bridge=build_bridge(tmp_path,tomorrow)
    assert bridge['bridge_health']['status']=='BRIDGE_STALE'
    assert bridge['latest_review'] is None
    assert bridge[lottery] is None


def freeze_fixture(db,lottery='dlt',target='2026-10-05',when='2026-10-05T15:30:00+08:00'):
    pid=db.add_prediction(lottery,'NEXT_AFTER_26113',[1,2,3,4,5],[1,2],'test',0,{})
    p={'prediction_id':pid,'lottery':lottery,'basis_issue':'26113','target_draw_date':target,
       'frozen_at':when,'main':[1,2,3,4,5],'bonus':[1,2]}
    db.freeze_prediction(pid,digest(p),p,target,'26113',when)
    return pid,p


def test_freeze_cannot_be_rewritten(tmp_path):
    db=DB(tmp_path/'db');pid,p=freeze_fixture(db)
    for sql in ['UPDATE predictions SET main_numbers="[]" WHERE id=?',
                'DELETE FROM predictions WHERE id=?',
                'UPDATE prediction_freezes SET payload_sha256="fake" WHERE prediction_id=?',
                'DELETE FROM prediction_freezes WHERE prediction_id=?']:
        with pytest.raises(sqlite3.IntegrityError): db.conn.execute(sql,(pid,))
        db.conn.rollback()
    p['main']=[6,7,8,9,10]
    with pytest.raises(ValueError): db.freeze_prediction(pid,digest(p),p)


@pytest.mark.parametrize('target,when',[('2026-10-07','2026-10-05T15:30:00+08:00'),
                                       ('2026-10-05','2026-10-05T21:30:00+08:00')])
def test_review_rejects_wrong_target_or_late_freeze(tmp_path,target,when):
    db=DB(tmp_path/'db');pid,p=freeze_fixture(db,target=target,when=when)
    db.upsert_draw('dlt','26113','2026-09-30',[6,7,8,9,10],[3,4],'TEST_FIXTURE')
    db.upsert_draw('dlt','26114','2026-10-05',p['main'],p['bonus'],'TEST_FIXTURE')
    assert cloud._review_new_predictions(db,'dlt',datetime(2026,10,7,23,tzinfo=TZ))==[]


def test_recommendation_refuses_stale_or_late_data(tmp_path,monkeypatch):
    path=tmp_path/'db';db=DB(path);seed_archive(db,'dlt')
    monkeypatch.setattr(engine,'DB_PATH',path)
    with pytest.raises(RuntimeError,match='不是可开奖日'):
        engine.recommend('dlt',now=datetime(2026,10,3,15,tzinfo=TZ))
    with pytest.raises(RuntimeError,match='发布时间'):
        engine.recommend('dlt',now=datetime(2026,10,5,23,tzinfo=TZ))
    with pytest.raises(RuntimeError,match='数据未更新'):
        engine.recommend('dlt',now=datetime(2026,10,7,15,tzinfo=TZ))


def test_old_review_never_overrides_holiday(tmp_path):
    (tmp_path/'reports').mkdir()
    (tmp_path/'reports/latest_cloud_run.json').write_text(json.dumps({'now':'2026-10-04T08:30:00+08:00','actions':[]}))
    (tmp_path/'reports/latest_review.json').write_text(json.dumps({'as_of':'2026-09-30T23:00:00+08:00','dlt':{'draw_state':'DRAW_COMPLETED'}}))
    payload=build_bridge(tmp_path,datetime(2026,10,4,9,tzinfo=TZ))
    assert payload['draw_states']['dlt']['status']=='HOLIDAY_SUSPENDED'
    assert payload['draw_states']['ssq']['status']=='HOLIDAY_SUSPENDED'
    assert payload['latest_review'] is None


def test_failed_jobs_retry_and_delayed_schedule_runs(tmp_path,monkeypatch):
    path=tmp_path/'data/lottery.db';db=DB(path)
    for lot in ('dlt','ssq'): seed_archive(db,lot)
    monkeypatch.setattr(cloud,'DB_PATH',path)
    monkeypatch.setattr(cloud,'REPORT_DIR',tmp_path/'reports')
    from lottery_assistant import cloud_research
    monkeypatch.setattr(cloud_research,'discover_github_candidates',lambda:[])
    failed=[True];calls=[]
    def fake_sync(lot,periods):
        calls.append(lot)
        if failed[0]: raise RuntimeError('official unavailable')
        return 500
    monkeypatch.setattr(cloud,'sync',fake_sync)
    first=cloud.run_due(datetime(2026,10,4,9,5,tzinfo=TZ))
    assert first.actions[1]['status']=='partial'
    failed[0]=False
    second=cloud.run_due(datetime(2026,10,4,9,10,tzinfo=TZ))
    assert second.actions[1]['status']=='ok'
    cloud.run_due(datetime(2026,10,4,9,15,tzinfo=TZ))
    assert len(calls)==4


def test_morning_sync_catches_late_review_on_non_draw_day(tmp_path,monkeypatch):
    path=tmp_path/'data/lottery.db';db=DB(path)
    for lot in ('ssq','dlt'): seed_archive(db,lot)
    pid,p=freeze_fixture(db)
    db.upsert_draw('dlt','26113','2026-09-30',[6,7,8,9,10],[3,4],'TEST_FIXTURE')
    db.upsert_draw('dlt','26114','2026-10-05',p['main'],p['bonus'],'TEST_FIXTURE')
    monkeypatch.setattr(cloud,'DB_PATH',path)
    monkeypatch.setattr(cloud,'REPORT_DIR',tmp_path/'reports')
    monkeypatch.setattr(cloud,'sync',lambda lot,periods:500)
    from lottery_assistant import cloud_research
    monkeypatch.setattr(cloud_research,'discover_github_candidates',lambda:[])
    run=cloud.run_due(datetime(2026,10,6,9,tzinfo=TZ))
    reviews=run.actions[1]['details']['dlt']['reviews']
    assert len(reviews)==1 and reviews[0]['prediction_id']==pid
    report=json.loads((tmp_path/'reports/latest_review.json').read_text())
    assert report['dlt']['draw_state']=='NO_DRAW_TODAY'
    assert cloud._review_new_predictions(db,'dlt',datetime(2026,10,6,10,tzinfo=TZ))==[]

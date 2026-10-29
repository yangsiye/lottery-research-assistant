"""Scheduler regressions use isolated synthetic state and never train new picks."""
from datetime import datetime
from pathlib import Path

import pytest

from lottery_assistant import cloud
from lottery_assistant.db import DB
from lottery_assistant.lifecycle import TZ, digest


@pytest.fixture
def cycle(tmp_path, monkeypatch):
    path=tmp_path/'lottery.db'
    db=DB(path)
    for lot in ('ssq','dlt'):
        db.upsert_draw(lot,'2026123','2026-10-27',[1,2,3,4,5,6] if lot=='ssq' else [1,2,3,4,5],
                       [1] if lot=='ssq' else [1,2],'TEST_FIXTURE')
    db.record_job_run('morning-sync:2026-10-29','ok',{})
    monkeypatch.setattr(cloud,'DB_PATH',path)
    monkeypatch.setattr(cloud,'REPORT_DIR',tmp_path/'reports')
    from lottery_assistant import cloud_research
    monkeypatch.setattr(cloud_research,'discover_github_candidates',lambda:[])
    state={'sync_fail':False,'model_calls':0,'sync_calls':0}
    def sync(lottery, periods):
        state['sync_calls']+=1
        if state['sync_fail']: raise RuntimeError('official unavailable')
        return 500
    def recommend(lottery, now, clock):
        state['model_calls']+=1
        # Real recommend() returns an existing immutable freeze before training.
        existing=db.get_frozen_recommendation(lottery,now.date().isoformat())
        if existing: return existing
        pid=db.add_prediction(lottery,'NEXT_AFTER_2026123',[1,2,3,4,5,6],[1],'test',0,{})
        rec={'prediction_id':pid,'lottery':lottery,'basis_issue':'2026123',
             'target_draw_date':now.date().isoformat(),'frozen_at':now.isoformat(),
             'model_version':'test','main':[1,2,3,4,5,6],'bonus':[1]}
        db.freeze_prediction(pid,digest(rec),rec,rec['target_draw_date'],rec['basis_issue'],rec['frozen_at'])
        return rec
    monkeypatch.setattr(cloud,'sync',sync)
    monkeypatch.setattr(cloud,'recommend',recommend)
    yield db,state
    db.conn.close()


def at(hour,minute=0,day=29):
    return datetime(2026,10,day,hour,minute,tzinfo=TZ)


def readiness(run,lottery='ssq'):
    return next(a for a in run.actions if a['job']==f'delivery-readiness-{lottery}')


def test_morning_freeze_is_reused_at_1530_and_late_retries(cycle):
    db,state=cycle
    first=cloud.run_due(at(8,37))
    rec=db.get_frozen_recommendation('ssq','2026-10-29')
    assert readiness(first)['status']=='ok'
    for now in (at(14,7),at(15,30),at(15,45),at(20,2)):
        run=cloud.run_due(now)
        assert readiness(run)['details']['prediction_id']==rec['prediction_id']
        assert db.get_frozen_recommendation('ssq','2026-10-29')==rec
    assert state['model_calls']==1
    assert db.conn.execute('SELECT COUNT(*) FROM prediction_freezes').fetchone()[0]==1


def test_transient_failure_retries_before_delivery(cycle):
    db,state=cycle
    state['sync_fail']=True
    first=cloud.run_due(at(8,37))
    assert any(a['job']=='recommend-ssq' and a['status']=='error' for a in first.actions)
    assert not db.job_has_run('recommend-ssq:2026-10-29')
    state['sync_fail']=False
    second=cloud.run_due(at(15,30))
    assert readiness(second)['status']=='ok'
    assert state['model_calls']==1


def test_success_marker_without_freeze_does_not_hide_missing_result(cycle):
    db,state=cycle
    db.record_job_run('recommend-ssq:2026-10-29','ok',{'legacy_marker':True})
    run=cloud.run_due(at(15,30))
    assert readiness(run)['status']=='ok'
    assert state['model_calls']==1


def test_late_scheduler_reports_missing_freeze_without_training(cycle):
    db,state=cycle
    run=cloud.run_due(at(20,2))
    assert readiness(run)['status']=='error'
    assert readiness(run)['details']['code']=='RECOMMENDATION_MISSING'
    assert state['model_calls']==0 and state['sync_calls']==0
    assert not db.get_frozen_recommendation('ssq','2026-10-29')


def test_missing_freeze_warns_before_1600_while_retry_remains_possible(cycle):
    _,state=cycle
    state['sync_fail']=True
    run=cloud.run_due(at(15,45))
    assert readiness(run)['status']=='error'
    assert readiness(run)['details']['prediction_id'] is None


def test_holiday_has_no_generation_or_missing_alarm(cycle):
    _,state=cycle
    run=cloud.run_due(at(15,45,day=4))
    assert not any(a['job'].startswith('delivery-readiness-') for a in run.actions)
    assert state['model_calls']==0
    assert all(a.get('draw_state')=='HOLIDAY_SUSPENDED' for a in run.actions if a['job'].startswith('recommend-'))


def test_trigger_evidence_is_saved(cycle, monkeypatch):
    for key,value in {'GITHUB_EVENT_NAME':'schedule','LOTTERY_TRIGGER_SCHEDULE':'30 7 * * *',
                      'GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'2','GITHUB_SHA':'abc',
                      'LOTTERY_CHECKOUT_SHA':'def'}.items():
        monkeypatch.setenv(key,value)
    run=cloud.run_due(at(15,30))
    assert run.trigger=={'event':'schedule','schedule_utc':'30 7 * * *',
                         'run_id':'123','run_attempt':'2','event_sha':'abc','checkout_sha':'def'}


def test_workflow_has_explicit_1530_retry_and_latest_state_checkout():
    workflow=(Path(__file__).resolve().parents[1]/'.github/workflows/lottery-cloud.yml').read_text()
    assert "cron: '7,30,45 7 * * *'" in workflow
    assert 'timezone:' not in workflow
    assert 'ref: main' in workflow
    assert 'LOTTERY_TRIGGER_SCHEDULE: ${{ github.event.schedule }}' in workflow


def test_legacy_installer_cannot_overwrite_production_state_or_scheduler():
    root=Path(__file__).resolve().parents[1]
    workflow=(root/'.github/workflows/unpack.yml').read_text()
    assert 'contents: read' in workflow and 'contents: write' not in workflow
    assert 'actions/checkout' not in workflow
    assert 'unzip -o' not in workflow and 'git push' not in workflow
    assert 'exit 1' in workflow
    assert not (root/'.github/.github/workflows/unpack.yml').exists()

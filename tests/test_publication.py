"""Regression of the real 2026-10-29 freeze, plus isolated safety fixtures."""
import copy
import json
from datetime import datetime

import pytest

from chatgpt_bridge import build_bridge
from lottery_assistant.db import DB
from lottery_assistant.lifecycle import TZ, digest
from lottery_assistant.publication import publication_decision, delivery_history_status

def test_real_prediction_15_is_publishable_at_1603_despite_1406_bridge(tmp_path):
    from scripts.verify_ssq_incident import incident_db
    db, evidence = incident_db(tmp_path)
    original = db.get_frozen_recommendation('ssq', '2026-10-29')
    assert original and original['prediction_id'] == 15
    assert evidence['freeze']['payload_sha256'] == '1745f69972e363e87adffee2ccaec2362d3b32fea6413c1d8230d71da3fbe8e1'
    result = publication_decision(db, 'ssq', datetime(2026, 10, 29, 16, 3, tzinfo=TZ))
    assert original['frozen_at'].startswith('2026-10-29T14:06:23')
    assert result['status'] == 'READY'
    assert result['basis_issue'] == '2026123'
    assert result['freeze_sha256'] == digest(original)
    assert result['dedupe_key'] == 'ssq:NEXT_AFTER_2026123:2026-10-29:15'
    assert result['delivered'] is False
    assert db.get_frozen_recommendation('ssq', '2026-10-29') == original
    db.conn.close()


def formal_fixture(tmp_path):
    db = DB(tmp_path / 'data/lottery.db')
    db.upsert_draw('ssq', '2026123', '2026-10-27', [1,2,3,4,5,6], [1], 'TEST_FIXTURE')
    pid = db.add_prediction('ssq', 'NEXT_AFTER_2026123', [2,4,8,18,19,23], [5], 'test', 0, {})
    rec = {'prediction_id': pid, 'lottery': 'ssq', 'basis_issue': '2026123',
           'target_draw_date': '2026-10-29', 'frozen_at': '2026-10-29T14:06:23+08:00',
           'model_version': 'test', 'main': [2,4,8,18,19,23], 'bonus': [5]}
    db.freeze_prediction(pid, digest(rec), rec, rec['target_draw_date'], rec['basis_issue'], rec['frozen_at'])
    return db, rec


def test_stale_liveness_and_unrelated_job_error_cannot_revoke_valid_freeze(tmp_path):
    db, rec = formal_fixture(tmp_path)
    db.conn.close()
    (tmp_path / 'reports').mkdir()
    # Deliberately stale liveness (>14h) with a valid current-day DB freeze.
    (tmp_path / 'reports/latest_cloud_run.json').write_text(json.dumps({
        'now': '2026-10-28T23:00:00+08:00', 'actions': []}))
    payload = build_bridge(tmp_path, datetime(2026,10,29,16,3,tzinfo=TZ))
    assert payload['bridge_health']['status'] == 'BRIDGE_STALE'
    assert payload['ssq'] == rec
    assert payload['publications']['ssq']['status'] == 'READY'
    assert 'BRIDGE_STALE' in payload['publications']['ssq']['warnings']
    (tmp_path / 'reports/latest_cloud_run.json').write_text(json.dumps({
        'now':'2026-10-29T15:45:00+08:00',
        'actions':[{'job':'recommend-ssq','status':'error','details':{'error':'later sync failed'}}]}))
    assert build_bridge(tmp_path, datetime(2026,10,29,16,3,tzinfo=TZ))['ssq'] == rec


@pytest.mark.parametrize('when,reason', [
    ((2026,10,29,20,0),'PUBLICATION_CLOSED'),
    ((2026,10,30,16,0),'NO_DRAW_TODAY'),
    ((2026,10,4,16,0),'HOLIDAY_SUSPENDED'),
    ((2027,1,3,16,0),'RULES_UNVERIFIED'),
    ((2026,10,29,14,0),'FREEZE_TIME_INVALID'),
])
def test_date_and_deadline_checks_remain_closed(tmp_path, when, reason):
    db, _ = formal_fixture(tmp_path)
    result = publication_decision(db,'ssq',datetime(*when,tzinfo=TZ))
    assert result['status'] == 'WITHHELD'
    assert result['reason'] == reason


def test_missing_stale_basis_and_completed_draw(tmp_path):
    db, _ = formal_fixture(tmp_path)
    now = datetime(2026,10,29,16,3,tzinfo=TZ)
    assert publication_decision(db,'ssq',now.replace(day=25))['reason'] == 'RECOMMENDATION_MISSING'
    db.conn.execute("UPDATE draws SET draw_date='2026-10-25'")
    db.conn.commit()
    assert publication_decision(db,'ssq',now)['reason'] == 'BASIS_DATA_INVALID'
    db.upsert_draw('ssq','2026124','2026-10-29',[2,3,4,5,6,7],[2],'TEST_FIXTURE')
    assert publication_decision(db,'ssq',now)['reason'] == 'DRAW_COMPLETED'


def test_modified_prediction_is_rejected_even_if_hash_looks_valid(tmp_path):
    db, _ = formal_fixture(tmp_path)
    db.conn.execute('DROP TRIGGER frozen_prediction_no_update')
    db.conn.execute("UPDATE predictions SET model_version='tampered'")
    db.conn.commit()
    assert publication_decision(db,'ssq',datetime(2026,10,29,16,3,tzinfo=TZ))['reason'] == 'FREEZE_INVALID'


def test_delivery_dedup_uses_issue_and_prediction_and_requires_actual_history(tmp_path):
    db, _ = formal_fixture(tmp_path)
    publication = publication_decision(db,'ssq',datetime(2026,10,29,16,3,tzinfo=TZ))
    assert delivery_history_status(publication, None) == 'UNKNOWN'
    assert delivery_history_status(publication, []) == 'NOT_DELIVERED'
    assert delivery_history_status(publication, [publication]) == 'ALREADY_DELIVERED'
    changed_pid = copy.deepcopy(publication); changed_pid.update(prediction_id=99,dedupe_key='different')
    assert delivery_history_status(publication, [changed_pid]) == 'ALREADY_DELIVERED'
    same_pid = {'lottery':'ssq','prediction_id':publication['prediction_id']}
    assert delivery_history_status(publication, [same_pid]) == 'ALREADY_DELIVERED'
    other = {'lottery':'ssq','prediction_id':999,'target_draw_date':'2026-10-27','target_issue_key':'NEXT_AFTER_2026122'}
    assert delivery_history_status(publication, [other]) == 'NOT_DELIVERED'


def test_only_actual_same_lottery_data_conflict_revokes_frozen_record(tmp_path):
    db, _ = formal_fixture(tmp_path)
    now = datetime(2026,10,29,16,3,tzinfo=TZ)
    db.block_data_quality('dlt','conflict in other lottery',{'issue':'26123'})
    assert publication_decision(db,'ssq',now)['status'] == 'READY'
    db.block_data_quality('ssq','official numbers disagree',{'issue':'2026123'})
    result = publication_decision(db,'ssq',now)
    assert result['reason'] == 'DATA_QUALITY_CONFLICT'
    assert result['data_quality_conflict']['status'] == 'BLOCKED'


def test_malformed_or_future_cloud_timestamp_cannot_invalidate_formal_freeze(tmp_path):
    db, rec = formal_fixture(tmp_path); db.conn.close()
    (tmp_path/'reports').mkdir()
    for value in ('not-a-time','2026-10-29T23:00:00+08:00'):
        (tmp_path/'reports/latest_cloud_run.json').write_text(json.dumps({'now':value,'actions':[]}))
        result=build_bridge(tmp_path,datetime(2026,10,29,16,3,tzinfo=TZ))
        assert result['bridge_health']['status']=='BRIDGE_STALE'
        assert result['publications']['ssq']['status']=='READY'
        assert result['ssq']==rec

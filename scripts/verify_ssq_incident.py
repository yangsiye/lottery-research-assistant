"""Replay the recorded incident; never read or write the production database."""
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from chatgpt_bridge import build_bridge
from lottery_assistant.db import DB
from lottery_assistant.lifecycle import TZ


def incident_db(root):
    evidence=json.loads((ROOT/'tests/fixtures/ssq_20261029_incident.json').read_text())
    freeze=evidence['freeze'];rec=freeze['payload_json'];basis=evidence['basis_draw']
    db=DB(root/'data/lottery.db')
    db.upsert_draw('ssq',basis['issue'],basis['draw_date'],basis['main_numbers'],basis['bonus_numbers'],
                   basis['source'],basis['prize_data'])
    db.conn.execute('''INSERT INTO predictions(id,lottery,issue,main_numbers,bonus_numbers,model_version,model_score,rationale)
        VALUES(?,?,?,?,?,?,?,?)''',(rec['prediction_id'],'ssq',f"NEXT_AFTER_{rec['basis_issue']}",
        json.dumps(rec['main']),json.dumps(rec['bonus']),rec['model_version'],rec['model_score'],json.dumps(rec['rationale'])))
    db.conn.commit()
    db.freeze_prediction(rec['prediction_id'],freeze['payload_sha256'],rec,rec['target_draw_date'],
                         rec['basis_issue'],rec['frozen_at'])
    return db,evidence


def replay():
    with tempfile.TemporaryDirectory(prefix='ssq-incident-') as directory:
        root=Path(directory)
        db,evidence=incident_db(root);db.checkpoint();db.conn.close()
        (root/'reports').mkdir()
        (root/'reports/latest_cloud_run.json').write_text(json.dumps({'now':evidence['cloud_now'],'actions':[]}))
        payload=build_bridge(root,datetime(2026,10,29,16,3,tzinfo=TZ))
        decision=payload['publications']['ssq']
        assert decision['status']=='READY'
        assert decision['freeze_sha256']=='1745f69972e363e87adffee2ccaec2362d3b32fea6413c1d8230d71da3fbe8e1'
        return {'mode':'HISTORICAL_REPLAY_NOT_DELIVERY','source_commit':evidence['source_commit'],
                'bridge_health':payload['bridge_health'],'publication':decision,
                'same_snapshot':payload['ssq']==evidence['freeze']['payload_json'],
                'production_database_opened':False,'numbers_generated':False,'numbers_sent':False}


if __name__=='__main__':
    print(json.dumps(replay(),ensure_ascii=False,indent=2))

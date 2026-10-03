from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .db import DB
from .engine import DB_PATH, sync, recommend

TZ = ZoneInfo('Asia/Shanghai')
ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / 'reports'
REPORT_DIR.mkdir(parents=True, exist_ok=True)

# Beijing weekday: Monday=0 ... Sunday=6
DRAW_DAYS = {
    'dlt': {0, 2, 5},   # Mon/Wed/Sat
    'ssq': {1, 3, 6},   # Tue/Thu/Sun
}

@dataclass
class RunResult:
    now: str
    actions: list[dict]


def _job_key(name: str, now: datetime) -> str:
    return f"{name}:{now.date().isoformat()}"


def _already_ran(db: DB, key: str) -> bool:
    return db.job_has_run(key)


def _mark(db: DB, key: str, status: str, details: dict):
    db.record_job_run(key, status, details)


def _write_report(name: str, payload: dict):
    path = REPORT_DIR / name
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    return str(path)


def _review_new_predictions(db: DB, lottery: str) -> list[dict]:
    reviewed=[]
    draws=db.get_draws(lottery)
    by_issue={d['issue']:i for i,d in enumerate(draws)}
    for p in db.get_unreviewed_predictions(lottery):
        issue=str(p.get('issue') or '')
        if not issue.startswith('NEXT_AFTER_'):
            continue
        basis=issue[len('NEXT_AFTER_'):]
        idx=by_issue.get(basis)
        if idx is None or idx+1 >= len(draws):
            continue
        actual=draws[idx+1]
        main=set(json.loads(p['main_numbers']))
        bonus=set(json.loads(p['bonus_numbers']))
        mh=len(main & set(actual['main_numbers']))
        bh=len(bonus & set(actual['bonus_numbers']))
        db.add_prediction_result(p['id'], actual['issue'], mh, bh)
        item={
            'prediction_id':p['id'], 'lottery':lottery,
            'basis_issue':basis, 'actual_issue':actual['issue'],
            'predicted_main':sorted(main), 'predicted_bonus':sorted(bonus),
            'actual_main':actual['main_numbers'], 'actual_bonus':actual['bonus_numbers'],
            'main_hits':mh, 'bonus_hits':bh,
            'model_version':p['model_version'],
        }
        db.log('review', item, lottery)
        reviewed.append(item)
    return reviewed


def run_due(now: datetime | None = None, force: bool = False) -> RunResult:
    """Run cloud jobs due at the current Beijing time.

    Intended to be invoked by a cloud scheduler at the configured Beijing-time slots. Idempotency
    is persisted in SQLite, so reruns/restarts are safe.
    """
    now = (now or datetime.now(TZ)).astimezone(TZ)
    db = DB(DB_PATH)
    actions=[]

    # Daily health/data refresh at 08:30.
    if force or now.hour == 8:
        key=_job_key('morning-sync', now)
        if force or not _already_ran(db,key):
            result={}
            try:
                from .cloud_research import discover_github_candidates
                result['research']={'github_candidates':discover_github_candidates()}
            except Exception as e:
                result['research']={'error':str(e)}
            for lot in ('ssq','dlt'):
                try:
                    result[lot]={'synced':sync(lot,500)}
                except Exception as e:
                    result[lot]={'error':str(e)}
            sync_parts=[result.get('ssq',{}),result.get('dlt',{})]
            status='ok' if all('synced' in x for x in sync_parts) else 'partial'
            _mark(db,key,status,result)
            actions.append({'job':'morning-sync','status':status,'details':result})

    # Draw-day recommendation at 15:30.
    if force or now.hour == 15:
        for lot,days in DRAW_DAYS.items():
            if not force and now.weekday() not in days:
                continue
            key=_job_key(f'recommend-{lot}', now)
            if force or not _already_ran(db,key):
                try:
                    sync(lot,500)
                    rec=recommend(lot)
                    _mark(db,key,'ok',rec)
                    _write_report(f'latest_{lot}_recommendation.json',rec)
                    actions.append({'job':f'recommend-{lot}','status':'ok','details':rec})
                except Exception as e:
                    detail={'error':str(e)}
                    _mark(db,key,'error',detail)
                    actions.append({'job':f'recommend-{lot}','status':'error','details':detail})

    # Nightly sync + review at 23:00, after results should normally be published.
    if force or now.hour == 23:
        key=_job_key('night-review', now)
        if force or not _already_ran(db,key):
            result={}
            try:
                from .cloud_research import discover_github_candidates
                result['research']={'github_candidates':discover_github_candidates()}
            except Exception as e:
                result['research']={'error':str(e)}
            for lot in ('ssq','dlt'):
                try:
                    sync(lot,500)
                    result[lot]={'reviews':_review_new_predictions(db,lot)}
                except Exception as e:
                    result[lot]={'error':str(e)}
            status='ok' if all('reviews' in result.get(lot,{}) for lot in ('ssq','dlt')) else 'partial'
            _mark(db,key,status,result)
            _write_report('latest_review.json',result)
            actions.append({'job':'night-review','status':status,'details':result})

    payload={'now':now.isoformat(),'actions':actions}
    _write_report('latest_cloud_run.json',payload)
    return RunResult(now=now.isoformat(), actions=actions)


def main():
    res=run_due()
    print(json.dumps({'now':res.now,'actions':res.actions},ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()

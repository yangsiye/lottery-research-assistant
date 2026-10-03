from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .db import DB
from .engine import DB_PATH, sync, recommend
from .rules import DRAW_DAYS, draw_status

TZ = ZoneInfo('Asia/Shanghai')
ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / 'reports'
REPORT_DIR.mkdir(parents=True, exist_ok=True)

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
        if not issue.startswith('NEXT_AFTER_'): continue
        basis=issue[len('NEXT_AFTER_'):]
        idx=by_issue.get(basis)
        if idx is None or idx+1 >= len(draws): continue
        actual=draws[idx+1]
        main=set(json.loads(p['main_numbers'])); bonus=set(json.loads(p['bonus_numbers']))
        mh=len(main & set(actual['main_numbers'])); bh=len(bonus & set(actual['bonus_numbers']))
        db.add_prediction_result(p['id'], actual['issue'], mh, bh)
        item={'prediction_id':p['id'],'lottery':lottery,'basis_issue':basis,'actual_issue':actual['issue'],
              'predicted_main':sorted(main),'predicted_bonus':sorted(bonus),
              'actual_main':actual['main_numbers'],'actual_bonus':actual['bonus_numbers'],
              'main_hits':mh,'bonus_hits':bh,'model_version':p['model_version']}
        db.log('review',item,lottery); reviewed.append(item)
    return reviewed

def run_due(now: datetime | None = None, force: bool = False) -> RunResult:
    now=(now or datetime.now(TZ)).astimezone(TZ)
    db=DB(DB_PATH); actions=[]

    if force or now.hour == 8:
        key=_job_key('morning-sync',now)
        if force or not _already_ran(db,key):
            result={}
            try:
                from .cloud_research import discover_github_candidates
                result['research']={'github_candidates':discover_github_candidates()}
            except Exception as e: result['research']={'error':str(e)}
            for lot in ('ssq','dlt'):
                try: result[lot]={'synced':sync(lot,500)}
                except Exception as e: result[lot]={'error':str(e)}
            status='ok' if all('synced' in result.get(l,{}) for l in ('ssq','dlt')) else 'partial'
            _mark(db,key,status,result); actions.append({'job':'morning-sync','status':status,'details':result})

    if force or now.hour == 15:
        for lot in DRAW_DAYS:
            calendar=draw_status(lot,now.date())
            if calendar['status'] != 'WAITING_DRAW':
                actions.append({'job':f'recommend-{lot}','status':'skipped','draw_state':calendar['status'],'details':calendar})
                continue
            key=_job_key(f'recommend-{lot}',now)
            if force or not _already_ran(db,key):
                try:
                    sync(lot,500); rec=recommend(lot)
                    _mark(db,key,'ok',rec); _write_report(f'latest_{lot}_recommendation.json',rec)
                    actions.append({'job':f'recommend-{lot}','status':'ok','draw_state':'WAITING_DRAW','details':rec})
                except Exception as e:
                    detail={'error':str(e)}; _mark(db,key,'error',detail)
                    actions.append({'job':f'recommend-{lot}','status':'error','draw_state':'BACKEND_ERROR','details':detail})

    if force or now.hour == 23:
        key=_job_key('night-review',now)
        if force or not _already_ran(db,key):
            result={'calendar':{}}
            try:
                from .cloud_research import discover_github_candidates
                result['research']={'github_candidates':discover_github_candidates()}
            except Exception as e: result['research']={'error':str(e)}
            for lot in ('ssq','dlt'):
                calendar=draw_status(lot,now.date()); result['calendar'][lot]=calendar
                if calendar['status'] in ('HOLIDAY_SUSPENDED','NO_DRAW_TODAY'):
                    result[lot]={'draw_state':calendar['status'],'reviews':[],'reason':calendar['reason']}
                    continue
                try:
                    sync(lot,500); reviews=_review_new_predictions(db,lot)
                    state='DRAW_COMPLETED' if reviews else 'WAITING_DRAW'
                    result[lot]={'draw_state':state,'reviews':reviews,
                                 'reason':'已同步新期开奖并完成复盘' if reviews else '开奖日，但尚未发现可对应的新官方开奖结果/冻结预测'}
                except Exception as e:
                    result[lot]={'draw_state':'BACKEND_ERROR','error':str(e)}
            status='ok' if all(result.get(l,{}).get('draw_state')!='BACKEND_ERROR' for l in ('ssq','dlt')) else 'partial'
            _mark(db,key,status,result); _write_report('latest_review.json',result)
            actions.append({'job':'night-review','status':status,'details':result})

    payload={'now':now.isoformat(),'actions':actions}
    _write_report('latest_cloud_run.json',payload)
    return RunResult(now=now.isoformat(),actions=actions)

def main():
    res=run_due(); print(json.dumps({'now':res.now,'actions':res.actions},ensure_ascii=False,indent=2))

if __name__=='__main__': main()

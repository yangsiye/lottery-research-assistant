from __future__ import annotations
import json
from dataclasses import dataclass
from datetime import datetime, date, time
from pathlib import Path
from .db import DB
from .engine import DB_PATH, CONFIG, sync, recommend
from .rules import draw_status
from .lifecycle import TZ, digest, before_deadline, timestamp
from .governance import attribute_prediction
from .evaluator import evaluate_official

ROOT=Path(__file__).resolve().parents[1]
REPORT_DIR=ROOT/'reports'

@dataclass
class RunResult:
    now: str
    actions: list[dict]


def _write_report(name,payload):
    REPORT_DIR.mkdir(parents=True,exist_ok=True)
    path=REPORT_DIR/name
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    temporary.replace(path)


def _review_new_predictions(db,lottery,now=None):
    now=(now or datetime.now(TZ)).astimezone(TZ)
    reviewed=[]
    draws=db.get_draws(lottery)
    by_issue={d['issue']:i for i,d in enumerate(draws)}
    for p in db.get_unreviewed_predictions(lottery):
        freeze=db.get_prediction_freeze(p['id'])
        if not freeze: continue  # Legacy/unfrozen rows are never relabelled as forward predictions.
        payload=freeze['payload_json']
        target=date.fromisoformat(freeze['target_draw_date'])
        idx=by_issue.get(freeze['basis_issue'])
        if idx is None or idx+1>=len(draws): continue
        actual=draws[idx+1]
        if actual['draw_date']!=target.isoformat():
            db.log('review-blocked',{'prediction_id':p['id'],'reason':'target date differs from next official draw'},lottery)
            continue
        if target>now.date(): continue
        if target==now.date() and now.time().replace(tzinfo=None)<time.fromisoformat(CONFIG[lottery]['draw_time']): continue
        if (digest(payload)!=freeze['payload_sha256'] or not before_deadline(freeze['frozen_at'],target)
            or payload.get('frozen_at')!=freeze['frozen_at'] or payload.get('basis_issue')!=freeze['basis_issue']
            or payload.get('target_draw_date')!=freeze['target_draw_date']
            or payload.get('lottery')!=lottery or payload.get('prediction_id')!=p['id']
            or payload.get('main')!=json.loads(p['main_numbers']) or payload.get('bonus')!=json.loads(p['bonus_numbers'])):
            db.log('review-blocked',{'prediction_id':p['id'],'reason':'freeze integrity/time check failed'},lottery)
            continue
        outcome=evaluate_official(lottery,payload['main'],payload['bonus'],actual)
        attribution=attribute_prediction(payload,actual,CONFIG[lottery])
        item={'prediction_id':p['id'],'lottery':lottery,'basis_issue':freeze['basis_issue'],
              'target_draw_date':target.isoformat(),'actual_issue':actual['issue'],
              'predicted_main':payload['main'],'predicted_bonus':payload['bonus'],
              'actual_main':actual['main_numbers'],'actual_bonus':actual['bonus_numbers'],
              'model_version':p['model_version'],'freeze_sha256':freeze['payload_sha256'],
              **outcome,'model_attribution':attribution,
              'governance_action':'保持；单期结果仅增加前向样本，不触发模型晋级。下次训练更新滚动验证和留出门槛。'}
        db.add_prediction_result(p['id'],actual['issue'],outcome['main_hits'],outcome['bonus_hits'],item)
        db.log('review',item,lottery)
        reviewed.append(item)
    return reviewed


def run_due(now=None,force=False):
    now=(now or datetime.now(TZ)).astimezone(TZ)
    db=DB(DB_PATH)
    calendar={lot:draw_status(lot,now.date()) for lot in ('ssq','dlt')}
    actions=[{'job':'calendar-status','status':'ok','details':calendar}]
    local_time=now.time().replace(tzinfo=None)
    # Jobs stay due after their scheduled minute; failures are retryable within the same day.
    morning_due=local_time>=time(8,30)
    empty=any(not db.get_draws(lot) for lot in ('ssq','dlt'))
    key=f'morning-sync:{now.date()}'
    if (morning_due or empty or force) and (force or not db.job_has_run(key)):
        result={}
        try:
            from .cloud_research import discover_github_candidates
            result['research']={'github_candidates':discover_github_candidates()}
        except Exception as e: result['research']={'error':str(e)}
        for lot in ('ssq','dlt'):
            try:
                result[lot]={'synced':sync(lot,500)}
                result[lot]['reviews']=_review_new_predictions(db,lot,now)
            except Exception as e: result[lot]={'error':str(e)}
        # A late official result is reviewed on the next successful sync, including non-draw days.
        if any(result[lot].get('reviews') for lot in ('ssq','dlt')):
            catchup={'as_of':now.isoformat(),'calendar':calendar}
            for lot in ('ssq','dlt'):
                completed=any(d['draw_date']==now.date().isoformat() for d in db.get_draws(lot))
                state='DRAW_COMPLETED' if completed and calendar[lot]['status']=='WAITING_DRAW' else calendar[lot]['status']
                catchup[lot]={'draw_state':state,'reviews':result[lot].get('reviews',[]),
                              'reason':'补齐此前已冻结推荐的官方对奖；当日状态按实际开奖日历显示'}
            _write_report('latest_review.json',catchup)
        status='ok' if all('synced' in result[l] for l in ('ssq','dlt')) else 'partial'
        db.record_job_run(key,status,result)
        actions.append({'job':'morning-sync','status':status,'details':result})
    if force or time(14,0)<=local_time<time(20):
        for lot in ('ssq','dlt'):
            if calendar[lot]['status']!='WAITING_DRAW':
                actions.append({'job':f'recommend-{lot}','status':'skipped','draw_state':calendar[lot]['status'],'details':calendar[lot]})
                continue
            key=f'recommend-{lot}:{now.date()}'
            if not force and db.job_has_run(key): continue
            try:
                if not db.get_frozen_recommendation(lot,now.date().isoformat()): sync(lot,500)
                rec=recommend(lot,now=now,clock=lambda:datetime.now(TZ))
                status='ok'; detail=rec
                _write_report(f'latest_{lot}_recommendation.json',rec)
            except Exception as e:
                status='error';detail={'error':str(e)}
            db.record_job_run(key,status,detail)
            actions.append({'job':f'recommend-{lot}','status':status,'details':detail})
    if force or local_time>=time(23):
        key=f'night-review:{now.date()}'
        if force or not db.job_has_run(key):
            result={'as_of':now.isoformat(),'calendar':calendar}
            for lot in ('ssq','dlt'):
                if calendar[lot]['status']!='WAITING_DRAW':
                    result[lot]={'draw_state':calendar[lot]['status'],'reviews':[],'reason':calendar[lot]['reason']}
                    continue
                try:
                    sync(lot,500)
                    reviews=_review_new_predictions(db,lot,now)
                    completed=any(d['draw_date']==now.date().isoformat() for d in db.get_draws(lot))
                    result[lot]={'draw_state':'DRAW_COMPLETED' if completed else 'WAITING_DRAW','reviews':reviews,
                                 'reason':'官方开奖结果已入库' if completed else '未发现当日官方结果，保持等待并允许重试',
                                 'prediction_available':bool(db.get_frozen_recommendation(lot,now.date().isoformat()))}
                except Exception as e:
                    result[lot]={'draw_state':'BACKEND_ERROR','reviews':[],'error':str(e)}
            status='ok' if all(result[l]['draw_state'] not in ('BACKEND_ERROR','WAITING_DRAW') for l in ('ssq','dlt')) else 'partial'
            db.record_job_run(key,status,result)
            _write_report('latest_review.json',result)
            actions.append({'job':'night-review','status':status,'details':result})
    payload={'now':now.isoformat(),'actions':actions}
    _write_report('latest_cloud_run.json',payload)
    db.checkpoint()
    return RunResult(**payload)


def main():
    res=run_due()
    print(json.dumps({'now':res.now,'actions':res.actions},ensure_ascii=False,indent=2))
    return 1 if any(a['status'] in ('error','partial') for a in res.actions) else 0

if __name__=='__main__':
    raise SystemExit(main())

"""Build machine-only ChatGPT payloads; stale reports cannot replace today's state."""
from __future__ import annotations
import json
from datetime import datetime, timedelta
from pathlib import Path
from lottery_assistant.db import DB
from lottery_assistant.rules import draw_status
from lottery_assistant.lifecycle import TZ, timestamp, digest, before_deadline

ROOT=Path(__file__).resolve().parent
FRONTEND=('Check bridge_health and draw_states first. HOLIDAY_SUSPENDED/NO_DRAW_TODAY are normal. '
          'Only publish a current verified frozen recommendation. Only push new official reviews. '
          'Never treat model_score as winning probability. Explain BACKEND_ERROR/BRIDGE_STALE/data errors. '
          'User interaction and results stay in ChatGPT.')


def build_bridge(root=ROOT,now=None):
    now=(now or datetime.now(TZ)).astimezone(TZ)
    reports=root/'reports'; bridge=root/'bridge'; bridge.mkdir(parents=True,exist_ok=True)
    def load(name):
        try: return json.loads((reports/name).read_text(encoding='utf-8'))
        except (FileNotFoundError,ValueError): return None
    cloud=load('latest_cloud_run.json');review=load('latest_review.json')
    db=DB(root/'data/lottery.db')
    age=None
    if cloud and cloud.get('now'):
        age=(now-timestamp(cloud['now'])).total_seconds()
    healthy=age is not None and 0<=age<=14*3600
    states={lot:{**draw_status(lot,now.date()),'as_of_date':now.date().isoformat()} for lot in ('ssq','dlt')}
    # Report overrides are valid only for the current local date.
    current_review=review if review and review.get('as_of') and timestamp(review['as_of']).astimezone(TZ).date()==now.date() else None
    if current_review:
        for lot in states:
            detail=current_review.get(lot,{})
            if states[lot]['status']=='WAITING_DRAW' and detail.get('draw_state'):
                states[lot].update(status=detail['draw_state'],reason=detail.get('reason') or detail.get('error'))
    current_cloud=cloud if cloud and timestamp(cloud['now']).astimezone(TZ).date()==now.date() else None
    if current_cloud:
        for action in current_cloud.get('actions',[]):
            for lot in states:
                if action['job']==f'recommend-{lot}' and action['status']=='error' and states[lot]['status']=='WAITING_DRAW':
                    states[lot].update(status='BACKEND_ERROR',reason=action['details']['error'])
    recs={};data_health={}
    for lot in states:
        draws=db.get_draws(lot)
        data_health[lot]={'rows':len(draws),'latest_issue':draws[-1]['issue'] if draws else None,
                          'latest_draw_date':draws[-1]['draw_date'] if draws else None,
                          'source_validation':'single-official-source' if draws else 'no-verified-data',
                          'sources':sorted({d['source'] for d in draws}),
                          'primary_source_error':(draws[-1]['prize_data'].get('primary_source_error') if draws else None)}
        rec=db.get_frozen_recommendation(lot,now.date().isoformat())
        valid=False
        if rec:
            freeze=db.get_prediction_freeze(rec['prediction_id'])
            valid=digest(rec)==freeze['payload_sha256'] and before_deadline(freeze['frozen_at'],now.date())
        recs[lot]=rec if valid and healthy and states[lot]['status']=='WAITING_DRAW' else None
    recent=[]
    for row in db.conn.execute('SELECT details FROM prediction_results WHERE details IS NOT NULL ORDER BY reviewed_at DESC LIMIT 20'):
        recent.append(json.loads(row['details']))
    research=[dict(r) for r in db.conn.execute('SELECT discovered_at,name,source_url,hypothesis,decision FROM research_candidates ORDER BY id DESC LIMIT 20')]
    model_states=[dict(r) for r in db.conn.execute('''SELECT lottery,model_name,model_version,status,weight,train_end
        FROM model_runs WHERE id IN (SELECT MAX(id) FROM model_runs GROUP BY lottery,model_name)''')]
    errors=[a for a in (current_cloud or {}).get('actions',[]) if a['status'] in ('partial','error')]
    payload={'schema_version':'1.2','generated_at':now.isoformat(),
             'bridge_health':{'status':'CURRENT' if healthy else 'BRIDGE_STALE','cloud_age_seconds':age,'job_errors':errors},
             'draw_states':states,'data_health':data_health,**recs,
             'latest_review':current_review,'latest_cloud_run':cloud,'recent_reviews':recent,
             'research_candidates':research,'model_states':model_states,'frontend_instruction':FRONTEND}
    def write(name,value):
        path=bridge/name;temporary=path.with_suffix('.tmp')
        temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8');temporary.replace(path)
    write('latest.json',payload)
    for lot in states:
        write(f'{lot}.json',{'schema_version':'1.2','generated_at':now.isoformat(),'bridge_health':payload['bridge_health'],
                            'draw_state':states[lot],'data_health':data_health[lot],'recommendation':recs[lot]})
    write('review.json',{k:payload[k] for k in ('schema_version','generated_at','bridge_health','draw_states','latest_review','recent_reviews','frontend_instruction')})
    write('research.json',{'generated_at':now.isoformat(),'candidates':research,'model_states':model_states})
    db.checkpoint()
    db.conn.close()
    return payload

if __name__=='__main__':
    build_bridge()
    print(ROOT/'bridge/latest.json')

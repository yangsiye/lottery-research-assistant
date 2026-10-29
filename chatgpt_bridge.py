"""Build machine-only ChatGPT payloads; stale reports cannot replace today's state."""
from __future__ import annotations
import json
from datetime import datetime, timedelta
from pathlib import Path
from lottery_assistant.db import DB
from lottery_assistant.rules import draw_status
from lottery_assistant.lifecycle import TZ, timestamp
from lottery_assistant.publication import publication_decision

ROOT=Path(__file__).resolve().parent
FRONTEND=('Read ssq.json and latest.json from the same main commit. Use publication/publications for eligibility. '
          'READY requires current local date, identical freeze hashes and now < valid_until. '
          'Bridge liveness is diagnostic: do not impose a post-15:30 run or an arbitrary age veto on a verified freeze. '
          'Check delivery history by lottery + target_issue_key/target_draw_date and prediction_id/dedupe_key; '
          'recent_reviews are NOT delivery receipts. Never invent numbers or reuse an old target. '
          'HOLIDAY_SUSPENDED/NO_DRAW_TODAY are normal. Never treat model_score as winning probability. '
          'Report missing output and data failures explicitly; READY is not proof of delivery.')


def build_bridge(root=ROOT,now=None):
    now=(now or datetime.now(TZ)).astimezone(TZ)
    reports=root/'reports'; bridge=root/'bridge'; bridge.mkdir(parents=True,exist_ok=True)
    def load(name):
        try: return json.loads((reports/name).read_text(encoding='utf-8'))
        except (FileNotFoundError,ValueError): return None
    cloud=load('latest_cloud_run.json');review=load('latest_review.json')
    db=DB(root/'data/lottery.db')
    age=None
    def report_time(report,key):
        try: return timestamp(report[key]).astimezone(TZ) if isinstance(report,dict) else None
        except (KeyError,TypeError,ValueError,OverflowError): return None
    cloud_time=report_time(cloud,'now')
    if cloud_time:
        age=(now-cloud_time).total_seconds()
    healthy=age is not None and 0<=age<=14*3600
    states={lot:{**draw_status(lot,now.date()),'as_of_date':now.date().isoformat()} for lot in ('ssq','dlt')}
    # Report overrides are valid only for the current local date.
    review_time=report_time(review,'as_of')
    current_review=review if review_time and review_time.date()==now.date() and review_time<=now else None
    if current_review:
        for lot in states:
            detail=current_review.get(lot,{})
            if states[lot]['status']=='WAITING_DRAW' and detail.get('draw_state'):
                states[lot].update(status=detail['draw_state'],reason=detail.get('reason') or detail.get('error'))
    current_cloud=cloud if cloud_time and cloud_time.date()==now.date() and cloud_time<=now else None
    if current_cloud:
        for action in current_cloud.get('actions',[]):
            for lot in states:
                if action['job']==f'recommend-{lot}' and action['status']=='error' and states[lot]['status']=='WAITING_DRAW':
                    states[lot].update(status='BACKEND_ERROR',reason=action['details']['error'])
    recs={};data_health={};publications={}
    for lot in states:
        draws=db.get_draws(lot)
        data_health[lot]={'rows':len(draws),'latest_issue':draws[-1]['issue'] if draws else None,
                          'latest_draw_date':draws[-1]['draw_date'] if draws else None,
                          'source_validation':'single-official-source' if draws else 'no-verified-data',
                          'sources':sorted({d['source'] for d in draws}),
                          'primary_source_error':(draws[-1]['prize_data'].get('primary_source_error') if draws else None)}
        data_health[lot]['quality_flag']=db.get_data_quality_flag(lot)
        publication=publication_decision(db,lot,now,states[lot])
        if publication['status']=='READY':
            # An unrelated/failed refresh does not revoke an existing immutable freeze.
            states[lot].update(status='WAITING_DRAW',reason='当日正式冻结记录已核验；桥接运行健康单独报告')
            if not healthy: publication['warnings'].append('BRIDGE_STALE')
        elif publication['reason']=='DRAW_COMPLETED':
            states[lot].update(status='DRAW_COMPLETED',reason='当日官方结果已入库')
        publications[lot]=publication
        recs[lot]=db.get_frozen_recommendation(lot,now.date().isoformat()) if publication['status']=='READY' else None
    recent=[]
    for row in db.conn.execute('SELECT details FROM prediction_results WHERE details IS NOT NULL ORDER BY reviewed_at DESC LIMIT 20'):
        recent.append(json.loads(row['details']))
    research=[dict(r) for r in db.conn.execute('SELECT discovered_at,name,source_url,hypothesis,decision FROM research_candidates ORDER BY id DESC LIMIT 20')]
    model_states=[dict(r) for r in db.conn.execute('''SELECT lottery,model_name,model_version,status,weight,train_end
        FROM model_runs WHERE id IN (SELECT MAX(id) FROM model_runs GROUP BY lottery,model_name)''')]
    errors=[a for a in (current_cloud or {}).get('actions',[]) if a['status'] in ('partial','error')]
    payload={'schema_version':'1.3','generated_at':now.isoformat(),
             'bridge_health':{'status':'CURRENT' if healthy else 'BRIDGE_STALE','cloud_age_seconds':age,'job_errors':errors},
             'draw_states':states,'data_health':data_health,'publications':publications,**recs,
             'latest_review':current_review,'latest_cloud_run':cloud,'recent_reviews':recent,
             'research_candidates':research,'model_states':model_states,'frontend_instruction':FRONTEND}
    def write(name,value):
        path=bridge/name;temporary=path.with_suffix('.tmp')
        temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8');temporary.replace(path)
    write('latest.json',payload)
    for lot in states:
        write(f'{lot}.json',{'schema_version':'1.3','generated_at':now.isoformat(),'bridge_health':payload['bridge_health'],
                            'draw_state':states[lot],'data_health':data_health[lot],
                            'publication':publications[lot],'recommendation':recs[lot]})
    write('review.json',{k:payload[k] for k in ('schema_version','generated_at','bridge_health','draw_states','latest_review','recent_reviews','frontend_instruction')})
    write('research.json',{'generated_at':now.isoformat(),'candidates':research,'model_states':model_states})
    db.checkpoint()
    db.conn.close()
    return payload

if __name__=='__main__':
    build_bridge()
    print(ROOT/'bridge/latest.json')

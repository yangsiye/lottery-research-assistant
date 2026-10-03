from __future__ import annotations
import json, sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parent; DB=ROOT/'data'/'lottery.db'; REPORTS=ROOT/'reports'; BRIDGE=ROOT/'bridge'
BRIDGE.mkdir(exist_ok=True); TZ=ZoneInfo('Asia/Shanghai')

def load_json(name):
    p=REPORTS/name
    if not p.exists(): return None
    try: return json.loads(p.read_text(encoding='utf-8'))
    except Exception: return None

def rows(sql,params=()):
    if not DB.exists(): return []
    con=sqlite3.connect(DB); con.row_factory=sqlite3.Row
    try: return [dict(r) for r in con.execute(sql,params).fetchall()]
    except Exception: return []
    finally: con.close()

def write(name,payload):
    (BRIDGE/name).write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')

now=datetime.now(TZ).isoformat(); ssq=load_json('latest_ssq_recommendation.json'); dlt=load_json('latest_dlt_recommendation.json')
review=load_json('latest_review.json'); cloud=load_json('latest_cloud_run.json')
research=rows("SELECT discovered_at,name,source_url,hypothesis,decision FROM research_candidates ORDER BY id DESC LIMIT 20")
recent_reviews=rows("""SELECT p.lottery,p.issue,p.main_numbers,p.bonus_numbers,p.model_version,r.actual_issue,r.main_hits,r.bonus_hits,r.reviewed_at
FROM prediction_results r JOIN predictions p ON p.id=r.prediction_id ORDER BY r.reviewed_at DESC LIMIT 20""")
draw_states=(review or {}).get('calendar',{})
for lot in ('ssq','dlt'):
    if review and isinstance(review.get(lot),dict) and review[lot].get('draw_state'):
        draw_states[lot]={**draw_states.get(lot,{}),'status':review[lot]['draw_state'],'reason':review[lot].get('reason') or draw_states.get(lot,{}).get('reason')}

frontend='Use draw_states before interpreting null reviews. HOLIDAY_SUSPENDED/NO_DRAW_TODAY are normal states, not backend failures. DRAW_COMPLETED may be pushed; WAITING_DRAW means do not invent results; BACKEND_ERROR/BRIDGE_STALE must be reported explicitly. Present results in ChatGPT; do not direct the user to a web dashboard.'
write('latest.json',{'schema_version':'1.1','generated_at':now,'draw_states':draw_states,'ssq':ssq,'dlt':dlt,'latest_review':review,'latest_cloud_run':cloud,'recent_reviews':recent_reviews,'research_candidates':research,'frontend_instruction':frontend})
write('ssq.json',{'generated_at':now,'draw_state':draw_states.get('ssq'),'recommendation':ssq})
write('dlt.json',{'generated_at':now,'draw_state':draw_states.get('dlt'),'recommendation':dlt})
write('review.json',{'schema_version':'1.1','generated_at':now,'draw_states':draw_states,'review':review,'recent_reviews':recent_reviews,'frontend_instruction':frontend})
write('research.json',{'generated_at':now,'candidates':research})
print(BRIDGE/'latest.json')

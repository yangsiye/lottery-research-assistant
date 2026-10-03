from __future__ import annotations
import json, sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parent
DB=ROOT/'data'/'lottery.db'
REPORTS=ROOT/'reports'
BRIDGE=ROOT/'bridge'
BRIDGE.mkdir(exist_ok=True)
TZ=ZoneInfo('Asia/Shanghai')

def load_json(name):
    p=REPORTS/name
    if not p.exists(): return None
    try: return json.loads(p.read_text(encoding='utf-8'))
    except Exception: return None

def rows(sql, params=()):
    if not DB.exists(): return []
    con=sqlite3.connect(DB); con.row_factory=sqlite3.Row
    try: return [dict(r) for r in con.execute(sql,params).fetchall()]
    except Exception: return []
    finally: con.close()

def write(name,payload):
    (BRIDGE/name).write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')

now=datetime.now(TZ).isoformat()
ssq=load_json('latest_ssq_recommendation.json')
dlt=load_json('latest_dlt_recommendation.json')
review=load_json('latest_review.json')
cloud=load_json('latest_cloud_run.json')
research=rows("SELECT discovered_at,name,source_url,hypothesis,decision FROM research_candidates ORDER BY id DESC LIMIT 20")
recent_reviews=rows("""SELECT p.lottery,p.issue,p.main_numbers,p.bonus_numbers,p.model_version,
                      r.actual_issue,r.main_hits,r.bonus_hits,r.reviewed_at
               FROM prediction_results r JOIN predictions p ON p.id=r.prediction_id
               ORDER BY r.reviewed_at DESC LIMIT 20""")

write('latest.json',{
    'schema_version':'1.0',
    'generated_at':now,
    'ssq':ssq,
    'dlt':dlt,
    'latest_review':review,
    'latest_cloud_run':cloud,
    'recent_reviews':recent_reviews,
    'research_candidates':research,
    'frontend_instruction':'This file is for ChatGPT automation consumption. Present results in ChatGPT; do not direct the user to a web dashboard.'
})
write('ssq.json',{'generated_at':now,'recommendation':ssq})
write('dlt.json',{'generated_at':now,'recommendation':dlt})
write('review.json',{'generated_at':now,'review':review,'recent_reviews':recent_reviews})
write('research.json',{'generated_at':now,'candidates':research})
print(BRIDGE/'latest.json')

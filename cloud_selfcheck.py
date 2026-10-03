from __future__ import annotations
import json, sys
from pathlib import Path

checks={}
try:
    import numpy, sklearn, requests, flask
    checks['dependencies']='ok'
except Exception as e:
    checks['dependencies']=f'error: {e}'

try:
    from lottery_assistant.db import DB
    from lottery_assistant.engine import DB_PATH
    db=DB(DB_PATH)
    checks['sqlite']=f'ok: {DB_PATH}'
except Exception as e:
    checks['sqlite']=f'error: {e}'

try:
    from lottery_assistant.fetchers import fetch_ssq
    x=fetch_ssq(3)
    checks['ssq_official_fetch']=f'ok: {len(x)} rows, latest={x[0]["issue"] if x else None}'
except Exception as e:
    checks['ssq_official_fetch']=f'error: {e}'

try:
    from lottery_assistant.fetchers import fetch_dlt
    x=fetch_dlt(3)
    checks['dlt_official_fetch']=f'ok: {len(x)} rows, latest={x[0]["issue"] if x else None}'
except Exception as e:
    checks['dlt_official_fetch']=f'error: {e}'

print(json.dumps(checks,ensure_ascii=False,indent=2))
sys.exit(0 if all(str(v).startswith('ok') for v in checks.values()) else 1)

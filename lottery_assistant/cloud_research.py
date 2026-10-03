from __future__ import annotations
import os
import re
import requests
from .db import DB
from .engine import DB_PATH

QUERIES=[
    '双色球 prediction',
    '大乐透 prediction',
    'ssq lottery prediction china',
    'dlt lottery prediction china',
]
METHODS={
    'transformer':['transformer','attention'],
    'lstm_gru':['lstm','gru'],
    'xgboost_lightgbm':['xgboost','lightgbm','catboost'],
    'random_forest':['random forest','随机森林'],
    'bayesian':['bayes','bayesian','贝叶斯'],
    'markov':['markov','马尔可夫'],
    'monte_carlo':['monte carlo','蒙特卡洛'],
    'genetic_algorithm':['genetic algorithm','遗传算法'],
    'reinforcement_learning':['reinforcement learning','强化学习'],
    'walk_forward':['walk-forward','walk forward','rolling backtest','滚动回测'],
}

def _method_tags(text:str):
    t=text.lower()
    return sorted(k for k,terms in METHODS.items() if any(term.lower() in t for term in terms))

def discover_github_candidates(limit_per_query=5):
    """Public GitHub discovery without any ChatGPT/GitHub connector.

    This only discovers and triages methods. It never promotes a method into production.
    Promotion remains governed by local implementation + leakage-safe OOS validation.
    """
    db=DB(DB_PATH)
    headers={'Accept':'application/vnd.github+json','User-Agent':'lottery-research-assistant-cloud/1.3'}
    token=os.getenv('GITHUB_TOKEN')
    if token:
        headers['Authorization']=f'Bearer {token}'
    discovered=[]
    seen=set()
    for q in QUERIES:
        try:
            r=requests.get('https://api.github.com/search/repositories',params={'q':q,'sort':'updated','order':'desc','per_page':limit_per_query},headers=headers,timeout=20)
            r.raise_for_status()
            items=r.json().get('items') or []
        except Exception as e:
            db.log('research-discovery-error',{'query':q,'error':str(e)})
            continue
        for item in items:
            url=item.get('html_url')
            if not url or url in seen: continue
            seen.add(url)
            desc=item.get('description') or ''
            readme=''
            # Keep requests conservative to stay under unauthenticated API limits.
            full=item.get('full_name')
            if full:
                try:
                    rr=requests.get(f'https://api.github.com/repos/{full}/readme',headers={**headers,'Accept':'application/vnd.github.raw+json'},timeout=15)
                    if rr.ok: readme=rr.text[:12000]
                except Exception:
                    pass
            text=' '.join([item.get('name') or '',desc,readme])
            tags=_method_tags(text)
            candidate={
                'name':full or item.get('name') or 'unknown',
                'source_url':url,
                'stars':int(item.get('stargazers_count') or 0),
                'updated_at':item.get('updated_at'),
                'method_tags':tags,
                'hypothesis':('Candidate methods: '+', '.join(tags)) if tags else 'Lottery-related repository; requires manual/LLM method extraction',
                'decision':'pending-validation',
            }
            db.upsert_research_candidate(candidate['name'],url,candidate['hypothesis'],json_meta=candidate)
            discovered.append(candidate)
    db.log('research-discovery',{'count':len(discovered),'items':discovered[:20]})
    return discovered

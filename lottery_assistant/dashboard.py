from __future__ import annotations
import json
from pathlib import Path
from flask import Flask, jsonify, Response

ROOT=Path(__file__).resolve().parents[1]
REPORTS=ROOT/'reports'
app=Flask(__name__)


def _load(name):
    p=REPORTS/name
    if not p.exists(): return None
    return json.loads(p.read_text(encoding='utf-8'))

@app.get('/api/status')
def status():
    return jsonify(_load('latest_cloud_run.json') or {'status':'no run yet'})

@app.get('/api/ssq')
def ssq():
    return jsonify(_load('latest_ssq_recommendation.json') or {'status':'no recommendation yet'})

@app.get('/api/dlt')
def dlt():
    return jsonify(_load('latest_dlt_recommendation.json') or {'status':'no recommendation yet'})

@app.get('/api/review')
def review():
    return jsonify(_load('latest_review.json') or {'status':'no review yet'})

@app.get('/')
def home():
    s=_load('latest_ssq_recommendation.json')
    d=_load('latest_dlt_recommendation.json')
    status=_load('latest_cloud_run.json')
    html=f'''<!doctype html><meta charset="utf-8"><title>彩票研究助理 Cloud</title>
    <style>body{{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;max-width:900px;margin:40px auto;padding:0 18px;line-height:1.55}}pre{{background:#f5f5f7;padding:16px;border-radius:12px;overflow:auto}}.card{{border:1px solid #ddd;border-radius:16px;padding:18px;margin:16px 0}}</style>
    <h1>彩票研究助理 · Cloud Edition</h1>
    <div class="card"><h2>双色球最新推荐</h2><pre>{json.dumps(s,ensure_ascii=False,indent=2) if s else '暂无'}</pre></div>
    <div class="card"><h2>大乐透最新推荐</h2><pre>{json.dumps(d,ensure_ascii=False,indent=2) if d else '暂无'}</pre></div>
    <div class="card"><h2>云端运行状态</h2><pre>{json.dumps(status,ensure_ascii=False,indent=2) if status else '暂无'}</pre></div>'''
    return Response(html,mimetype='text/html')

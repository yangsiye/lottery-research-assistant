from __future__ import annotations
import argparse, json
from .db import DB
from .engine import DB_PATH, sync, recommend

def main():
    p=argparse.ArgumentParser(prog='lottery-assistant')
    sp=p.add_subparsers(dest='cmd',required=True)
    sp.add_parser('init-db')
    s=sp.add_parser('sync'); s.add_argument('lottery',choices=['ssq','dlt']); s.add_argument('--periods',type=int,default=500)
    r=sp.add_parser('recommend'); r.add_argument('lottery',choices=['ssq','dlt']); r.add_argument('--seed',type=int)
    d=sp.add_parser('daily'); d.add_argument('--periods',type=int,default=500)
    sp.add_parser('cloud')
    q=sp.add_parser('quality-resolve',help='resolve an audited official-data conflict; never automatic')
    q.add_argument('lottery',choices=['ssq','dlt'])
    q.add_argument('--resolution',required=True)
    q.add_argument('--evidence-url',action='append',required=True)
    a=p.parse_args()
    if a.cmd=='init-db': DB(DB_PATH); print(DB_PATH)
    elif a.cmd=='sync': print({'synced':sync(a.lottery,a.periods)})
    elif a.cmd=='recommend': print(json.dumps(recommend(a.lottery,a.seed),ensure_ascii=False,indent=2))
    elif a.cmd=='quality-resolve':
        db=DB(DB_PATH)
        db.resolve_data_quality_flag(a.lottery,resolution=a.resolution,evidence_urls=a.evidence_url)
        db.checkpoint()
        print(json.dumps(db.get_data_quality_flag(a.lottery),ensure_ascii=False,indent=2))
        db.conn.close()
    elif a.cmd=='cloud':
        from .cloud import run_due
        res=run_due(); print(json.dumps({'now':res.now,'actions':res.actions},ensure_ascii=False,indent=2))
        if any(a['status'] in ('error','partial') for a in res.actions): raise SystemExit(1)
    elif a.cmd=='daily':
        out={}
        for lot in ('ssq','dlt'):
            try: sync(lot,a.periods); out[lot]=recommend(lot)
            except Exception as e: out[lot]={'error':str(e)}
        print(json.dumps(out,ensure_ascii=False,indent=2))

if __name__=='__main__': main()

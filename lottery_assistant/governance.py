"""Persist conservative model-state decisions and frozen forward attribution."""
import json
import numpy as np
from .backtest import probability_metrics


def record_training(db, lottery, zone, metrics, weights, draws, version):
    decisions={}
    for name,m in metrics.items():
        weight=float(weights.get(name,0))
        previous=db.conn.execute('SELECT status,weight FROM model_runs WHERE lottery=? AND model_name=? ORDER BY id DESC LIMIT 1',
                                 (lottery,f'{zone}:{name}')).fetchone()
        status='production' if name=='uniform' else ('low_weight' if weight else 'shadow')
        if previous and previous['weight']>0 and weight==0 and name!='uniform': status='reduced'
        decisions[name]={'status':status,'weight':weight,'reason':'基线保留' if name=='uniform' else
                         ('验证及留出稳定性门槛通过，小权重试运行' if weight else '证据不足或退化，保持影子验证')}
        meta={'zone':zone,'metrics':m,'decision':decisions[name]}
        db.conn.execute('''INSERT INTO model_runs(lottery,model_name,model_version,train_start,train_end,
            validation_brier,holdout_brier,baseline_brier,weight,status,metadata) VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
            (lottery,f'{zone}:{name}',version,draws[0]['issue'],draws[-1]['issue'],
             ((m or {}).get('validation') or {}).get('brier'), ((m or {}).get('holdout') or {}).get('brier'),
             (metrics.get('uniform') or {}).get('brier'),weight,status,json.dumps(meta,ensure_ascii=False)))
        db.conn.commit()
        if not previous or previous['status']!=status or abs(previous['weight']-weight)>1e-9:
            db.log('model-transition',{'zone':zone,'model':name,'previous':dict(previous) if previous else None,
                                     'current':decisions[name],'evidence_end':draws[-1]['issue'],'version':version},lottery)
    return decisions


def attribute_prediction(payload, actual, config):
    result={}
    for zone,key,max_key,pick_key in [('main','main_numbers','main_max','main_pick'),
                                       ('bonus','bonus_numbers','bonus_max','bonus_pick')]:
        y=np.array([n in actual[key] for n in range(1,config[max_key]+1)],dtype=int)
        result[zone]={name:probability_metrics(y,p,config[pick_key])
                      for name,p in payload.get('model_probabilities',{}).get(zone,{}).items()}
    return result

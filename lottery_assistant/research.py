from __future__ import annotations
from .db import DB
from .engine import DB_PATH

GATES = [
  'No future leakage; every feature at draw t uses only data strictly before t.',
  'Compare against uniform random baseline under the same walk-forward protocol.',
  'Use a holdout period untouched by feature/rule/model selection.',
  'Adjust for multiple comparisons when many hypotheses are screened.',
  'Require repeatable improvement across more than one historical window.',
  'Do not promote a method solely because of one jackpot-like lucky hit.',
  'Hot/cold/omission/mean-reversion signals are features, not mutually exclusive hard rules.',
  'Deep-learning models remain experimental unless they beat simpler baselines out of sample.'
]

def register_candidate(name, source_url, hypothesis):
    db=DB(DB_PATH)
    db.conn.execute('INSERT INTO research_candidates(name,source_url,hypothesis,leakage_check) VALUES(?,?,?,?)',
                    (name,source_url,hypothesis,'pending'))
    db.conn.commit()
    return {'name':name,'gates':GATES}

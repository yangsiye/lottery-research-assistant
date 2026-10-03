from __future__ import annotations
import json, sqlite3
from pathlib import Path
from typing import Iterable

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS draws(
  lottery TEXT NOT NULL,
  issue TEXT NOT NULL,
  draw_date TEXT NOT NULL,
  main_numbers TEXT NOT NULL,
  bonus_numbers TEXT NOT NULL,
  source TEXT NOT NULL,
  fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(lottery, issue)
);
CREATE TABLE IF NOT EXISTS predictions(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  lottery TEXT NOT NULL,
  issue TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  main_numbers TEXT NOT NULL,
  bonus_numbers TEXT NOT NULL,
  model_version TEXT NOT NULL,
  model_score REAL,
  rationale TEXT,
  UNIQUE(lottery, issue, main_numbers, bonus_numbers, model_version)
);
CREATE TABLE IF NOT EXISTS prediction_freezes(
  prediction_id INTEGER PRIMARY KEY,
  frozen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  target_draw_date TEXT,
  basis_issue TEXT,
  payload_sha256 TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  FOREIGN KEY(prediction_id) REFERENCES predictions(id)
);
CREATE TABLE IF NOT EXISTS prediction_results(
  prediction_id INTEGER PRIMARY KEY,
  actual_issue TEXT NOT NULL,
  main_hits INTEGER NOT NULL,
  bonus_hits INTEGER NOT NULL,
  reviewed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(prediction_id) REFERENCES predictions(id)
);
CREATE TABLE IF NOT EXISTS model_runs(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  lottery TEXT NOT NULL,
  model_name TEXT NOT NULL,
  model_version TEXT NOT NULL,
  trained_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  train_start TEXT,
  train_end TEXT,
  validation_brier REAL,
  holdout_brier REAL,
  baseline_brier REAL,
  weight REAL,
  status TEXT NOT NULL,
  metadata TEXT
);
CREATE TABLE IF NOT EXISTS research_candidates(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  discovered_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  name TEXT NOT NULL,
  source_url TEXT,
  hypothesis TEXT,
  leakage_check TEXT,
  backtest_summary TEXT,
  decision TEXT NOT NULL DEFAULT 'pending'
);
CREATE TABLE IF NOT EXISTS evolution_log(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  lottery TEXT,
  action TEXT NOT NULL,
  details TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS cloud_job_runs(
  job_key TEXT PRIMARY KEY,
  ran_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  status TEXT NOT NULL,
  details TEXT NOT NULL
);
"""

class DB:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def upsert_draw(self, lottery, issue, draw_date, main, bonus, source):
        self.conn.execute(
            """INSERT INTO draws(lottery,issue,draw_date,main_numbers,bonus_numbers,source)
               VALUES(?,?,?,?,?,?) ON CONFLICT(lottery,issue) DO UPDATE SET
               draw_date=excluded.draw_date,main_numbers=excluded.main_numbers,
               bonus_numbers=excluded.bonus_numbers,source=excluded.source""",
            (lottery, issue, draw_date, json.dumps(sorted(main)), json.dumps(sorted(bonus)), source),
        )
        self.conn.commit()

    def get_draws(self, lottery):
        rows = self.conn.execute(
            "SELECT * FROM draws WHERE lottery=? ORDER BY draw_date, issue", (lottery,)
        ).fetchall()
        out=[]
        for r in rows:
            d=dict(r); d['main_numbers']=json.loads(d['main_numbers']); d['bonus_numbers']=json.loads(d['bonus_numbers']); out.append(d)
        return out

    def add_prediction(self, lottery, issue, main, bonus, version, score, rationale):
        cur=self.conn.execute(
            """INSERT OR IGNORE INTO predictions(lottery,issue,main_numbers,bonus_numbers,model_version,model_score,rationale)
               VALUES(?,?,?,?,?,?,?)""",
            (lottery,issue,json.dumps(sorted(main)),json.dumps(sorted(bonus)),version,float(score),json.dumps(rationale, ensure_ascii=False)),
        )
        self.conn.commit()
        if cur.lastrowid:
            return cur.lastrowid
        row=self.conn.execute("""SELECT id FROM predictions WHERE lottery=? AND issue IS ? AND main_numbers=? AND bonus_numbers=? AND model_version=?""",
                              (lottery,issue,json.dumps(sorted(main)),json.dumps(sorted(bonus)),version)).fetchone()
        return row['id'] if row else None


    def freeze_prediction(self, prediction_id, payload_sha256, payload, target_draw_date=None, basis_issue=None):
        self.conn.execute(
            """INSERT OR IGNORE INTO prediction_freezes(prediction_id,target_draw_date,basis_issue,payload_sha256,payload_json)
               VALUES(?,?,?,?,?)""",
            (prediction_id,target_draw_date,basis_issue,payload_sha256,json.dumps(payload,ensure_ascii=False,sort_keys=True)),
        )
        self.conn.commit()

    def get_prediction_freeze(self, prediction_id):
        row=self.conn.execute("SELECT * FROM prediction_freezes WHERE prediction_id=?",(prediction_id,)).fetchone()
        if not row: return None
        d=dict(row); d['payload_json']=json.loads(d['payload_json']); return d

    def upsert_research_candidate(self, name, source_url, hypothesis, json_meta=None):
        row=self.conn.execute("SELECT id FROM research_candidates WHERE source_url=?",(source_url,)).fetchone()
        meta=json.dumps(json_meta or {},ensure_ascii=False)
        if row:
            self.conn.execute(
                "UPDATE research_candidates SET name=?,hypothesis=?,backtest_summary=? WHERE id=?",
                (name,hypothesis,meta,row['id'])
            )
        else:
            self.conn.execute(
                """INSERT INTO research_candidates(name,source_url,hypothesis,backtest_summary,decision)
                   VALUES(?,?,?,?,?)""",
                (name,source_url,hypothesis,meta,'pending')
            )
        self.conn.commit()

    def get_unreviewed_predictions(self, lottery):
        rows=self.conn.execute(
            """SELECT p.* FROM predictions p
               LEFT JOIN prediction_results r ON r.prediction_id=p.id
               WHERE p.lottery=? AND r.prediction_id IS NULL
               ORDER BY p.id""", (lottery,)
        ).fetchall()
        return [dict(r) for r in rows]

    def add_prediction_result(self, prediction_id, actual_issue, main_hits, bonus_hits):
        self.conn.execute(
            """INSERT OR REPLACE INTO prediction_results(prediction_id,actual_issue,main_hits,bonus_hits)
               VALUES(?,?,?,?)""",
            (prediction_id,actual_issue,int(main_hits),int(bonus_hits)),
        )
        self.conn.commit()

    def job_has_run(self, job_key):
        row=self.conn.execute("SELECT 1 FROM cloud_job_runs WHERE job_key=?",(job_key,)).fetchone()
        return row is not None

    def record_job_run(self, job_key, status, details):
        self.conn.execute(
            """INSERT OR REPLACE INTO cloud_job_runs(job_key,status,details) VALUES(?,?,?)""",
            (job_key,status,json.dumps(details,ensure_ascii=False)),
        )
        self.conn.commit()

    def log(self, action, details, lottery=None):
        self.conn.execute("INSERT INTO evolution_log(lottery,action,details) VALUES(?,?,?)",
                          (lottery, action, json.dumps(details, ensure_ascii=False)))
        self.conn.commit()

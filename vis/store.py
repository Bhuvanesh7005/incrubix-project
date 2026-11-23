"""SQLite store. One row per (question, provider, market, check_date, attempt):
re-running the same day updates in place (no duplicates); raw answers are kept as files."""
import json, sqlite3
from pathlib import Path
from .util import norm_question, qid_for, norm_priority

SCHEMA = """
CREATE TABLE IF NOT EXISTS questions(
  question_id TEXT PRIMARY KEY, question TEXT, norm TEXT UNIQUE, intent TEXT,
  source_type TEXT, source_url TEXT, collected_on TEXT, priority TEXT, notes TEXT);
CREATE TABLE IF NOT EXISTS checks(
  question_id TEXT, provider TEXT, market TEXT, check_date TEXT, attempt INTEGER,
  checked_at TEXT, mentioned INTEGER, cited INTEGER, position INTEGER, has_answer_box INTEGER, box_kind TEXT,
  quoted_urls TEXT, competitors TEXT, raw_path TEXT,
  PRIMARY KEY(question_id, provider, market, check_date, attempt));
"""

class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def upsert_question(self, q, intent="", source_type="", source_url="", collected_on="", priority="", notes=""):
        """Returns (question_id, inserted?). Duplicate (normalised) questions are rejected, not re-added."""
        norm = norm_question(q)
        row = self.db.execute("SELECT question_id FROM questions WHERE norm=?", (norm,)).fetchone()
        if row: return row["question_id"], False
        qid = qid_for(q)
        self.db.execute("INSERT INTO questions VALUES(?,?,?,?,?,?,?,?,?)",
                        (qid, q.strip(), norm, intent, source_type, source_url, collected_on, norm_priority(priority), notes))
        self.db.commit(); return qid, True

    def questions(self):
        return self.db.execute("SELECT * FROM questions ORDER BY question_id").fetchall()

    def has_check(self, qid, provider, market, date, attempt):
        return self.db.execute("SELECT 1 FROM checks WHERE question_id=? AND provider=? AND market=? AND check_date=? AND attempt=?",
                               (qid, provider, market, date, attempt)).fetchone() is not None

    def save_check(self, **k):
        k["quoted_urls"] = json.dumps(k.get("quoted_urls", [])); k["competitors"] = json.dumps(k.get("competitors", []))
        cols = ",".join(k); ph = ",".join("?" * len(k))
        self.db.execute(f"INSERT OR REPLACE INTO checks({cols}) VALUES({ph})", tuple(k.values()))
        self.db.commit()

    def checks(self, **where):
        sql = "SELECT * FROM checks"
        if where: sql += " WHERE " + " AND ".join(f"{k}=?" for k in where)
        return self.db.execute(sql, tuple(where.values())).fetchall()

    def dates(self):
        return [r[0] for r in self.db.execute("SELECT DISTINCT check_date FROM checks ORDER BY check_date")]

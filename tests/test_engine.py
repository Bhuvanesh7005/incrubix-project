import csv, json, datetime as dt
import pytest
from vis import collect, runner, export, report
from vis.store import Store
from vis.cli import load_cfg
from vis.providers import MockProvider, TransientError, ProviderUnavailable, OpenAIProvider
from vis.scoring import mentions_brand, cites_brand, google_position, question_score
from vis.util import norm_question

CFG = load_cfg("config/config.toml")

@pytest.fixture
def store(tmp_path): return Store(tmp_path / "t.db")

def mk(store, n=4):
    for i in range(n): store.upsert_question(f"how to caption short videos with ai tool {i}", "how-to", "forum", "https://x.example/t", "2026-01-01", "P1")

def provs(): return [MockProvider("google", "google"), MockProvider("chatgpt"), MockProvider("gemini"), MockProvider("perplexity"), MockProvider("claude")]

def test_dedupe_normalised(store):
    a = store.upsert_question("How to Caption Videos?", source_url="https://s"); b = store.upsert_question("how to caption  videos", source_url="https://s")
    assert a[1] and not b[1] and len(store.questions()) == 1

def test_import_rejects_missing_source(store, tmp_path):
    p = tmp_path / "q.csv"; p.write_text("question,source_url\nhow to edit podcasts with ai tools,https://reddit.example/1\nhow to make clips from long video,\n")
    r = collect.import_csv(store, p); assert r["added"] == 1 and r["rejected_no_source"] == 1

def test_run_idempotent_and_resumable(store, tmp_path):
    mk(store); kw = dict(raw_dir=str(tmp_path / "raw"), log_dir=str(tmp_path / "log"), sleep=lambda x: None)
    s1 = runner.run(store, provs(), CFG, check_date="2026-02-01", **kw); n = len(store.checks())
    s2 = runner.run(store, provs(), CFG, check_date="2026-02-01", **kw)
    assert s2["saved"] == 0 and s2["skipped_existing"] == s1["saved"] and len(store.checks()) == n

def test_failure_recovery(store, tmp_path):
    mk(store, 2)
    class Flaky(MockProvider):
        calls = 0
        def ask(self, q, m):
            Flaky.calls += 1
            if Flaky.calls == 1: raise TransientError("boom")
            return super().ask(q, m)
    s = runner.run(store, [Flaky("chatgpt")], CFG, check_date="2026-02-01", raw_dir=str(tmp_path / "r"), log_dir=str(tmp_path / "l"), sleep=lambda x: None)
    assert s["errors"] == 0 and s["saved"] > 0

def test_hard_failure_logged_not_fatal(store, tmp_path):
    mk(store, 2)
    class Dead(MockProvider):
        def ask(self, q, m): raise RuntimeError("HTTP 400")
    s = runner.run(store, [Dead("gemini")], CFG, check_date="2026-02-01", raw_dir=str(tmp_path / "r"), log_dir=str(tmp_path / "l"), sleep=lambda x: None)
    assert s["errors"] > 0 and (tmp_path / "l" / "errors.jsonl").exists()

def test_missing_key_is_skipped_not_faked(store, tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False); mk(store, 1)
    s = runner.run(store, [OpenAIProvider()], CFG, check_date="2026-02-01", raw_dir=str(tmp_path / "r"), log_dir=str(tmp_path / "l"))
    assert s["unavailable"] == ["chatgpt"] and store.checks() == []

def test_export_needs_two_days_and_official_columns(store, tmp_path):
    mk(store); kw = dict(raw_dir=str(tmp_path / "raw"), log_dir=str(tmp_path / "log"), sleep=lambda x: None)
    runner.run(store, provs(), CFG, check_date="2026-02-01", **kw)
    with pytest.raises(ValueError): export.export_csv(store, CFG, tmp_path / "v.csv")
    runner.run(store, provs(), CFG, check_date="2026-02-02", **kw)
    r = export.export_csv(store, CFG, tmp_path / "v.csv"); assert r["exported"] == 4
    rows = list(csv.DictReader(open(tmp_path / "v.csv"))); assert list(rows[0].keys()) == export.COLUMNS
    assert rows[0]["check_date_day1"] == "2026-02-01" and rows[0]["check_date_day2"] == "2026-02-02"
    # values must match the workbook's dropdown lists
    for r in rows:
        assert r["intent"] in {"Informational", "Comparison", "Transactional", "Navigational"}
        assert r["market"] in {"US", "GB", "CA", "AU", "IN", "SG", "Other"}
        assert r["answer_box_or_ai_overview"] in {"Answer box", "AI Overview", "Both", "None"}
        for k in ("chatgpt", "gemini", "perplexity", "claude_or_copilot"): assert r[k] in {"Cited", "Mentioned", "Not mentioned"}
        assert r["priority"] in {"High", "Medium", "Low"} and r["changed_on_day2"] in {"Yes", "No"}

def test_scoring_helpers():
    assert mentions_brand("Try IncuBrix today", ["IncuBrix"]) and not mentions_brand("incubrixify", ["IncuBrix"])
    assert cites_brand(["https://www.incubrix.com/x"], ["incubrix.com"])
    assert not cites_brand(["https://notincubrix.com/x"], ["incubrix.com"])
    assert cites_brand(["https://blog.incubrix.com/x"], ["incubrix.com"])
    assert google_position([(3, "https://www.incubrix.com/a", "t")], ["incubrix.com"]) == 3
    assert question_score([], None, False) == 0 and question_score([{"cited": 1, "mentioned": 1}], 1, True) == 100.0

def test_report_alert_and_brief(store, tmp_path):
    mk(store); kw = dict(raw_dir=str(tmp_path / "raw"), log_dir=str(tmp_path / "log"), sleep=lambda x: None)
    runner.run(store, provs(), CFG, check_date="2026-02-01", **kw)
    runner.run(store, [MockProvider("google", "google", mention_every=1), MockProvider("chatgpt", mention_every=1)], CFG, check_date="2026-02-08", **kw)
    md, agg = report.weekly_report(store, CFG); assert "Overall visibility score" in md and agg["overall"] is not None
    assert isinstance(report.alerts(store, CFG, threshold=0.1), list)
    qid = store.questions()[0]["question_id"]; assert "Answer in the first two sentences" in report.brief_for(store, qid, CFG)

def test_suggest_with_fake_fetch():
    url, s = collect.suggest("ai video captions", fetch=lambda u: ["q", ["how to add ai video captions free", "x", "best ai video captions tool"]])
    assert "suggestqueries.google.com" in url and len(s) == 2

def test_web_api_roundtrip(tmp_path, monkeypatch):
    import threading, urllib.request, json as _j
    from http.server import ThreadingHTTPServer
    from vis import web
    monkeypatch.chdir(tmp_path); (tmp_path / "data").mkdir()
    import shutil, pathlib
    shutil.copy(pathlib.Path(__file__).parent.parent / "data/DEMO_questions_NOT_REAL.csv", tmp_path / "data/")
    web.H.cfg = CFG; srv = ThreadingHTTPServer(("127.0.0.1", 0), web.H); port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    def call(path, body=None):
        req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=_j.dumps(body).encode() if body is not None else None, method="POST" if body is not None else "GET")
        try: return _j.loads(urllib.request.urlopen(req).read())
        except urllib.error.HTTPError as e: return _j.loads(e.read())
    assert "error" in call("/api/questions?mode=demo", {"question": "how to caption short videos fast", "source_url": ""})   # source required
    assert call("/api/sample?mode=demo", {})["added"] == 5
    for d in ("2026-03-01", "2026-03-02"):
        call("/api/run?mode=demo", {"date": d}); import time
        for _ in range(100):
            if not call("/api/run/status")["running"]: break
            time.sleep(0.1)
    assert len(call("/api/results?mode=demo")["rows"]) == 5
    assert "Overall visibility score" in call("/api/report?mode=demo")["markdown"]
    srv.shutdown()

"""Web interface for the visibility engine. Standard library only.
Start:  python -m vis serve   ->  http://127.0.0.1:8765
Binds to localhost by default; API keys stay in environment variables on the machine running the server."""
import csv, io, json, threading, time, datetime as dt
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from .store import Store
from .util import setup_logging
from . import collect, runner, export, report
from .cli import load_cfg, providers_for

STATIC = Path(__file__).parent / "static" / "index.html"
SAMPLE = Path("data/DEMO_questions_NOT_REAL.csv")
JOB = {"running": False, "started": None, "finished": None, "summary": None, "error": None, "mode": None}
LOCK = threading.Lock()

def root_for(mode): return Path("demo_data" if mode == "demo" else "data")
def open_store(mode): return Store(root_for(mode) / "vis.db")

def state(cfg, mode):
    st = open_store(mode); provs = providers_for(cfg, mode == "demo")
    return {"mode": mode, "dates": st.dates(), "questions": len(st.questions()), "checks": len(st.checks()),
            "providers": [{"name": p.name, "available": p.available(), "env": getattr(p, "__class__").__name__} for p in provs],
            "markets": [m["code"] for m in cfg["markets"]], "brand": cfg["brand"]["names"][0]}

def results(cfg, mode, date):
    st = open_store(mode); dates = st.dates(); date = date or (dates[-1] if dates else None)
    if not date: return {"date": None, "rows": []}
    per_q, agg, comp = report.snapshot(st, date, cfg); rows = []
    for q in st.questions():
        cs = st.checks(question_id=q["question_id"], check_date=date); v = per_q[q["question_id"]]
        ai = {}
        for p in ("chatgpt", "gemini", "perplexity", "claude"):
            c = [x for x in cs if x["provider"] == p]
            ai[p] = None if not c else "Cited" if any(x["cited"] for x in c) else "Mentioned" if any(x["mentioned"] for x in c) else "Not mentioned"
        rows.append({"id": q["question_id"], "question": q["question"], "intent": q["intent"], "priority": q["priority"], "source_url": q["source_url"],
                     "score": v["score"], "google_position": v["gpos"], "competitors": v["competitors"], **ai})
    return {"date": date, "rows": rows, "agg": agg, "competitors": comp.most_common(8)}

def start_run(cfg, mode, body):
    with LOCK:
        if JOB["running"]: raise RuntimeError("a run is already in progress")
        JOB.update(running=True, started=time.strftime("%H:%M:%S"), finished=None, summary=None, error=None, mode=mode)
    def work():
        try:
            root = root_for(mode); st = open_store(mode); log = setup_logging(str(root / "logs"))
            ps = providers_for(cfg, mode == "demo", bool(body.get("flaky")))
            s = runner.run(st, ps, cfg, check_date=body.get("date") or dt.date.today().isoformat(), repeat=int(body.get("repeat") or cfg["run"]["ai_repeats"]),
                           limit=int(body["limit"]) if body.get("limit") else None, sleep=(lambda x: None) if mode == "demo" else time.sleep,
                           logger=log, raw_dir=str(root / "raw"), log_dir=str(root / "logs"))
            JOB["summary"] = s
        except Exception as e: JOB["error"] = repr(e)
        finally: JOB["running"] = False; JOB["finished"] = time.strftime("%H:%M:%S")
    threading.Thread(target=work, daemon=True).start()

class H(BaseHTTPRequestHandler):
    cfg = None
    def log_message(self, *a): pass
    def _send(self, code, body, ctype="application/json", extra=None):
        data = body if isinstance(body, bytes) else (body if isinstance(body, str) else json.dumps(body, default=str)).encode()
        self.send_response(code); self.send_header("Content-Type", ctype + "; charset=utf-8"); self.send_header("Content-Length", str(len(data)))
        for k, v in (extra or {}).items(): self.send_header(k, v)
        self.end_headers(); self.wfile.write(data)
    def _err(self, e, code=400): self._send(code, {"error": str(e)})
    def do_GET(self):
        u = urlparse(self.path); q = {k: v[0] for k, v in parse_qs(u.query).items()}; mode = "demo" if q.get("mode") == "demo" else "live"
        try:
            if u.path == "/": return self._send(200, STATIC.read_bytes(), "text/html")
            if u.path == "/api/state": return self._send(200, state(self.cfg, mode))
            if u.path == "/api/results": return self._send(200, results(self.cfg, mode, q.get("date")))
            if u.path == "/api/run/status": return self._send(200, JOB)
            if u.path == "/api/report":
                st = open_store(mode)
                if not st.dates(): return self._err("no checks yet - run the tracker first")
                md, _ = report.weekly_report(st, self.cfg, q.get("date")); return self._send(200, {"markdown": md})
            if u.path == "/api/brief":
                return self._send(200, {"markdown": report.brief_for(open_store(mode), q["qid"], self.cfg)})
            if u.path == "/api/raw":
                st = open_store(mode); rows = [dict(r) for r in st.checks(question_id=q["qid"])]
                for r in rows:
                    try: r["raw"] = json.loads(Path(r["raw_path"]).read_text())
                    except Exception: r["raw"] = None
                return self._send(200, {"checks": rows})
            if u.path == "/api/alerts": return self._send(200, {"alerts": report.alerts(open_store(mode), self.cfg)})
            if u.path == "/api/export":
                st = open_store(mode)
                try: rows, rejected = export.build_rows(st, self.cfg)
                except ValueError as e: return self._err(e)
                buf = io.StringIO(); w = csv.DictWriter(buf, fieldnames=export.COLUMNS); w.writeheader(); w.writerows(rows)
                return self._send(200, buf.getvalue(), "text/csv", {"Content-Disposition": "attachment; filename=visibility.csv", "X-Rejected": str(len(rejected))})
            self._err("not found", 404)
        except Exception as e: self._err(e, 500)
    def do_POST(self):
        u = urlparse(self.path); q = {k: v[0] for k, v in parse_qs(u.query).items()}; mode = "demo" if q.get("mode") == "demo" else "live"
        n = int(self.headers.get("Content-Length") or 0); raw = self.rfile.read(n).decode() if n else ""
        try:
            body = json.loads(raw) if raw.strip().startswith("{") else {"text": raw}
            st = open_store(mode)
            if u.path == "/api/questions":
                src = (body.get("source_url") or "").strip(); text = (body.get("question") or "").strip()
                if len(text.split()) < 3: return self._err("question is too short")
                if not src.startswith("http"): return self._err("source_url is required (a real link where the question was found)")
                qid, new = st.upsert_question(text, intent=body.get("intent") or collect.guess_intent(text), source_type=body.get("source_type") or "manual_entry",
                                              source_url=src, collected_on=dt.date.today().isoformat(), priority=body.get("priority", ""))
                return self._send(200, {"id": qid, "added": new})
            if u.path == "/api/import":
                tmp = root_for(mode) / "_upload.csv"; tmp.parent.mkdir(parents=True, exist_ok=True); tmp.write_text(body.get("text", ""), encoding="utf-8")
                return self._send(200, collect.import_csv(st, tmp))
            if u.path == "/api/collect":
                seeds = [s.strip() for s in (body.get("seeds") or "").splitlines() if s.strip()]
                return self._send(200, collect.collect_from_seeds(st, seeds, gl=self.cfg["markets"][0]["gl"]))
            if u.path == "/api/sample":
                if mode != "demo": return self._err("sample questions are only loaded in demo mode")
                return self._send(200, collect.import_csv(st, SAMPLE))
            if u.path == "/api/run":
                start_run(self.cfg, mode, body); return self._send(200, {"started": True})
            if u.path == "/api/reset":
                if mode != "demo": return self._err("reset is only allowed in demo mode")
                import shutil; shutil.rmtree("demo_data", ignore_errors=True); return self._send(200, {"ok": True})
            self._err("not found", 404)
        except Exception as e: self._err(e)

def serve(cfg, host="127.0.0.1", port=8765):
    H.cfg = cfg; srv = ThreadingHTTPServer((host, port), H)
    print(f"IncuBrix visibility UI: http://{host}:{port}   (Ctrl+C to stop)")
    try: srv.serve_forever()
    except KeyboardInterrupt: print("\nstopped")

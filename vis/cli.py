import argparse, csv, json, sys, tomllib, datetime as dt
from pathlib import Path
from .store import Store
from .util import setup_logging
from . import collect, runner, export, report
from .providers import (OpenAIProvider, GeminiProvider, PerplexityProvider, ClaudeProvider, SerpApiGoogle, MockProvider, TransientError)

class FlakyOnce:
    """Demo only: wraps a provider and fails its first call once to prove retry/recovery."""
    def __init__(self, inner): self.inner, self.failed = inner, False; self.name, self.kind = inner.name, inner.kind
    def available(self): return True
    def ask(self, q, m):
        if not self.failed: self.failed = True; raise TransientError("simulated timeout (demo)")
        return self.inner.ask(q, m)

def load_cfg(path):
    with open(path, "rb") as f: return tomllib.load(f)

def providers_for(cfg, demo=False, flaky=False):
    if demo:
        ps = [MockProvider("google", "google"), MockProvider("chatgpt"), MockProvider("gemini"), MockProvider("perplexity"), MockProvider("claude")]
        return [FlakyOnce(ps[0])] + ps[1:] if flaky else ps
    m = cfg["models"]
    return [SerpApiGoogle(), OpenAIProvider(m["openai"]), GeminiProvider(m["gemini"]), PerplexityProvider(m["perplexity"]), ClaudeProvider(m["claude"])]

def main(argv=None):
    ap = argparse.ArgumentParser(prog="vis", description="IncuBrix visibility engine")
    ap.add_argument("--config", default="config/config.toml"); ap.add_argument("--demo", action="store_true", help="offline mock providers + separate demo DB (never real data)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect"); c.add_argument("--seeds", required=True, help="text file, one seed phrase per line")
    i = sub.add_parser("import"); i.add_argument("csv")
    r = sub.add_parser("run"); r.add_argument("--date"); r.add_argument("--repeat", type=int); r.add_argument("--limit", type=int); r.add_argument("--flaky", action="store_true")
    sub.add_parser("report"); a = sub.add_parser("alerts")
    e = sub.add_parser("export"); e.add_argument("--out", default="visibility.csv")
    b = sub.add_parser("brief"); b.add_argument("question_id"); 
    sv = sub.add_parser("serve", help="start the web interface"); sv.add_argument("--port", type=int, default=8765); sv.add_argument("--host", default="127.0.0.1")
    sub.add_parser("weekly", help="run today's checks, then report + alerts (use this in cron)")
    args = ap.parse_args(argv)
    cfg = load_cfg(args.config)
    if args.cmd == "serve":
        from .web import serve; return serve(cfg, args.host, args.port)
    root = Path("demo_data" if args.demo else "data")
    log = setup_logging(str(root / "logs")); store = Store(root / "vis.db")
    kw = dict(raw_dir=str(root / "raw"), log_dir=str(root / "logs"), logger=log)
    if args.cmd == "collect":
        seeds = [s.strip() for s in open(args.seeds) if s.strip()]
        print(json.dumps(collect.collect_from_seeds(store, seeds, gl=cfg["markets"][0]["gl"])))
    elif args.cmd == "import": print(json.dumps(collect.import_csv(store, args.csv)))
    elif args.cmd in ("run", "weekly"):
        s = runner.run(store, providers_for(cfg, args.demo, getattr(args, "flaky", False)), cfg, check_date=getattr(args, "date", None),
                       repeat=getattr(args, "repeat", None), limit=getattr(args, "limit", None), sleep=(lambda x: None) if args.demo else __import__("time").sleep, **kw)
        print(json.dumps(s))
        if args.cmd == "weekly":
            md, _ = report.weekly_report(store, cfg); out = root / "reports" / f"{store.dates()[-1]}.md"
            out.parent.mkdir(parents=True, exist_ok=True); out.write_text(md); print("report:", out)
            lines = report.alerts(store, cfg)
            if lines: print("ALERTS:\n" + "\n".join(lines)); report.send_alert(lines, __import__("os").environ.get("ALERT_WEBHOOK_URL"))
    elif args.cmd == "report":
        md, _ = report.weekly_report(store, cfg); out = root / "reports" / f"{store.dates()[-1]}.md"
        out.parent.mkdir(parents=True, exist_ok=True); out.write_text(md); print(md)
    elif args.cmd == "alerts":
        lines = report.alerts(store, cfg); print("\n".join(lines) or "no alerts"); sys.exit(2 if lines else 0)
    elif args.cmd == "export": print(json.dumps(export.export_csv(store, cfg, args.out)))
    elif args.cmd == "brief": print(report.brief_for(store, args.question_id, cfg))

if __name__ == "__main__": main()

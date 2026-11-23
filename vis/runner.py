"""Run the question set across providers/markets. Resumable and idempotent."""
import json, time, datetime as dt
from pathlib import Path
from .providers import ProviderUnavailable, TransientError, Result
from .scoring import mentions_brand, cites_brand, competitors_in, google_position
from .util import log_error

def now_iso(): return dt.datetime.now().astimezone().isoformat(timespec="seconds")

def call_with_retry(provider, q, market, retries=3, base_delay=2.0, sleep=time.sleep):
    last = None
    for i in range(retries + 1):
        try:
            return provider.ask(q, market)
        except TransientError as e:
            last = e; sleep(base_delay * (2 ** i))
    raise last

def run(store, providers, cfg, check_date=None, repeat=None, limit=None, sleep=time.sleep, logger=None, raw_dir="raw", log_dir="logs"):
    """Returns a summary dict. Existing (question,provider,market,date,attempt) rows are skipped,
    so re-running never duplicates and an interrupted run continues where it stopped."""
    check_date = check_date or dt.date.today().isoformat()
    repeat = repeat or cfg["run"]["ai_repeats"]
    brand, comps = cfg["brand"], cfg["competitors"]
    qs = store.questions()[: limit or None]
    stats = {"date": check_date, "attempted": 0, "saved": 0, "skipped_existing": 0, "errors": 0, "unavailable": []}
    for p in providers:
        if not p.available():
            msg = f"{p.name}: not available (missing API key/feature) at {now_iso()}"
            stats["unavailable"].append(p.name); log_error(log_dir, provider=p.name, error=msg, kind="unavailable")
            if logger: logger.warning(msg)
            continue
        markets = cfg["markets"] if p.kind == "google" or p.name == "chatgpt" else cfg["markets"][:1]
        attempts = 1 if p.kind == "google" else repeat
        for q in qs:
            for m in markets:
                for a in range(1, attempts + 1):
                    if store.has_check(q["question_id"], p.name, m["code"], check_date, a):
                        stats["skipped_existing"] += 1; continue
                    stats["attempted"] += 1
                    try:
                        res: Result = call_with_retry(p, q["question"], m, retries=cfg["run"]["retries"], sleep=sleep)
                    except ProviderUnavailable as e:
                        stats["unavailable"].append(p.name); log_error(log_dir, provider=p.name, error=str(e), kind="unavailable"); break
                    except Exception as e:           # log and continue: one bad item never kills the run
                        stats["errors"] += 1
                        log_error(log_dir, provider=p.name, question_id=q["question_id"], market=m["code"], error=repr(e), kind="failed")
                        if logger: logger.error("%s %s %s: %s", p.name, q["question_id"], m["code"], e)
                        continue
                    loc = "set via API (%s)" % m["gl"] if p.kind == "google" or p.name == "chatgpt" else "not configurable via API; provider default"
                    rel = Path(raw_dir) / check_date / p.name / m["code"] / f"{q['question_id']}_a{a}.json"
                    rel.parent.mkdir(parents=True, exist_ok=True)
                    meta = {"checked_at": now_iso(), "date": check_date, "provider": p.name, "market": m["code"], "attempt": a,
                            "question": q["question"], "location_setting": loc}
                    rel.write_text(json.dumps({"meta": meta, "text": res.text, "urls": res.urls, "organic": res.organic,
                                               "answer_box": res.answer_box, "raw": res.raw}, indent=1))
                    pos = google_position(res.organic, brand["domains"]) if p.kind == "google" else None
                    blob = res.text + " " + json.dumps(res.answer_box or {})
                    store.save_check(question_id=q["question_id"], provider=p.name, market=m["code"], check_date=check_date,
                                     attempt=a, checked_at=meta["checked_at"],
                                     mentioned=int(mentions_brand(blob, brand["names"])),
                                     cited=int(cites_brand(res.urls, brand["domains"])),
                                     position=pos, has_answer_box=int(bool(res.answer_box)), box_kind=",".join((res.answer_box or {}).get("kinds", [])),
                                     quoted_urls=res.urls[:15], competitors=competitors_in(blob, res.urls, comps),
                                     raw_path=str(rel))
                    stats["saved"] += 1
    return stats

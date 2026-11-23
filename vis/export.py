"""Export visibility.csv in the official workbook column order (02_QUESTIONS A..T), using the workbook's dropdown values:
intent Informational|Comparison|Transactional|Navigational · market one of US,GB,CA,AU,IN,SG,Other ·
answer box = Answer box|AI Overview|Both|None · assistants = Cited|Mentioned|Not mentioned · priority High|Medium|Low."""
import csv, json

COLUMNS = ["question_id", "question", "intent", "source_type", "source_url", "market", "google_position", "answer_box_or_ai_overview",
           "quoted_source_url", "chatgpt", "gemini", "perplexity", "claude_or_copilot", "competitors_named", "check_date_day1",
           "check_date_day2", "changed_on_day2", "raw_answers_url", "priority", "notes"]
INTENT_MAP = {"how-to": "Informational", "definition": "Informational", "other": "Informational", "comparison": "Comparison", "best-tool": "Transactional"}
RANK = {"Not mentioned": 0, "Mentioned": 1, "Cited": 2}

def _state(c): return "Cited" if c["cited"] else "Mentioned" if c["mentioned"] else "Not mentioned"
def _best(cs): return max((_state(c) for c in cs), key=RANK.get) if cs else None

def validate_row(r) -> list:
    """Quality gate before export. Returns problems (empty = OK)."""
    bad = []
    for k in ("question", "intent", "source_type", "source_url", "market", "google_position", "answer_box_or_ai_overview",
              "chatgpt", "gemini", "perplexity", "claude_or_copilot", "check_date_day1", "check_date_day2", "raw_answers_url"):
        if not str(r.get(k, "")).strip(): bad.append(f"missing {k}")
    if r.get("check_date_day1") and r.get("check_date_day1") == r.get("check_date_day2"): bad.append("day1 == day2")
    return bad

def build_rows(store, cfg):
    dates = store.dates()
    if len(dates) < 2: raise ValueError(f"need checks on 2 different days, have {len(dates)}: {dates}")
    d1, d2 = dates[0], dates[1]
    mk = [m["code"] for m in cfg["markets"]]; primary = mk[0]
    rows, rejected = [], []
    for q in store.questions():
        cs_all = store.checks(question_id=q["question_id"])
        def sel(p=None, d=None, m=None):
            return [c for c in cs_all if (p is None or c["provider"] == p) and (d is None or c["check_date"] == d) and (m is None or c["market"] == m)]
        def gpos(d, m):
            g = sel("google", d, m); return (g[0]["position"] if g and g[0]["position"] else "none") if g else "n/a"
        primary_pos = f"d1:{gpos(d1, primary)} d2:{gpos(d2, primary)}"
        others = "; ".join(f"{m} d1:{gpos(d1, m)} d2:{gpos(d2, m)}" for m in mk[1:])
        gg = sel("google"); kinds = {k for c in gg for k in (c["box_kind"] or "").split(",") if k}
        box = "Both" if {"answer_box", "ai_overview"} <= kinds else "AI Overview" if "ai_overview" in kinds else "Answer box" if "answer_box" in kinds else "None"
        ai = {p: sel(p) for p in ("chatgpt", "gemini", "perplexity", "claude")}
        changed = gpos(d1, primary) != gpos(d2, primary) or any(
            (_best(sel(p, d1)) != _best(sel(p, d2))) for p in ai)
        det = " ".join(f"{p}[d1:{_best(sel(p, d1)) or 'n/a'}; d2:{_best(sel(p, d2)) or 'n/a'}]" for p in ai)
        quoted = sorted({u for c in gg for u in json.loads(c["quoted_urls"])})[:5]
        comps = sorted({x for c in cs_all for x in json.loads(c["competitors"])})
        note = " | ".join(x for x in (q["notes"], f"Other markets: {others}" if others else "", det) if x)
        row = {"question_id": q["question_id"], "question": q["question"], "intent": INTENT_MAP.get(q["intent"], q["intent"]),
               "source_type": q["source_type"], "source_url": q["source_url"], "market": primary,
               "google_position": primary_pos, "answer_box_or_ai_overview": box if gg else "",
               "quoted_source_url": " ".join(quoted), **{k: (_best(ai[p]) or "") for k, p in
               (("chatgpt", "chatgpt"), ("gemini", "gemini"), ("perplexity", "perplexity"), ("claude_or_copilot", "claude"))},
               "competitors_named": ", ".join(comps), "check_date_day1": d1, "check_date_day2": d2,
               "changed_on_day2": "Yes" if changed else "No", "raw_answers_url": f"raw/{d1}/ and raw/{d2}/ (…/{q['question_id']}_a*.json)",
               "priority": q["priority"] or "Medium", "notes": note}
        probs = validate_row(row)
        (rejected.append((row, probs)) if probs else rows.append(row))
    return rows, rejected

def export_csv(store, cfg, path):
    rows, rejected = build_rows(store, cfg)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS); w.writeheader(); w.writerows(rows)
    return {"exported": len(rows), "rejected": len(rejected), "rejected_reasons": [p for _, p in rejected][:5], "path": str(path)}

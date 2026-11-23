"""Weekly report + alerts + brief generator."""
import json, datetime as dt, urllib.request
from collections import Counter
from .scoring import question_score

def snapshot(store, date, cfg):
    """Per-question score and aggregate rates for one check date."""
    ai_names = [p for p in ("chatgpt", "gemini", "perplexity", "claude")]
    per_q, agg = {}, {"ai_checks": 0, "ai_mentions": 0, "ai_cites": 0, "google_checks": 0, "top10": 0, "box": 0, "box_ours": 0}
    comp = Counter()
    for q in store.questions():
        cs = [c for c in store.checks(question_id=q["question_id"], check_date=date)]
        ai = [c for c in cs if c["provider"] in ai_names]
        gg = [c for c in cs if c["provider"] == "google"]
        gpos = min([c["position"] for c in gg if c["position"]], default=None)
        ours = any(c["has_answer_box"] and c["cited"] for c in gg)
        per_q[q["question_id"]] = {"question": q["question"], "priority": q["priority"], "score": question_score(ai, gpos, ours),
                                   "gpos": gpos, "competitors": sorted({x for c in cs for x in json.loads(c["competitors"])})}
        for c in ai: agg["ai_checks"] += 1; agg["ai_mentions"] += c["mentioned"] or c["cited"]; agg["ai_cites"] += c["cited"]
        for c in gg:
            agg["google_checks"] += 1; agg["top10"] += bool(c["position"] and c["position"] <= 10)
            agg["box"] += c["has_answer_box"]; agg["box_ours"] += int(c["has_answer_box"] and c["cited"])
        for c in cs:
            for x in json.loads(c["competitors"]): comp[x] += 1
    n = len(per_q) or 1
    agg["overall"] = round(sum(v["score"] for v in per_q.values()) / n, 1)
    pct = lambda a, b: round(100 * a / b, 1) if b else None
    agg["ai_mention_rate"] = pct(agg["ai_mentions"], agg["ai_checks"]); agg["ai_citation_rate"] = pct(agg["ai_cites"], agg["ai_checks"])
    agg["google_top10_rate"] = pct(agg["top10"], agg["google_checks"]); agg["answer_share"] = pct(agg["box_ours"], agg["box"])
    return per_q, agg, comp

def weekly_report(store, cfg, date=None):
    dates = store.dates()
    if not dates: raise ValueError("no checks stored yet")
    date = date or dates[-1]
    prev = max([d for d in dates if d < date], default=None)
    per_q, agg, comp = snapshot(store, date, cfg)
    pagg = snapshot(store, prev, cfg)[1] if prev else None
    def delta(k):
        if not pagg or agg[k] is None or pagg[k] is None: return "–"
        d = round(agg[k] - pagg[k], 1); return f"{d:+}"
    gaps = sorted([v for v in per_q.values() if v["score"] < 20], key=lambda v: (v["priority"] != "High", -len(v["competitors"])))[:15]
    L = [f"# IncuBrix visibility report — {date}", "",
         f"Questions tracked: **{len(per_q)}** · compared with: {prev or 'first run'}", "",
         "| Metric | Now | Change |", "|---|---|---|",
         f"| Overall visibility score (0-100) | {agg['overall']} | {delta('overall')} |",
         f"| AI mention rate (%) | {agg['ai_mention_rate']} | {delta('ai_mention_rate')} |",
         f"| AI citation rate (%) | {agg['ai_citation_rate']} | {delta('ai_citation_rate')} |",
         f"| Google top-10 rate (%) | {agg['google_top10_rate']} | {delta('google_top10_rate')} |",
         f"| Answer share (% of answer boxes citing us) | {agg['answer_share']} | {delta('answer_share')} |", "",
         "## Competitors named most often", ""] + [f"- {n}: {c} checks" for n, c in comp.most_common(8)] + \
        ["", "## Biggest gaps (score < 20) — write or fix these first", ""] + \
        [f"- `{qid}` {v['question']} — competitors: {', '.join(v['competitors']) or 'none named'}" for qid, v in
         [(k, v) for k, v in per_q.items() if v in gaps]] + \
        ["", "_Raw answers for every number above are stored under raw/<date>/. Scores are recalculated from the database, never typed._"]
    return "\n".join(L), agg

def alerts(store, cfg, threshold=5.0):
    dates = store.dates()
    if len(dates) < 2: return []
    a_prev = snapshot(store, dates[-2], cfg)[0]; a_now = snapshot(store, dates[-1], cfg)[0]
    out = []
    for qid, v in a_now.items():
        p = a_prev.get(qid)
        if p and abs(v["score"] - p["score"]) >= threshold * 2 and v["priority"] in ("High", "Medium", ""):
            out.append(f"{qid} '{v['question']}' score {p['score']} → {v['score']}")
    o_now = sum(v["score"] for v in a_now.values()) / max(len(a_now), 1); o_prev = sum(v["score"] for v in a_prev.values()) / max(len(a_prev), 1)
    if abs(o_now - o_prev) >= threshold: out.insert(0, f"OVERALL visibility {o_prev:.1f} → {o_now:.1f}")
    return out

def send_alert(lines, webhook):
    if not (lines and webhook): return False
    req = urllib.request.Request(webhook, data=json.dumps({"text": "IncuBrix visibility alert:\n" + "\n".join(lines)}).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    urllib.request.urlopen(req, timeout=20); return True

SCHEMA_FOR_INTENT = {"how-to": "HowTo + FAQPage", "comparison": "Article + FAQPage (comparison table in HTML)", "best-tool": "Article + ItemList + FAQPage",
                     "definition": "DefinedTerm + FAQPage", "other": "Article + FAQPage"}

def brief_for(store, qid, cfg):
    q = next(r for r in store.questions() if r["question_id"] == qid)
    cs = store.checks(question_id=qid)
    comps = sorted({x for c in cs for x in json.loads(c["competitors"])})
    cited = Counter(u for c in cs for u in json.loads(c["quoted_urls"]))
    return "\n".join([
        f"# Page brief — {q['question']}", f"- Question ID: `{qid}` · intent: {q['intent']} · priority: {q['priority'] or 'unset'}",
        f"- Source of question: {q['source_type']} — {q['source_url']}", "",
        "## Must-have structure",
        "1. H1 = the question in plain words.", "2. **Answer in the first two sentences** (40-60 words, no preamble).",
        "3. Steps / table / list that a reader can follow without leaving the page.",
        f"4. Structured data: {SCHEMA_FOR_INTENT.get(q['intent'], SCHEMA_FOR_INTENT['other'])}.",
        "5. 3+ cited sources (official docs, studies) with links; one original element (own test, screenshot, data).",
        "6. 3+ internal links (hub page, 2 related guides); one clear next step into the product.", "",
        "## What the market currently shows",
        f"- Competitors named by AI/Google: {', '.join(comps) or 'none recorded yet'}",
        "- Pages already cited for this question (earn a mention here, see citation plan):"] +
        [f"  - {u} (seen {n}×)" for u, n in cited.most_common(8)] + ["",
        "## Product-claim check (do before publishing)",
        "- [ ] Every claim about IncuBrix verified by using the feature; screenshot saved.",
        "- [ ] No keyword stuffing; no claim without evidence.",
        "- [ ] Validated in Google's Rich Results Test and Schema.org validator; link result."])

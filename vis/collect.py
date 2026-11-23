"""Collect REAL questions with a recorded source. Nothing is invented:
 - suggest(): Google autocomplete for seed phrases (source_url = the exact request URL)
 - import_csv(): rows exported from keyword tools / forums / People-also-ask; source_url is mandatory."""
import csv, datetime as dt, json, urllib.parse, urllib.request
from .util import norm_question

QUESTION_WORDS = ("how", "what", "which", "can", "does", "is", "are", "should", "why", "best", "vs", "versus", "alternative", "tool", "app", "software", "ai")

def looks_like_creator_question(q: str) -> bool:
    n = norm_question(q)
    return len(n.split()) >= 4 and any(w in n.split() or w in n for w in QUESTION_WORDS)

def suggest(seed: str, gl="us", hl="en", fetch=None):
    url = "https://suggestqueries.google.com/complete/search?" + urllib.parse.urlencode({"client": "firefox", "q": seed, "hl": hl, "gl": gl})
    if fetch is None:
        fetch = lambda u: json.loads(urllib.request.urlopen(u, timeout=30).read().decode("latin-1"))
    data = fetch(url)
    return url, [s for s in data[1] if looks_like_creator_question(s)]

def collect_from_seeds(store, seeds, prefixes=("how to", "best", "can ai", "what is the best"), gl="us", fetch=None, intent_for=None):
    today = dt.date.today().isoformat(); added = dup = 0
    for seed in seeds:
        for pre in prefixes:
            url, sugg = suggest(f"{pre} {seed}", gl=gl, fetch=fetch)
            for s in sugg:
                _, new = store.upsert_question(s, intent=(intent_for or guess_intent)(s), source_type="google_autocomplete",
                                               source_url=url, collected_on=today, priority="Medium")
                added += new; dup += (not new)
    return {"added": added, "duplicates_skipped": dup}

def guess_intent(q: str) -> str:
    n = norm_question(q)
    if " vs " in f" {n} " or "versus" in n or "alternative" in n: return "comparison"
    if n.startswith(("best ", "what is the best", "which ")) or "best " in n: return "best-tool"
    if n.startswith(("how ", "can ")): return "how-to"
    if n.startswith(("what is", "what are")): return "definition"
    return "other"

def import_csv(store, path, source_type_default="manual_import"):
    """Required columns: question, source_url. Optional: source_type, intent, priority, notes.
    Rows without a source_url are REJECTED (invented lists do not count)."""
    ok = rejected = dup = 0; today = dt.date.today().isoformat()
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            q, src = (r.get("question") or "").strip(), (r.get("source_url") or "").strip()
            if not q or not src.startswith("http"):
                rejected += 1; continue
            _, new = store.upsert_question(q, intent=r.get("intent") or guess_intent(q), source_type=r.get("source_type") or source_type_default,
                                           source_url=src, collected_on=r.get("collected_on") or today, priority=r.get("priority", ""), notes=r.get("notes", ""))
            ok += new; dup += (not new)
    return {"added": ok, "rejected_no_source": rejected, "duplicates_skipped": dup}

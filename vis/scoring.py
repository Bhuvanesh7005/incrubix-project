"""Detect IncuBrix mentions/citations and competitor names; compute visibility scores."""
import re
from .util import on_domain

def mentions_brand(text: str, brand_terms) -> bool:
    t = (text or "").lower()
    return any(re.search(r"\b" + re.escape(b.lower()) + r"\b", t) for b in brand_terms)

def cites_brand(urls, brand_domains) -> bool:
    return any(on_domain(u, d) for u in urls for d in brand_domains)

def competitors_in(text: str, urls, competitors) -> list:
    t = (text or "").lower(); found = []
    for c in competitors:
        key = c["name"].lower()
        doms = c.get("domains", [])
        if re.search(r"\b" + re.escape(key) + r"\b", t) or any(on_domain(u, d) for u in urls for d in doms):
            found.append(c["name"])
    return found

def google_position(organic, brand_domains):
    for pos, url, _ in organic:
        if url and any(on_domain(url, d) for d in brand_domains): return pos
    return None

def question_score(ai_checks, google_pos, answer_box_ours: bool) -> float:
    """0-100. 40% Google rank (top3=100, top10=60, top30=25, else 0), 15% owning the answer box,
    45% AI mention-or-citation rate across all AI checks (mention=0.6, citation=1.0 weights)."""
    g = 0 if not google_pos else 100 if google_pos <= 3 else 60 if google_pos <= 10 else 25 if google_pos <= 30 else 0
    if ai_checks:
        ai = sum(100 if c["cited"] else 60 if c["mentioned"] else 0 for c in ai_checks) / len(ai_checks)
    else:
        ai = 0
    return round(0.40 * g + 0.15 * (100 if answer_box_ours else 0) + 0.45 * ai, 1)

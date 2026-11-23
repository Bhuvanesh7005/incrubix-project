#!/usr/bin/env python3
"""Evidence-producing technical audit for a site (stdlib only). Usage: python tools/audit_site.py https://www.incubrix.com [--psi]
Writes audit/<host>-<date>.json (raw evidence you link in the workbook). Only fetches public URLs a normal browser can fetch."""
import json, re, sys, time, datetime as dt, urllib.request, urllib.parse, urllib.error
from html.parser import HTMLParser
from pathlib import Path

UA = {"User-Agent": "IncuBrixAudit/1.0 (+assessment)"}
def get(url, method="GET"):
    t = time.time()
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers=UA, method=method), timeout=30)
        return r.status, dict(r.headers), r.read(2_000_000).decode("utf-8", "replace"), round(time.time() - t, 2), r.geturl()
    except urllib.error.HTTPError as e: return e.code, dict(e.headers), "", round(time.time() - t, 2), url
    except Exception as e: return 0, {}, "", round(time.time() - t, 2), f"{type(e).__name__}: {e}"

class P(HTMLParser):
    def __init__(s): super().__init__(); s.title = ""; s.h1 = 0; s.meta = {}; s.links = []; s.canon = None; s.jsonld = []; s.imgs = []; s.hreflang = []; s._t = s._ld = False; s.scripts_blocking = 0
    def handle_starttag(s, tag, a):
        a = dict(a)
        if tag == "title": s._t = True
        if tag == "h1": s.h1 += 1
        if tag == "meta":
            k = a.get("name") or a.get("property")
            if k: s.meta[k.lower()] = a.get("content", "")
        if tag == "link" and a.get("rel") == "canonical": s.canon = a.get("href")
        if tag == "link" and a.get("rel") == "alternate" and a.get("hreflang"): s.hreflang.append(a["hreflang"])
        if tag == "a" and a.get("href"): s.links.append(a["href"])
        if tag == "img": s.imgs.append(a)
        if tag == "script" and a.get("type") == "application/ld+json": s._ld = True; s.jsonld.append("")
        if tag == "script" and a.get("src") and "async" not in a and "defer" not in a and "type" not in a: s.scripts_blocking += 1
    def handle_endtag(s, tag):
        if tag == "title": s._t = False
        if tag == "script": s._ld = False
    def handle_data(s, d):
        if s._t: s.title += d
        if s._ld: s.jsonld[-1] += d

def audit_page(url):
    st, h, body, secs, final = get(url); p = P(); p.feed(body)
    ld_types = []
    for blob in p.jsonld:
        try:
            d = json.loads(blob); items = d.get("@graph", [d]) if isinstance(d, dict) else d
            ld_types += [i.get("@type") for i in items if isinstance(i, dict)]
        except Exception as e: ld_types.append(f"INVALID_JSON: {e}")
    host = urllib.parse.urlparse(url).netloc
    internal = [l for l in p.links if l.startswith("/") or host in l]
    return {"url": url, "final_url": final, "status": st, "seconds": secs, "bytes": len(body), "content_encoding": h.get("Content-Encoding"),
            "cache_control": h.get("Cache-Control"), "hsts": "Strict-Transport-Security" in h,
            "title": p.title.strip(), "title_len": len(p.title.strip()), "description": p.meta.get("description"),
            "viewport": p.meta.get("viewport"), "h1_count": p.h1, "canonical": p.canon, "robots_meta": p.meta.get("robots"),
            "og_title": p.meta.get("og:title"), "twitter_card": p.meta.get("twitter:card"), "jsonld_types": ld_types, "hreflang": p.hreflang,
            "internal_links": len(internal), "images": len(p.imgs), "images_missing_alt": sum(1 for i in p.imgs if not i.get("alt")),
            "images_missing_size": sum(1 for i in p.imgs if not (i.get("width") and i.get("height"))), "render_blocking_scripts": p.scripts_blocking}

def main():
    base = sys.argv[1].rstrip("/"); out = {"base": base, "checked_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"), "files": {}, "pages": []}
    for f in ("robots.txt", "sitemap.xml", "llms.txt"):
        st, h, body, secs, _ = get(f"{base}/{f}"); out["files"][f] = {"status": st, "bytes": len(body), "head": body[:400]}
    rb = out["files"]["robots.txt"]["head"]; out["files"]["robots.txt"]["has_sitemap_line"] = "sitemap:" in rb.lower()
    out["files"]["robots.txt"]["blocks_all"] = bool(re.search(r"user-agent:\s*\*\s*disallow:\s*/\s*$", rb, re.I | re.M))
    _, _, sm, _, _ = get(f"{base}/sitemap.xml"); urls = re.findall(r"<loc>(.*?)</loc>", sm)[:15] or [base + "/"]
    for u in urls[:15]: out["pages"].append(audit_page(u))
    if "--psi" in sys.argv:   # Google PageSpeed Insights API (free, key optional)
        for strat in ("mobile", "desktop"):
            q = urllib.parse.urlencode({"url": base + "/", "strategy": strat, "category": "performance"})
            st, _, b, _, _ = get("https://www.googleapis.com/pagespeedonline/v5/runPagespeed?" + q)
            try:
                d = json.loads(b); a = d["lighthouseResult"]["audits"]
                out[f"psi_{strat}"] = {"score": d["lighthouseResult"]["categories"]["performance"]["score"], "LCP": a["largest-contentful-paint"]["displayValue"],
                                       "CLS": a["cumulative-layout-shift"]["displayValue"], "TBT": a["total-blocking-time"]["displayValue"]}
            except Exception as e: out[f"psi_{strat}"] = {"error": f"status {st}: {e}"}
    # findings = evidence for fixes
    F = []
    if out["files"]["robots.txt"]["status"] != 200: F.append("robots.txt missing")
    if out["files"]["sitemap.xml"]["status"] != 200: F.append("sitemap.xml missing")
    if out["files"]["llms.txt"]["status"] != 200: F.append("llms.txt missing")
    for p in out["pages"]:
        if not p["title"]: F.append(f"{p['url']}: no <title>")
        elif p["title_len"] > 60: F.append(f"{p['url']}: title {p['title_len']} chars")
        if not p["description"]: F.append(f"{p['url']}: no meta description")
        if not p["viewport"]: F.append(f"{p['url']}: no viewport meta")
        if p["h1_count"] != 1: F.append(f"{p['url']}: {p['h1_count']} H1 tags")
        if not p["canonical"]: F.append(f"{p['url']}: no canonical")
        if not p["jsonld_types"]: F.append(f"{p['url']}: no structured data")
        if p["images_missing_alt"]: F.append(f"{p['url']}: {p['images_missing_alt']} images without alt")
        if p["images_missing_size"]: F.append(f"{p['url']}: {p['images_missing_size']} images without width/height (CLS risk)")
        if not p["content_encoding"]: F.append(f"{p['url']}: no gzip/brotli")
    out["findings"] = F
    Path("audit").mkdir(exist_ok=True); fn = Path("audit") / f"{urllib.parse.urlparse(base).netloc}-{dt.date.today()}.json"
    fn.write_text(json.dumps(out, indent=1)); print(f"wrote {fn}: {len(out['pages'])} pages, {len(F)} findings"); print("\n".join(F[:40]))
if __name__ == "__main__": main()

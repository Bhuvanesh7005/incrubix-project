"""Providers. Each returns a Result with the raw payload so nothing is lost.
Network code uses only the standard library. Keys come from environment variables
(never from the repo). A provider whose key is missing is skipped and logged, not faked."""
from __future__ import annotations
import json, time, urllib.parse, urllib.request, urllib.error
from dataclasses import dataclass, field
from .util import env, extract_urls

class ProviderUnavailable(Exception):
    """Missing key / feature not available. Record it with date+time, do not work around."""

class TransientError(Exception):
    """Retryable failure (HTTP 429/5xx, timeout)."""

@dataclass
class Result:
    provider: str
    text: str = ""
    urls: list = field(default_factory=list)      # cited / quoted source URLs
    organic: list = field(default_factory=list)   # [(position, url, title)] for Google
    answer_box: dict | None = None                # featured snippet / AI Overview summary
    raw: dict = field(default_factory=dict)

def _post(url, payload, headers, timeout=90):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json", **headers}, method="POST")
    return _send(req, timeout)

def _get(url, timeout=90):
    return _send(urllib.request.Request(url), timeout)

def _send(req, timeout):
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:500]
        if e.code in (408, 429) or e.code >= 500:
            raise TransientError(f"HTTP {e.code}: {body}")
        raise RuntimeError(f"HTTP {e.code}: {body}")
    except (urllib.error.URLError, TimeoutError) as e:
        raise TransientError(str(e))

class Provider:
    name = "base"
    kind = "ai"          # "ai" or "google"
    def available(self) -> bool: return True
    def ask(self, question: str, market: dict) -> Result: raise NotImplementedError

class OpenAIProvider(Provider):
    name = "chatgpt"
    def __init__(self, model="gpt-4.1"): self.model = model
    def available(self): return bool(env("OPENAI_API_KEY"))
    def ask(self, q, market):
        if not self.available(): raise ProviderUnavailable("OPENAI_API_KEY not set")
        d = _post("https://api.openai.com/v1/responses",
                  {"model": self.model, "input": q, "tools": [{"type": "web_search", "user_location": {"type": "approximate", "country": market["gl"].upper()}}]},
                  {"Authorization": "Bearer " + env("OPENAI_API_KEY")})
        text, urls = "", []
        for item in d.get("output", []):
            for c in item.get("content", []) or []:
                if c.get("type") == "output_text":
                    text += c.get("text", "")
                    urls += [a["url"] for a in c.get("annotations", []) if a.get("type") == "url_citation"]
        return Result(self.name, text, urls or extract_urls(text), raw=d)

class GeminiProvider(Provider):
    name = "gemini"
    def __init__(self, model="gemini-2.5-flash"): self.model = model
    def available(self): return bool(env("GEMINI_API_KEY"))
    def ask(self, q, market):
        if not self.available(): raise ProviderUnavailable("GEMINI_API_KEY not set")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key=" + env("GEMINI_API_KEY")
        d = _post(url, {"contents": [{"parts": [{"text": q}]}], "tools": [{"google_search": {}}]}, {})
        cand = (d.get("candidates") or [{}])[0]
        text = "".join(p.get("text", "") for p in cand.get("content", {}).get("parts", []))
        chunks = cand.get("groundingMetadata", {}).get("groundingChunks", [])
        return Result(self.name, text, [c["web"]["uri"] for c in chunks if "web" in c], raw=d)

class PerplexityProvider(Provider):
    name = "perplexity"
    def __init__(self, model="sonar"): self.model = model
    def available(self): return bool(env("PERPLEXITY_API_KEY"))
    def ask(self, q, market):
        if not self.available(): raise ProviderUnavailable("PERPLEXITY_API_KEY not set")
        d = _post("https://api.perplexity.ai/chat/completions", {"model": self.model, "messages": [{"role": "user", "content": q}]},
                  {"Authorization": "Bearer " + env("PERPLEXITY_API_KEY")})
        text = d["choices"][0]["message"]["content"]
        urls = d.get("citations") or [r.get("url") for r in d.get("search_results", []) if r.get("url")]
        return Result(self.name, text, urls, raw=d)

class ClaudeProvider(Provider):
    name = "claude"
    def __init__(self, model="claude-sonnet-4-5"): self.model = model
    def available(self): return bool(env("ANTHROPIC_API_KEY"))
    def ask(self, q, market):
        if not self.available(): raise ProviderUnavailable("ANTHROPIC_API_KEY not set")
        d = _post("https://api.anthropic.com/v1/messages",
                  {"model": self.model, "max_tokens": 1500, "messages": [{"role": "user", "content": q}],
                   "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}]},
                  {"x-api-key": env("ANTHROPIC_API_KEY"), "anthropic-version": "2023-06-01"})
        text, urls = "", []
        for b in d.get("content", []):
            if b.get("type") == "text":
                text += b.get("text", "")
                urls += [c["url"] for c in b.get("citations", []) or [] if "url" in c]
            elif b.get("type") == "web_search_tool_result" and isinstance(b.get("content"), list):
                urls += [r["url"] for r in b["content"] if "url" in r]
        return Result(self.name, text, list(dict.fromkeys(urls)), raw=d)

class SerpApiGoogle(Provider):
    """Google results via SerpAPI (a licensed SERP API; we do not scrape google.com directly)."""
    name = "google"; kind = "google"
    def available(self): return bool(env("SERPAPI_KEY"))
    def ask(self, q, market):
        if not self.available(): raise ProviderUnavailable("SERPAPI_KEY not set")
        qs = urllib.parse.urlencode({"engine": "google", "q": q, "gl": market["gl"], "hl": market.get("hl", "en"),
                                     "location": market.get("location", ""), "num": 100, "api_key": env("SERPAPI_KEY")})
        d = _get("https://serpapi.com/search.json?" + qs)
        org = [(o.get("position"), o.get("link"), o.get("title")) for o in d.get("organic_results", [])]
        box = d.get("answer_box") or None
        aio = d.get("ai_overview")
        urls, kinds = [], []
        if box:
            kinds.append("answer_box")
            if box.get("link"): urls.append(box["link"])
        if aio:
            kinds.append("ai_overview")
            urls += [r.get("link") for r in aio.get("references", []) if r.get("link")]
        if kinds:
            box = dict(box or {}); box["kinds"] = kinds
            if aio: box["ai_overview_text"] = json.dumps(aio)[:1500]
        return Result(self.name, (box or {}).get("snippet", "") if box else "", urls, org, box, raw=d)

class MockProvider(Provider):
    """Deterministic offline provider for tests and demos ONLY. Its output is stored in a
    separate demo database and is never exported as real measurement."""
    def __init__(self, name="mock", kind="ai", mention_every=3):
        self.name, self.kind, self.mention_every = name, kind, mention_every
    def ask(self, q, market):
        h = sum(map(ord, q + self.name)) % 6
        brands = ["IncuBrix"] if h % self.mention_every == 0 else []
        comps = ["Opus Clip", "Descript", "CapCut"][: (h % 3) + 1]
        text = f"[DEMO] For '{q}', tools include " + ", ".join(brands + comps) + ". See https://example.com/guide-%d" % h
        if self.kind == "google":
            org = [(i + 1, f"https://site{i}.example/{h}", f"Result {i}") for i in range(10)]
            if brands: org[h % 10] = (h % 10 + 1, "https://www.incubrix.com/guide", "IncuBrix guide")
            return Result(self.name, "", [], org, {"kinds": ["answer_box"], "snippet": text, "link": "https://example.com/x"} if h % 2 else None, raw={"demo": True})
        return Result(self.name, text, ["https://example.com/guide-%d" % h] + (["https://www.incubrix.com"] if brands else []), raw={"demo": True})

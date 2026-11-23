import hashlib, json, logging, os, re, time, unicodedata
from pathlib import Path

def norm_question(q: str) -> str:
    """Normalise a question so near-identical duplicates collapse to one key."""
    q = unicodedata.normalize("NFKC", q).lower().strip()
    q = re.sub(r"[^\w\s']", " ", q)
    return re.sub(r"\s+", " ", q).strip()

def qid_for(q: str) -> str:
    return "Q" + hashlib.sha1(norm_question(q).encode()).hexdigest()[:8].upper()

def setup_logging(log_dir: str) -> logging.Logger:
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    lg = logging.getLogger("vis")
    if not lg.handlers:
        lg.setLevel(logging.INFO)
        fh = logging.FileHandler(Path(log_dir) / "engine.log")
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        sh = logging.StreamHandler()
        sh.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
        lg.addHandler(fh); lg.addHandler(sh)
    return lg

def log_error(log_dir: str, **fields):
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    fields["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    with open(Path(log_dir) / "errors.jsonl", "a") as f:
        f.write(json.dumps(fields) + "\n")

def env(name: str, default=None):
    return os.environ.get(name, default)

URL_RE = re.compile(r"https?://[^\s)\]>\"']+")
def extract_urls(text: str):
    return [u.rstrip(".,;") for u in URL_RE.findall(text or "")]

def domain_of(url: str) -> str:
    m = re.match(r"https?://(?:www\.)?([^/:?#]+)", url or "")
    return m.group(1).lower() if m else ""

def on_domain(url: str, domain: str) -> bool:
    """True for the domain itself or a subdomain (not 'notexample.com' for 'example.com')."""
    d = domain_of(url)
    return d == domain or d.endswith("." + domain)

def norm_priority(p):
    """Map P1/P2/P3 or free text to the workbook's High/Medium/Low (default Medium)."""
    return {"p1": "High", "high": "High", "p2": "Medium", "medium": "Medium", "p3": "Low", "low": "Low"}.get((p or "").strip().lower(), "Medium")

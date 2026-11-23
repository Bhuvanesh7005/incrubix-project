# IncuBrix Visibility Engine (Option 3: AEO · SEO · GEO)

Measures how visible IncuBrix is on **Google** and **4 AI assistants** (ChatGPT, Gemini, Perplexity, Claude) for a set of real creator questions,
stores every raw answer, scores visibility, writes a weekly report, alerts on changes, and generates a brief for each new page.
Pure Python 3.11+ standard library — nothing to install (tests need `pytest`).

## One run command
```bash
python -m vis weekly
```
That runs today's checks (resumable), writes `data/reports/<date>.md`, and prints alerts. Run it on **two different days** before `export`.

## First-time setup (5 minutes)
```bash
export SERPAPI_KEY=...  OPENAI_API_KEY=...  GEMINI_API_KEY=...  PERPLEXITY_API_KEY=...  ANTHROPIC_API_KEY=...   # any subset; missing = skipped + logged, never faked
python -m vis import questions.csv        # real questions: columns question,source_url[,source_type,intent,priority,notes]
python -m vis collect --seeds seeds.txt   # optional: Google autocomplete suggestions (source URL recorded)
python -m vis weekly                      # day 1
python -m vis weekly                      # day 2 (or: python -m vis run --date YYYY-MM-DD)
python -m vis export --out visibility.csv # official column order, quality-gated
```
No keys at all? `python -m vis --demo ...` uses an offline mock and a **separate** `demo_data/` folder. Demo output is labelled and is never real measurement.

## Web interface
```bash
python -m vis serve            # then open http://127.0.0.1:8765
```
Dashboard (scores, competitors, alerts, weekly report), Questions (add with a required source link, CSV import, autocomplete collection), Run (provider key status, date, repeats, limit, failure simulation in demo mode), Results (sortable table, click a row for the page brief and every raw answer) and Export (downloads `visibility.csv`).
The **Demo / Live** switch at the top keeps mock data and real data in separate folders (`demo_data/` and `data/`); demo mode is bannered so it cannot be mistaken for real measurement. The server listens on localhost only; keys stay in environment variables (`$env:OPENAI_API_KEY="..."` in PowerShell) set before you start it.

## Commands
| Command | What it does |
|---|---|
| `import FILE.csv` | Adds questions. Rows **without a `source_url` are rejected**. Duplicates (normalised) are skipped. |
| `collect --seeds FILE` | Google autocomplete for each seed × prefix; records the exact request URL as the source. |
| `run [--date D] [--repeat N] [--limit N]` | Checks Google (3 markets) + AI assistants (each repeated, default 2×). Skips anything already stored → no duplicates; interrupted runs resume. |
| `report` / `weekly` | Weekly Markdown report with deltas vs the previous check date. |
| `alerts` | Lists overall / per-question score moves; exit code 2 when something changed (use in cron/CI). Set `ALERT_WEBHOOK_URL` to push to Slack/Teams. |
| `export --out visibility.csv` | Writes the official columns. Fails unless two different days exist; rows missing a source/date/raw path are rejected. |
| `brief QID` | Page brief for a question: structure, schema type, competitors, pages already cited, product-claim checklist. |

## What is stored (reproducibility)
`data/raw/<date>/<provider>/<market>/<QID>_a<attempt>.json` — date, time, provider, market, **location setting**, the question, full answer text, cited URLs, Google organic results and answer-box/AI-overview payload.
`data/vis.db` — SQLite index. Scores are always recalculated from it; nothing is typed in by hand.
AI-assistant APIs cannot all be geo-pinned: the location field says "set via API" or "not configurable via API; provider default" so it is never overstated.

## Scoring (0-100 per question, recomputed every run)
40% Google rank (top 3 = 100, top 10 = 60, top 30 = 25) + 15% owning the answer box/AI Overview + 45% AI score (cited = 100, mentioned = 60, absent = 0, averaged over every AI check).
Report metrics: AI mention rate, AI citation rate, Google top-10 rate, answer share.

## Reliability
* Transient errors (HTTP 408/429/5xx, timeouts) retry with exponential backoff (`[run] retries`).
* A hard failure on one item is written to `data/logs/errors.jsonl` and the run continues.
* A provider with no API key is skipped and logged with date/time (the brief asks you to record unavailable sources, not work around them).
* Demo of recovery: `python -m vis --demo run --flaky` fails the first call on purpose, retries, and finishes with `errors: 0`.

## Runtime and cost at scale
Each question costs ≈ 1 SERP call × 3 markets + 4 assistants × 2 repeats (+ 2 extra ChatGPT markets) ≈ 15 API calls.
300 questions ≈ 4,500 calls; with sequential calls at ~6 s ≈ 7.5 h, so run overnight or add parallelism per provider. Rough direct cost at list prices is
**tens of USD per full run** (dominated by the SERP API and web-search-enabled model calls). Always confirm current pricing and put the real figure in the workbook.
`--limit` and the per-day resume make partial/cheaper runs easy.

## Schedule + alerts
Cron: `0 9 * * 1 cd /path/to/repo && python -m vis weekly` · or use `.github/workflows/weekly.yml` (secrets in repo settings, never in files).

## Tests
```bash
pip install pytest && python -m pytest -q     # 11 tests: dedupe, source gate, idempotence, retry, hard-failure logging, missing key, 2-day export, scoring, report/alerts/brief
```

## Compliance
Uses licensed APIs (SERP API, model APIs) rather than scraping google.com or logged-in chat UIs. No posting, no contacting site owners. No secrets in the repository (`.env` is git-ignored).

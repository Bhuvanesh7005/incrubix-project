# Video scripts (read in your own words; speak slowly)

Rules from the brief: both videos must be **unedited**, in your own voice, and honest. The first video needs the real product, so the "say" lines below tell you what to cover, not what the product does.

---
## VIDEO B: Technical demo (max 8 min) - run `demo.ps1`

**Before recording:** open PowerShell in `engine_repo`, make the font large, close other apps, then start your recorder (Win+G or OBS). Run:
`powershell -ExecutionPolicy Bypass -File .\demo.ps1`
The script pauses at every scene so you can talk.

**0:00 Intro (30 s)** - "Hi, I'm <name>. This is my Option 3 engine for IncuBrix. It measures how visible IncuBrix is on Google and four AI assistants, stores every raw answer, scores it and writes a weekly report. One command runs everything: `python -m vis weekly`."
Show README.md briefly.

**Scene 1 Tests (30 s)** - "First, ten automated tests: duplicates, the source-link rule, retries, failure logging and the export format."

**Scene 2 Normal run (60 s)** - "I import questions. A row without a source link is rejected, because invented questions don't count. This demo uses a mock provider and a separate folder, so it is not real measurement. The real run uses licensed APIs."

**Scene 3 Failure and recovery (60 s)** - "Here the first call fails on purpose. The engine retries with backoff and finishes with errors: 0. A hard failure on one item would be written to logs/errors.jsonl and the run would continue. A missing API key is skipped and logged, never faked."

**Scene 4 Second day (30 s)** - "The brief needs two different days. This is day two."

**Scene 5 No duplicates (45 s)** - "Same input again: saved 0, skipped 75. Re-running never duplicates, and an interrupted run resumes."

**Scene 6 Report (45 s)** - "The weekly report: overall score, AI mention and citation rate, Google top-10 rate, answer share, competitors and the biggest gaps. Scores are recalculated from stored data, never typed."

**Scene 7 Evidence (45 s)** - "Every check keeps a raw file with date, time, provider, market, the location setting and the full answer, so a reviewer can trace any number."

**Scene 8 Refresh on new input (60 s)** - "I add one new question. Only that one is processed; existing items update without duplicates."

**Scene 9 Export (45 s)** - "The export checks each row before writing, and uses the official columns and dropdown values from the workbook."

**Close (30 s)** - "Limits, honestly: this demo used mock data. I'd change X" (pick one real decision you would change, the live review asks for it). "Weekly scheduling is in `.github/workflows/weekly.yml`. Thank you."

---
## VIDEO A: Product walkthrough (max 5 min) - needs your IncuBrix access

Record your screen while using IncuBrix with the login from your invitation email. Suggested structure:
- **0:00-0:30** Who you are, what IncuBrix is *in your own words after using it*.
- **0:30-3:30** Do one real task start to finish. Say what you click and what happens. Show 1 thing that worked well and 1 thing that was hard or confusing.
- **3:30-4:30** Tie it to growth: which of your 5 observations matter for search and AI visibility, and the 3 biggest opportunities.
- **4:30-5:00** What you will do next.
Only say things you actually saw. Note the date and time of any feature that was unavailable.

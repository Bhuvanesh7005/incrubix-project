# IncuBrix technical demo runner. Press Enter between scenes so you can talk.
# Run from the engine_repo folder:  powershell -ExecutionPolicy Bypass -File .\demo.ps1
$ErrorActionPreference = "Stop"
function Scene($title) { Write-Host "`n=== $title ===" -ForegroundColor Cyan; Read-Host "Press Enter to run" | Out-Null }
function Run($cmd) { Write-Host "PS> $cmd" -ForegroundColor Yellow; Invoke-Expression $cmd }
Clear-Host
Scene "Scene 1: tests (10 passing)"
Run "python -m pytest -q"
if (Test-Path demo_data) { Remove-Item -Recurse -Force demo_data }
Scene "Scene 2: NORMAL RUN - import questions (rows without a source link are rejected)"
Run "python -m vis --demo import data\DEMO_questions_NOT_REAL.csv"
Scene "Scene 3: FAILURE + RECOVERY - first call fails on purpose, engine retries"
Run "python -m vis --demo run --date 2026-03-01 --flaky"
Scene "Scene 4: second day of checks"
Run "python -m vis --demo run --date 2026-03-02"
Scene "Scene 5: SAME INPUT AGAIN - no duplicates (saved: 0)"
Run "python -m vis --demo run --date 2026-03-02"
Scene "Scene 6: weekly report"
Run "python -m vis --demo report"
Scene "Scene 7: raw answer evidence"
$f = Get-ChildItem demo_data\raw -Recurse -Filter *.json | Select-Object -First 1
Run "Get-Content '$($f.FullName)' -TotalCount 20"
Scene "Scene 8: REFRESH ON NEW INPUT - add one question, only it is processed"
Add-Content data\DEMO_questions_NOT_REAL.csv "how to caption podcast clips,https://demo.invalid/not-a-real-source"
Run "python -m vis --demo import data\DEMO_questions_NOT_REAL.csv"
Run "python -m vis --demo run --date 2026-03-02"
Scene "Scene 9: export in the official format"
Run "python -m vis --demo export --out demo_data\visibility.csv"
Run "Get-Content demo_data\visibility.csv -TotalCount 3"
Write-Host "`nDone. Stop recording." -ForegroundColor Green

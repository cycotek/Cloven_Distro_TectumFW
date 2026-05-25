# TectumFW — Session Handoff

**Last updated:** 2026-05-25  
**Repo:** `C:\Users\bmaas\repo\Cloven_Distro_TectumFW`  
**GitHub:** https://github.com/cycotek/Cloven_Distro_TectumFW  
**Branch:** main  
**Stack:** `docker compose up -d` — all 4 containers running (ollama, db, api, fetcher)

---

## What was built (complete)

The full TectumFW stack is done and pushed. All 37 core tasks completed:

- **3-tier routing**: semantic memory cache → direct fast-path → full quorum with R1 synthesis
- **Semantic memory**: nomic-embed-text embeddings in pgvector, cosine similarity ≥ 0.82 = cache hit
- **Direct path**: immutable facts (math, constants) served by llama3.2:3b, TTL 365 days
- **Quorum**: 3 contributor models in parallel (OLLAMA_NUM_PARALLEL=3), DeepSeek-R1:14b synthesis
- **Auto-fetch**: news-intent queries trigger tectum_fetcher automatically
- **Fetcher**: shared httpx client, BeautifulSoup in thread pool, batch size 10
- **UI**: full terminal-themed single-page app at localhost:8000
- **README**: complete with architecture diagram, API reference, UI walkthrough

---

## What's still needed (task #38)

**8 UI screenshots** for the README — saved to `assets/screenshots/`:

| Filename | Status | What to capture |
|---|---|---|
| `ui_query_panel.png` | ❌ needed | Query panel — chips, synthesis selector, Research Mode toggle |
| `ui_status_bar.png` | ❌ needed | Mid-request status bar — "QUORUM · Checking memory…" |
| `ui_badges_memory.png` | ❌ needed | Badge row close-up — `⬡ DIRECT` + `⚡ FROM MEMORY` |
| `ui_memory_hit.png` | ❌ needed | Memory meta bar — sim%, age, serve count |
| `ui_full_memory.png` | ❌ needed | Full view — query + badges + cached synthesis |
| `ui_history.png` | ❌ needed | Full UI with history sidebar |
| `ui_model_cards.png` | ❌ needed | Three contributor cards from a full quorum run |
| `ui_synthesis.png` | ❌ needed | R1 synthesis panel with ▶ Reasoning block expanded |

Currently in `assets/screenshots/`: only `test.png` (a test shot from Chrome headless).

---

## Screenshot approach that works

Chrome headless (`chrome.exe`) running on Windows can take screenshots via `--screenshot` flag. This was proven working:

```bash
# From WSL2 terminal at localhost:7681 (bash on TheCloven)
CHROME="/mnt/c/Program Files/Google/Chrome/Application/chrome.exe"
SHOTS_WIN=$(wslpath -w "/mnt/c/Users/bmaas/repo/Cloven_Distro_TectumFW/assets/screenshots")
"$CHROME" --headless=new --disable-gpu --window-size=1456,819 \
  --screenshot="$SHOTS_WIN\\filename.png" "http://localhost:8000/" 2>/dev/null
```

This produced a valid 70KB PNG. **The `wslpath -w` conversion is required** — Chrome.exe doesn't understand Linux WSL2 paths.

### Limitation: static pages only

`--screenshot` takes a snapshot at page load. It doesn't support triggering JS actions (like clicking "Run Quorum" or loading a specific job).

---

## CDP approach (partially working, needs firewall fix)

`take_screenshots.py` in the repo root uses Chrome DevTools Protocol to:
1. Start Chrome headless with `--remote-debugging-port=9224`
2. Connect via WebSocket (Python `websockets` library — already installed via `pip3 install websockets --break-system-packages`)
3. Navigate to pages, call `loadJob('job-id')` via JS, wait for render, capture PNG

**Problem:** Chrome.exe binds CDP to Windows `127.0.0.1:9224`. From WSL2, the Windows host is at `172.24.224.1` (detected automatically by the script), but Windows Firewall blocks WSL2→Windows on port 9224.

**Fix options (pick one):**

**Option A — Run the Python script on Windows directly (recommended):**
```powershell
# In PowerShell (Windows-side, not WSL2):
pip install websockets
python C:\Users\bmaas\repo\Cloven_Distro_TectumFW\take_screenshots.py
```
Python3 may need to be installed on Windows if not present. The script's `CHROME` path is already the Windows WSL2-style path — change line 25 to:
```python
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
```
(The script has a WSL2 path `"/mnt/c/Program Files/..."` which only works from WSL2.)

**Option B — Add Windows Firewall rule to allow WSL2 → port 9224:**
```powershell
# In PowerShell as Administrator:
New-NetFirewallRule -DisplayName "Chrome CDP WSL2" -Direction Inbound -Protocol TCP -LocalPort 9224 -Action Allow
```
Then run from WSL2 terminal as before.

**Option C — Use `--screenshot` with JS injection via a custom HTML redirect page:**
Write a temp HTML file that auto-submits to the API, then screenshot that. Only works for states achievable from a URL.

---

## How to load specific result states for screenshots

The TectumFW UI has a `loadJob(jobId)` function. In the CDP script this works:
```javascript
loadJob('some-job-uuid')  // loads a completed result into the UI
```

Get job IDs from the API:
```bash
curl http://localhost:8000/quorum/history?limit=20
```

Look for:
- **Memory hit** (direct intent, speed of light): `intent=direct`, `question` contains "speed of light"  
- **Model cards + synthesis**: `intent=reference`, completed quorum — look for "diabetes", "stars", "woodchuck"

---

## Key files

```
Cloven_Distro_TectumFW/
├── take_screenshots.py          ← CDP screenshot script (WSL2-ready, needs firewall fix OR run on Windows)
├── assets/screenshots/          ← destination for all 8 PNG files
│   └── test.png                 ← proof-of-concept Chrome headless shot
├── README.md                    ← full docs, references all 8 screenshot filenames
├── docker-compose.yml           ← 4-service stack (ollama, db, api, fetcher)
├── .env                         ← local config (not in git)
├── tectum_framework/
│   ├── api_server/
│   │   ├── main.py              ← 3-tier router, memory layer, FastAPI
│   │   ├── quorum.py            ← parallel fan-out + R1 synthesis
│   │   ├── memory.py            ← pgvector embed/search/store
│   │   └── static/index.html   ← full terminal UI
│   └── fetcher/
│       ├── main.py              ← FastAPI service
│       ├── optimizer.py         ← intent classifier (temp=0, deterministic)
│       ├── crawler.py           ← ant crawler, shared httpx client
│       └── fetchers/web.py      ← BS4 in thread pool
```

---

## Uncommitted changes

The git index has a corruption (`fatal: unable to read 7cf295cc...`) — run from WSL2 terminal:

```bash
cd /mnt/c/Users/bmaas/repo/Cloven_Distro_TectumFW
git fsck --unreachable 2>&1 | head -5
# If index is corrupt:
rm .git/index && git reset
git status
```

Files changed since last commit (based on working tree):
- `take_screenshots.py` — new file (screenshot tool)
- `assets/screenshots/test.png` — test shot

After taking all 8 screenshots, commit with:
```bash
git add assets/screenshots/ take_screenshots.py
git commit -m "docs: add UI screenshots for README"
git push
```

---

## Stack health check

```bash
# All containers running?
docker ps --format "table {{.Names}}\t{{.Status}}"

# API healthy?
curl http://localhost:8000/health

# Memory working?
curl "http://localhost:8000/memory/search?q=speed+of+light&threshold=0.8"
```

---

## Models loaded

| Model | Role | VRAM |
|---|---|---|
| `llama3.2:3b` | Intent classifier + direct path | ~2GB |
| `qwen2.5:7b` | Contributor | ~5GB |
| `mistral-nemo:12b` | Contributor | ~8GB |
| `deepseek-r1:14b` | Synthesis (R1 reasoning) | ~10GB |
| `nomic-embed-text` | Memory embeddings | small |

OLLAMA_NUM_PARALLEL=3, OLLAMA_MAX_LOADED_MODELS=4 set in docker-compose.yml.

---

## Recommended next session start

1. Open WSL2 terminal at `C:\Users\bmaas\repo\Cloven_Distro_TectumFW`
2. Confirm stack is up: `docker ps`
3. Open http://localhost:8000 in Chrome — UI should show full history sidebar
4. Take the 8 screenshots using **Option A** (PowerShell + Python on Windows side) or **Option B** (firewall rule)
5. Commit and push
6. Delete `take_screenshots.py` and `SESSION_HANDOFF.md` if no longer needed

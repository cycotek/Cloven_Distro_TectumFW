# TectumFW — Session Handoff

**Last updated:** 2026-05-25  
**Repo:** `C:\Users\bmaas\repo\Cloven_Distro_TectumFW`  
**GitHub:** https://github.com/cycotek/Cloven_Distro_TectumFW  
**Branch:** main  
**Stack:** `docker compose up -d` — all 4 containers running (ollama, db, api, fetcher)

---

## What is complete

All 38 tasks done and pushed to GitHub:

- **3-tier routing**: semantic memory cache → direct fast-path → full quorum with R1 synthesis
- **Semantic memory**: nomic-embed-text embeddings in pgvector, cosine similarity ≥ 0.82 = cache hit
- **Direct path**: immutable facts (math, constants) served by llama3.2:3b, TTL 365 days
- **Quorum**: 3 contributor models in parallel (OLLAMA_NUM_PARALLEL=3), DeepSeek-R1:14b synthesis
- **Auto-fetch**: news-intent queries trigger tectum_fetcher automatically
- **Fetcher**: shared httpx client, BeautifulSoup in thread pool, batch size 10
- **UI**: full terminal-themed single-page app at localhost:8000
- **README**: complete with architecture diagram, API reference, UI walkthrough, all 8 screenshots
- **HANDBOOK.md**: living reference — routing behavior, thresholds, model swap, ops notes, quirks
- **git_push.sh**: authenticated push via GITHUB_USER + GITHUB_TOKEN from .env — `bash git_push.sh`

---

## Git / push workflow

```bash
# From WSL2 terminal — stages everything, commits, pushes via token in .env
bash /mnt/c/Users/bmaas/repo/Cloven_Distro_TectumFW/git_push.sh

# With a custom commit message
bash git_push.sh "feat: your message here"
```

Token lives in `.env` as `GITHUB_TOKEN` — never in git history. `.env` is gitignored.

---

## Ecosystem context

TectumFW is one node in a planned constellation of hardened local MCPs:

| MCP | Status | Purpose |
|-----|--------|---------|
| **TectumFW** | ✅ Running — `localhost:8000` | Multi-model reasoning, semantic memory, web fetch |
| **UniFi MCP** | ✅ Running — `192.168.1.232:8100` | Network intelligence — devices, clients, firewall, events, DPI |
| **Log Analysis MCP** | 🔲 Next build | SIEM intake, log normalization, contextual ops reasoning |

Philosophy: harden each MCP independently, then compose the best pieces into unified solutions. Don't consolidate until each layer is breakproof.

All outbound traffic routes through Cloudflare. Everything runs locally — no cloud LLM calls.

---

## Immediate fix needed

**IPS false positive:** 192.168.1.232 (UniFi MCP / AI server) is being flagged by CyberSecure for connecting to GitHub (140.82.114.4). It's polluting Security events. Whitelist it before building log analysis or the signal will be noisy from day one.

```bash
# Create a trusted hosts firewall group via UniFi MCP
curl -X POST http://192.168.1.232:8100/firewall/groups \
  -H "Content-Type: application/json" \
  -d '{"name": "Trusted AI Hosts", "group_type": "address-group", "members": ["192.168.1.232"]}'
```

Then add an IPS exception referencing that group in the UniFi console.

---

## Next builds (in order)

### 1. SIEM intake endpoint on TectumFW

UniFi has a native "Export to SIEM Server" button (bottom-left of the Network logs view). Build a `/siem` intake endpoint that receives those structured log events, normalizes them, and wires them into TectumFW's existing `logs` intent. This is the foundation for everything else.

**What to build:**
- POST endpoint `/siem` on `cloven_tectum_api` (or a new sidecar container)
- Accept UniFi syslog/JSON format, normalize to a standard event schema
- Store events in a new `network_events` table in postgres
- When `intent=logs`, query recent events as context before running quorum
- Point UniFi SIEM export at `http://<TheCloven IP>:<port>/siem`

**UniFi events endpoint for reference (polling fallback):**
```bash
curl http://192.168.1.232:8100/events?limit=200&filter=Security
```
Categories worth routing to `logs` intent: Security (78), VPN (272), Internet and WAN (44)

### 2. Fetcher content sanitization

Before exposing TectumFW as an MCP to other LLMs, harden the fetcher against:
- Ad text embedded in otherwise-clean pages (high link density = reject chunk)
- Prompt injection in crawled content (scan for instruction-like patterns before injecting into model prompts)
- Known bad domains (blocklist pass before crawl)

Lives in `tectum_framework/fetcher/crawler.py` — add a `sanitize(content)` pass after BS4 extraction, before the context assembler.

### 3. MCP protocol exposure on TectumFW

Expose TectumFW as a proper stdio MCP server so other LLMs on the network can call it as a tool — same pattern as `unifi-mcp`. Other agents call it and get back cached, reasoned, network-aware answers.

**What to build:**
- `tectum_mcp/` directory alongside `tectum_framework/`
- stdio MCP server wrapping the existing `/quorum/sync` and `/memory/search` endpoints
- Tools to expose: `ask_tectum(question)`, `search_memory(query)`, `fetch_context(topic)`
- Register in Claude Desktop / Open WebUI as a tool provider

This is the "SaaMCP" milestone — TectumFW becomes callable by any LLM on the network.

---

## Key files

```
Cloven_Distro_TectumFW/
├── git_push.sh                  ← authenticated push via .env token
├── SESSION_HANDOFF.md           ← this file
├── HANDBOOK.md                  ← living capability reference
├── README.md                    ← full docs + all 8 screenshots
├── assets/screenshots/          ← all 8 UI PNGs (complete)
├── docker-compose.yml           ← 4-service stack (ollama, db, api, fetcher)
├── .env                         ← local config + GITHUB_TOKEN (gitignored)
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
└── unifi-mcp (separate repo)
    └── running at 192.168.1.232:8100
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

# UniFi MCP alive?
curl http://192.168.1.232:8100/info
```

---

## Models

| Model | Role | VRAM |
|-------|------|------|
| `llama3.2:3b` | Intent classifier + direct path | ~2GB |
| `qwen2.5:7b` | Contributor | ~5GB |
| `mistral-nemo:12b` | Contributor | ~8GB |
| `deepseek-r1:14b` | Synthesis (R1 reasoning) | ~10GB |
| `nomic-embed-text` | Memory embeddings | small |

`OLLAMA_NUM_PARALLEL=3`, `OLLAMA_MAX_LOADED_MODELS=4` in docker-compose.yml.

---

## Session start checklist

1. `docker ps` — confirm all 4 containers up
2. `curl http://localhost:8000/health` — API healthy
3. `curl http://192.168.1.232:8100/info` — UniFi MCP alive
4. Open http://localhost:8000 — UI loads with history sidebar
5. Pick up next build from the list above

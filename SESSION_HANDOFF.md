# TectumFW — Session Handoff

**Last updated:** 2026-06-11  
**Repo:** `C:\Users\bmaas\repo\Cloven_Distro_TectumFW`  
**GitHub:** https://github.com/cycotek/Cloven_Distro_TectumFW  
**Branch:** main  

---

## What is complete (as of 2026-06-11)

### Core reasoning stack
- **3-tier routing**: semantic memory cache → direct fast-path → full quorum with R1 synthesis
- **Semantic memory**: nomic-embed-text embeddings in pgvector, cosine similarity ≥ 0.82 = cache hit
- **Direct path**: immutable facts (math, constants) served by llama3.2:3b, TTL 365 days
- **Quorum**: 3 contributor models in parallel (OLLAMA_NUM_PARALLEL=3), DeepSeek-R1:14b synthesis
- **Auto-fetch**: news-intent queries trigger tectum_fetcher automatically
- **Fetcher**: shared httpx client, BeautifulSoup in thread pool, batch size 10
- **UI**: full terminal-themed single-page app (port 8000 bundled / 8800 standalone)
- **MCP / SaaMCP Router**: `http://192.168.1.173:8802/mcp`
- **SIEM pipeline**: UniFi MCP → poller → TectumFW `/siem` — fully operational

### SIEM pipeline — completed 2026-06-11

Full UniFi → TectumFW SIEM pipeline is operational end-to-end.

**Flow:**
```
UniFi MCP (localhost:8100)
    ↓  systemd poller polls every 30s
TectumFW API (192.168.1.173:8800/siem)
    ↓
siem_events table (PostgreSQL + pgvector, Syn1)
```

**Why the poller runs on the ai server, not Syn1:**  
Syn1 → ai server port 8100 times out (wireless client isolation / UniFi LAN firewall rule). ai server → Syn1 over wired works fine. The poller uses `localhost` for the MCP — no asymmetry issue.

**SIEM endpoints (TectumFW v0.8.0, Syn1):**
```bash
POST http://192.168.1.173:8800/siem          # ingest event
GET  http://192.168.1.173:8800/siem/events   # list stored events (?limit=N)
GET  http://192.168.1.173:8800/siem/stats    # by_severity, events_last_hour, high_critical_24h
```

**Poller service (ai server 192.168.1.232):**
```bash
systemctl --user status siem-poller
journalctl --user -u siem-poller -n 50
systemctl --user restart siem-poller

# Files
~/siem-poller/poller.py                         # stdlib-only, no pip deps
~/siem-poller/.env                              # UNIFI_MCP_URL, UNIFI_MCP_KEY, TECTUM_SIEM_URL
~/.config/systemd/user/siem-poller.service
```

Linger enabled (`loginctl enable-linger cloven`) — persists across logouts and reboots.

**Note:** `cloven_tectum_siem_poller` is defined in `docker-compose.synology.yml` but **stopped** on Syn1. The live poller is the systemd service above.

### IPS false positive — resolved
192.168.1.232 connecting to GitHub (140.82.114.4) was generating CyberSecure alerts. IPS exception added.

---

## Git / push workflow

```bash
bash /mnt/c/Users/bmaas/repo/Cloven_Distro_TectumFW/git_push.sh
bash git_push.sh "feat: your message here"
```

Token lives in `.env` as `GITHUB_TOKEN` — never in git history. `.env` is gitignored.

**Uncommitted changes pending push (as of 2026-06-11):**
- `.env.standalone.example` — SIEM env vars documented
- `.github/workflows/publish-images.yml` — siem_poller image added
- `docker-compose.synology.yml` — siem_poller service defined
- `tectum_framework/api_server/main.py` — v0.8.0 with /siem endpoints

---

## Ecosystem

| Service | Host | IP | Port | Status |
|---------|------|----|------|--------|
| **TectumFW API** | Syn1 (DS2418+) | 192.168.1.173 | 8800 | ✅ v0.8.0 |
| **TectumFW Fetcher** | Syn1 | 192.168.1.173 | 8801 | ✅ Running |
| **TectumFW MCP** | Syn1 | 192.168.1.173 | 8802 | ✅ Running |
| **PostgreSQL + pgvector** | Syn1 | 192.168.1.173 | 55432 | ✅ Running |
| **UniFi MCP** | ai server | 192.168.1.232 | 8100 | ✅ Running |
| **SIEM Poller** | ai server | 192.168.1.232 | — (systemd) | ✅ Running |

All inference stays local. All outbound traffic through Cloudflare.

---

## Stack health check

```bash
# TectumFW
curl http://192.168.1.173:8800/health
curl http://192.168.1.173:8800/siem/stats

# UniFi MCP (run from ai server)
curl -H "Authorization: Bearer $MCP_API_KEY" http://localhost:8100/events?limit=5

# SIEM poller (run on ai server)
systemctl --user status siem-poller

# Docker stack (on Syn1 via SSH)
cd /volume1/docker/tectum
sudo /usr/local/bin/docker compose -f docker-compose.synology.yml ps
```

**Updating the API container on Syn1:**  
`sudo docker` fails on Synology (secure PATH issue). Use DSM Task Scheduler (Scheduled Task → User-defined script, Owner: root):
```bash
#!/bin/bash
DOCKER=$(find /var/packages/ContainerManager/target/usr/bin /usr/local/bin -name docker -type f 2>/dev/null | head -1)
cd /volume1/docker/tectum
$DOCKER pull ghcr.io/cycotek/tectum-api:latest
$DOCKER compose -f docker-compose.synology.yml up -d cloven_tectum_api
```
Delete the task after it runs to prevent midnight re-execution.

---

## Next builds (in order)

1. **Self-healing automation loop** (UniFi + Synology + Tectum) — **now unblocked** by SIEM pipeline
2. **GUI: stats/observability page + pgvector memory browser + health panel** (#13)
3. **Fix `DELETE /memory/{id}`** — documented in HANDBOOK but missing from `main.py` (#12)
4. **ttyd ↔ Claude Cowork ↔ Claude Code handoff workflow** (#1)
5. **Fetcher scale-test + depth-level controls** (#2)
6. **Synology SAN MCP server** (#3)
7. **Expose TectumFW as stdio MCP server** (SaaMCP milestone, #11)
8. **Define pgvector as long-term quorum memory** (#6)
9. **Fix cache miss UI override + badge metadata on history reload** (#7)
10. **Harden fetcher sanitization before MCP exposure** (#10)

---

## Key files

```
Cloven_Distro_TectumFW/
├── git_push.sh
├── SESSION_HANDOFF.md           ← this file
├── HANDBOOK.md                  ← ops reference + SIEM ops section
├── ROADMAP.md                   ← punch list
├── README.md                    ← user-facing docs + API reference
├── README.standalone.md         ← NAS/Synology deployment guide
├── docker-compose.synology.yml  ← 5-service Syn1 stack (db, api, fetcher, mcp, siem_poller)
├── .env.standalone.example      ← config template (includes SIEM vars)
├── .github/workflows/
│   └── publish-images.yml       ← GHCR build: tectum-{api,fetcher,mcp,siem-poller}
└── tectum_framework/
    └── api_server/
        ├── main.py              ← 3-tier router + /siem endpoints (v0.8.0)
        └── schema.sql           ← siem_events table + indexes

# ai server (192.168.1.232) — not in repo:
~/siem-poller/poller.py
~/siem-poller/.env
~/.config/systemd/user/siem-poller.service
```

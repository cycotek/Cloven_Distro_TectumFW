# TectumFW Handbook

Living reference for the Cloven Distro TectumFW stack. Add notes here as capabilities are refined, tuned, or discovered.

---

## Routing Behavior

### When does a query hit each tier?

| Tier | Trigger condition | Typical latency |
|------|------------------|-----------------|
| Memory cache | Cosine similarity ≥ 0.82 to a stored embedding | < 200ms |
| Direct fast-path | `intent=direct` (immutable facts, math, constants) and cache miss | ~3s warm |
| Full quorum | `intent=reference` or `intent=news` and cache miss | 30–120s depending on models loaded |

### Intent classifications

The optimizer (llama3.2:3b, temp=0) classifies every query into one of:

- `direct` — single correct answer, immutable (physics constants, math, conversions, fixed dates)
- `reference` — encyclopedic, benefits from multi-model debate (science, history, how-things-work)
- `news` — time-sensitive, triggers auto-fetch before quorum
- `logs` — never cached, intended for log/diagnostic analysis
- `network` — never cached, intended for network topology questions

If the classifier misroutes a query (e.g., calls a math question `reference`), submit it a second time — the memory cache will return the correct-intent answer on repeat queries once one is stored.

---

## Memory Layer

### Similarity threshold

Default threshold is **0.82**. Queries scoring below this miss the cache and run the full pipeline.

- Raising the threshold (e.g., 0.90) makes the cache more exact-match — fewer false hits, more fresh inference runs.
- Lowering it (e.g., 0.75) makes it more permissive — useful if you want paraphrase variants to always cache-hit, but risks serving wrong answers for loosely related questions.

Threshold is set in `tectum_framework/api_server/main.py` → `SIMILARITY_THRESHOLD`.

### TTL per intent

| Intent | TTL |
|--------|-----|
| `direct` | 365 days |
| `reference` | 30 days |
| `news` | 1 day |
| `logs` / `network` | Not cached |

### Forcing a cache miss

There is no UI override yet. To force a fresh quorum on a cached query, either:
1. Delete the memory entry directly: `DELETE FROM tectum_memory WHERE question ILIKE '%your question%';`
2. Lower the threshold temporarily and re-raise it after.

---

## Models

### Current stack

| Model | Role | Approx VRAM |
|-------|------|-------------|
| `llama3.2:3b` | Intent classifier (fetcher) + direct-path answerer | ~2 GB |
| `qwen2.5:7b` | Quorum contributor | ~5 GB |
| `mistral-nemo:12b` | Quorum contributor | ~8 GB |
| `deepseek-r1:14b` | Synthesis + R1 reasoning | ~10 GB |
| `nomic-embed-text` | Memory embeddings | small |

### Swapping models

- **Synthesis model**: selectable per-query in the UI (dropdown). No config change needed.
- **Contributors**: toggled per-query via chips in the UI. No config change needed.
- **Classifier / embedder**: hard-coded in `fetcher/optimizer.py` and `api_server/memory.py`. Change model name and rebuild.

### VRAM tuning

`OLLAMA_MAX_LOADED_MODELS=4` and `OLLAMA_NUM_PARALLEL=3` are set in `docker-compose.yml`. If you swap in a larger synthesis model and hit OOM:
- Lower `OLLAMA_MAX_LOADED_MODELS` to 3 (models will unload/reload between tiers — slower but works)
- Or reduce to 2 contributor models per quorum

---

## Fetcher / Research Mode

### Depth levels

| Depth | Approx crawl time | Sources |
|-------|------------------|---------|
| Quick | ~30s | RSS + Wikipedia only |
| Standard | ~2 min | RSS + Wikipedia + top web results |
| Deep | ~10 min | All sources, expanded crawl |

### When fetch triggers automatically

`news` intent always fetches regardless of the Research Mode toggle. Everything else only fetches when Research Mode is explicitly on.

### Adding RSS sources

RSS feed list is in `tectum_framework/fetcher/crawler.py`. Add URLs to the feeds list — no restart needed (fetcher reads at crawl time).

---

## API Quick Reference

```bash
# Health
curl http://localhost:8000/health
curl http://localhost:8001/health

# Submit a query (async — returns job_id)
curl -X POST http://localhost:8000/quorum \
  -H "Content-Type: application/json" \
  -d '{"question": "your question here"}'

# Submit synchronously (waits for result)
curl -X POST http://localhost:8000/quorum/sync \
  -H "Content-Type: application/json" \
  -d '{"question": "your question here"}'

# Get result by job ID
curl http://localhost:8000/quorum/{job_id}

# History (last 20)
curl http://localhost:8000/quorum/history?limit=20

# Search memory
curl "http://localhost:8000/memory/search?q=speed+of+light&threshold=0.8"

# Delete a memory entry
# ⚠️  NOTE: This endpoint does NOT exist in main.py (Task #12 — not yet implemented).
# Workaround: delete directly in the DB:
#   docker exec -it cloven_tectum_db psql -U $DATABASE_USER -d $DATABASE_NAME
#   DELETE FROM tectum_memory WHERE question ILIKE '%your question%';
curl -X DELETE http://localhost:8000/memory/{memory_id}
```

Full interactive docs at `http://localhost:8000/docs`.

---

## Ops Notes

### Restarting the stack

```bash
docker compose down && docker compose up -d
```

Models stay loaded in Ollama's volume — no re-pull needed after restart.

### Checking model load state

```bash
curl http://localhost:11434/api/ps
```

Shows which models are currently resident in VRAM.

### Database

PostgreSQL 17 + pgvector. Data persists in the `cloven_db_data` Docker volume.

```bash
# Connect
docker exec -it cloven_tectum_db psql -U ${DATABASE_USER} -d ${DATABASE_NAME}

# Row counts
SELECT COUNT(*) FROM tectum_memory;
SELECT COUNT(*) FROM quorum_jobs;
```

### Log tailing

```bash
docker logs -f cloven_tectum_api
docker logs -f cloven_tectum_fetcher
docker logs -f cloven_ollama
```

---

## Standalone / MCP flavor — NAS deployment

> The bundled stack above runs Ollama + GPU locally. The **standalone** flavor
> (`docker-compose.standalone.yml` / `docker-compose.synology.yml`) drops Ollama,
> attaches to an existing one via `OLLAMA_HOST`, adds an MCP server, and runs on
> non-standard ports (8800/8801/8802/55432).

**Live deployment:** Syn1 (DS2418+), `/volume1/docker/tectum`, attached to Ollama
on `192.168.1.232`. MCP endpoint for any agent: `http://192.168.1.173:8802/mcp`.

```bash
# Connect (key-based, passwordless; 10G link, or 192.168.1.173 on 1G)
ssh -i ~/.ssh/tectum_deploy cloven@10.79.45.122

# Manage the stack (docker needs sudo; cloven is in administrators w/ NOPASSWD)
cd /volume1/docker/tectum
sudo /usr/local/bin/docker compose -f docker-compose.synology.yml ps
sudo /usr/local/bin/docker compose -f docker-compose.synology.yml logs -f cloven_tectum_api
sudo /usr/local/bin/docker compose -f docker-compose.synology.yml restart cloven_tectum_api
sudo /usr/local/bin/docker compose -f docker-compose.synology.yml down        # stop
sudo /usr/local/bin/docker compose -f docker-compose.synology.yml up -d        # start
sudo /usr/local/bin/docker compose -f docker-compose.synology.yml pull && \
sudo /usr/local/bin/docker compose -f docker-compose.synology.yml up -d        # update from GHCR
```

**DSM quirks (bit us, documented so they don't again):**
- DSM `sshd` has **no SFTP subsystem** → `scp` fails. Transfer files with `cat local | ssh host "cat > remote"`.
- The DB self-initializes — the API applies the idempotent `schema.sql` on startup, so **no schema bind mount** is needed for pull-only deploys.
- `host.docker.internal` is wired for Ollama-on-same-host; for a remote Ollama (like `.232`) it's just unused.

## CI — publishing images (GitHub Actions)

`.github/workflows/publish-images.yml` builds the 3 service images and pushes them
to GHCR (`ghcr.io/cycotek/tectum-{api,fetcher,mcp}`) on push to `main` /
`standalone-mcp` and on `v*` tags. Publishing uses the Action's own `GITHUB_TOKEN`.

```bash
gh run list --workflow=publish-images.yml      # see runs
gh run watch <run-id> --exit-status            # follow live
gh run view <run-id> --log                     # read logs
gh workflow run publish-images.yml             # trigger manually (workflow_dispatch)
gh api user/packages/container/tectum-api/versions --jq '.[].metadata.container.tags'
```

- **Token scopes** to *push* a workflow file: classic PAT needs `repo` **+ `workflow`**
  (`repo` alone can trigger/view but not push `.github/workflows/*`). Check with `gh auth status`.
- **Tags**: every build tags `<branch-name>` + `sha-<short>`. `:latest` is created
  **only on `main`** (the convention — `latest` tracks the stable branch).
- **Pulling on the NAS**: packages are public → anonymous `docker pull` works. If
  on a feature branch, set `IMAGE_TAG=<branch>` in the NAS `.env`; once on `main`,
  the default `${IMAGE_TAG:-latest}` just works.

## SIEM Operations

### Architecture

```
UniFi MCP (localhost:8100 on ai server)
    ↓  systemd poller — polls every 30s, forwards new events
TectumFW API (192.168.1.173:8800) → siem_events table (PostgreSQL + pgvector)
```

The poller runs as a `systemd --user` service on the **ai server (192.168.1.232)**,
not on Syn1. Reason: Syn1 → ai server port 8100 times out due to wireless client
isolation. The poller uses `localhost` for the MCP, avoiding the asymmetry.

### SIEM endpoints

```bash
# Ingest an event
curl -X POST http://192.168.1.173:8800/siem \
  -H "Content-Type: application/json" \
  -d '{"event_type":"firewall","subsystem":"lan","severity":"warning","src_ip":"10.0.0.5","msg":"blocked"}'

# List recent events
curl "http://192.168.1.173:8800/siem/events?limit=20"

# Stats
curl http://192.168.1.173:8800/siem/stats
# → {"by_severity":{"info":N,"warning":N},"events_last_hour":N,"high_critical_24h":N}
```

### Poller service (ai server)

```bash
# Status / logs / control
systemctl --user status siem-poller
journalctl --user -u siem-poller -n 50
systemctl --user restart siem-poller

# Config
cat ~/siem-poller/.env
# UNIFI_MCP_URL=http://localhost:8100
# UNIFI_MCP_KEY=<key>
# TECTUM_SIEM_URL=http://192.168.1.173:8800/siem
# POLL_INTERVAL=30
```

Silent when 0 new events (by design). Logs appear only when forwarding events.
Linger is enabled — survives logouts and reboots.

### siem_events table schema

```sql
id           UUID PRIMARY KEY DEFAULT gen_random_uuid()
event_type   TEXT NOT NULL
subsystem    TEXT
severity     TEXT DEFAULT 'info'
src_ip       INET
dst_ip       INET
src_port     INTEGER
dst_port     INTEGER
proto        TEXT
msg          TEXT
site_id      TEXT
raw_payload  JSONB
processed    BOOLEAN DEFAULT FALSE
received_at  TIMESTAMPTZ DEFAULT NOW()
quorum_job_id UUID REFERENCES quorum_jobs(id)
```

Indexes: `received_at DESC`, `(severity, received_at DESC)`, `src_ip`.

### Synology Docker quirks (documented — bit us once)

`sudo docker` fails on Synology DSM: the `sudo` secure PATH doesn't include
ContainerManager's binary location. **Workaround**: use DSM Task Scheduler
(Control Panel → Task Scheduler → Create → Scheduled Task → User-defined script,
Owner: root) and locate docker dynamically:

```bash
#!/bin/bash
DOCKER=$(find /var/packages/ContainerManager/target/usr/bin /usr/local/bin \
  -name docker -type f 2>/dev/null | head -1)
cd /volume1/docker/tectum
$DOCKER pull ghcr.io/cycotek/tectum-api:latest
$DOCKER compose -f docker-compose.synology.yml up -d cloven_tectum_api
```

**Delete the task after it runs** — scheduled tasks run at midnight by default.

---

## Docs philosophy — where help lives

Two kinds of help, opposite hosting:
- **Usage help** (badges, modes, model toggles) → **in-app Help panel**. You only
  need it when the app is up, so it can live in the GUI.
- **Recovery / runbook** (this file: restart, logs, redeploy, `gh`/`ssh`/`docker`)
  → **the repo**, because it must be reachable when the service is *down*. An
  in-app help screen is useless during an outage; GitHub still renders HANDBOOK.md.

So: the GUI Help should explain usage and then **link out to HANDBOOK.md** (and the
`/health` endpoints) for the "it's broken, now what" path — never bury recovery
steps only inside the running app.

## Known Quirks

- **R1 reasoning blocks**: DeepSeek-R1 doesn't always emit `<think>` tags. When `synthesis_thinking` is empty the UI shows no reasoning block — this is expected, not a bug.
- **Badge metadata on history reload**: Loading a past job via the history sidebar re-fetches from `/quorum/{id}`, which doesn't include `intent`/`from_memory` fields. Badges may not appear on reloaded jobs.
- **Memory match on first submit**: If you ask "speed of light" and it misses cache the first time, submitting it a second time will hit. The first run stores the embedding; the second run finds it.

---

*Add to this file as behaviors are confirmed, edge cases discovered, or the routing logic is tuned.*

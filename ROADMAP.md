# TectumFW — Roadmap & Punch List

Living capture of where the project is and where it's going. Organized so any of
these can be picked up cold in a fresh session.

---

## High-level vision — what this modeling accomplishes

TectumFW is a **bias-and-consensus reasoning layer** over local models. The core
bet: a single LLM's answer is one sample from one training distribution with one
set of biases. Fan the same question across several *different* architectures,
then have a separate model synthesize across them, and you get an answer that is
**auditable** (you can see where models agreed, disagreed, and diverged) and
**less captured by any single model's blind spots**.

Layered on top:
- **Semantic memory (pgvector)** turns the system into an *institutional memory* —
  it remembers what it concluded and why, matched by meaning, so repeated or
  rephrased questions are instant and consistent over time.
- **The fetcher** grounds answers in live sources, breaking the training-cutoff
  ceiling for time-sensitive questions.
- **MCP exposure** makes all of this a *tool* any agent on the network can call —
  Tectum becomes shared reasoning infrastructure, not a one-off app.

Where this goes: a private, air-gapped "research desk" that several agents and
machines share — consistent, sourced, bias-aware answers with a durable memory of
everything it has ever concluded. The consensus + memory + provenance combination
is the differentiator; most local-LLM setups have none of it.

---

## Deployment / repos / git

- **Branch `standalone-mcp`** holds the standalone (Ollama-decoupled) + MCP work.
  Two commits so far (standalone flavor; Synology/GHCR + self-init schema).
- **Live on Syn1 (DS2418+)** at `/volume1/docker/tectum` via
  `docker-compose.synology.yml`, attached to Ollama on `192.168.1.232`.
  Ports: API 8800 · Fetcher 8801 · MCP 8802 · DB 55432.
  MCP endpoint: `http://192.168.1.173:8802/mcp`.
- [ ] **Split into its own repo `TectumFW-Standalone`** once the branch settles
  (the bundled `Cloven_Distro_TectumFW` stays as the GPU all-in-one demo).
- [x] **GHCR auto-publish** — `.github/workflows/publish-images.yml` builds and
  pushes `ghcr.io/cycotek/tectum-{api,fetcher,mcp,siem-poller}` on push to
  `main`. Packages are **public** — anonymous `docker pull` works on the NAS.
  `sudo docker` fails on Synology (PATH issue); use DSM Task Scheduler as root
  with a `find`-based docker binary path. See HANDBOOK.md → Synology quirks.
- [x] Refresh the GitHub repo **description** (was outdated).

## SIEM Intake — completed 2026-06-11

- [x] **`POST /siem`** endpoint on `cloven_tectum_api` — accepts normalized network
  events, stores to `siem_events` table (UUID PK, event_type, subsystem, severity,
  src_ip/dst_ip INET, raw_payload JSONB, received_at).
- [x] **`GET /siem/events`** — paginated event list.
- [x] **`GET /siem/stats`** — by_severity counts, events_last_hour, high_critical_24h.
- [x] **SIEM poller** — stdlib-only Python script running as a `systemd --user`
  service on the ai server (192.168.1.232). Polls UniFi MCP at `localhost:8100`
  every 30s, forwards new events to `http://192.168.1.173:8800/siem`. Tracks
  state in `/tmp/siem_poller_state.json`. Linger-enabled for reboot persistence.
- [x] **Network asymmetry documented**: Syn1 → ai server times out (wireless client
  isolation); poller runs on ai server and uses localhost for the MCP.
- [x] **IPS false positive resolved**: 192.168.1.232 → GitHub (140.82.114.4) was
  generating CyberSecure alerts. IPS exception added.

## GUI

- [ ] **In-app Help / onboarding** — explain the badges, the 3 tiers, Research
  Mode depths, contributor vs synthesis models, and the memory hit meta bar.
  Right now the README carries all of this; the UI assumes prior knowledge.
- [ ] **Persistent statistics / observability page.** We already capture the raw
  data (per-model `duration_ms`, `tokens_in`, `tokens_out` on every response and
  synthesis) — surface it instead of throwing it away:
  - Raw numbers **per machine / per model** (throughput, tokens, latency, error
    rate). Multi-Ollama-aware once more than one backend is in play.
  - Token accounting over time (cost/usage trends, even if "cost" is just compute).
  - **pgvector memory browser** — list/search/sort stored memories by recency,
    hit_count, intent, similarity, TTL; see what's cached, what's hot, prune
    stale entries. (Cloven may start this in a separate session.)
  - These are mostly read-side: new `/stats` endpoints aggregating existing
    `quorum_responses` / `quorum_narratives` / `tectum_memory` rows, plus a page.
- [ ] **Component health panel** — the UI shows a single online dot today; expand
  it to a per-component list (API, fetcher, DB/pgvector, MCP, and each Ollama
  backend) with green/red, last-checked, and latency, so you can see *what* went
  down, not just *that* something did. Back it with a `/status` endpoint that
  probes each dependency (DB query, fetcher `/health`, Ollama `/api/tags` +
  `/api/ps` for loaded models). Per-machine once multiple Ollama backends exist —
  dovetails with the per-machine stats above. Each red item links to the relevant
  HANDBOOK.md runbook section ("how to fix it") — usage stays in-app, recovery
  points to the repo.
- [ ] **Self-healing / auto-fix (future, gated).** Per-component "diagnose" action
  that bundles its status + recent logs into a prompt, sends it to an AI (Claude
  API or a local model), and returns a diagnosis + proposed fix; optional one-click
  apply → commit. Must be gated behind explicit confirmation and never auto-apply
  destructive actions (restart = ok; schema/data changes = review first). The
  agentic endgame: status → diagnosis → fix → commit.

## Fetcher — faster, distributed backend

Today the crawler is single-threaded and capped at a few sources per query
(noted in README as a known limit). Target: a **sharded worker pool**, Hadoop-style.

- [ ] **Worker pool / job-shard model** — split a fetch job into independent
  units of work dispatched to workers, results merged in the context assembler.
- [ ] **Source-specialized workers** — dedicated fetchers per source class so each
  can be tuned/rate-limited/authed independently: news wires (AP, Reuters), RSS,
  Wikipedia, general web. Add more by dropping in a worker.
- [ ] **"Site of sites" seed discovery** — before crawling, find high-yield hub
  pages (aggregators, link directories, topic indexes) and crawl *those* deeper,
  rather than a shallow fan-out from raw query terms.
- [ ] **Faster backend** generally — async/queue (e.g. a task queue + workers),
  connection pooling, parallel source classes; the fetcher already runs as its
  own service on its own port, so it can scale out independently of the API.
- This dovetails with the README's stated "broker / shard architecture (future)":
  a persistent fetch service that pre-fetches topics on a schedule and caches
  assembled context in pgvector for any consumer.

## Docs

- [ ] Keep README / README.standalone / GitHub description in sync as the above
  lands. The standalone + MCP + Synology story should be reflected in the main
  README's architecture section, not only in README.standalone (main README now
  just has a pointer).
- [ ] **Reality-check todo:** HANDBOOK.md documents `DELETE /memory/{memory_id}`
  but **no such endpoint exists** in `api_server/main.py`. Either implement the
  DELETE route (handy for the pgvector memory browser anyway) or remove the claim
  from HANDBOOK. (The SQL `DELETE FROM tectum_memory …` workaround is real.)
- [x] README reality-check pass: fixed theme names (Dark/Light/Terminal, was
  "Dim"), reframed the screenshots checklist as done, added a standalone/MCP
  flavor pointer. Verified the claimed UI (badges, R1 reasoning block, memory
  meta bar, online dot) all actually exist in the code.

---

*Some items (stats page, pgvector memory metrics) may be started by Cloven in a
separate session — this file is the shared brief so that work and this work line up.*

# TectumFW Standalone — MCP Service Flavor

This is the **decoupled, plug-into-your-own-Ollama** flavor of TectumFW. It runs
as a single persistent service on your network (Synology Container Manager, a
Docker host, or right next to your bare-metal Ollama box), attaches to an Ollama
instance you **already have**, and exposes the whole reasoning stack to your MCP
fleet as three tools.

Where the bundled [`docker-compose.yml`](docker-compose.yml) ships its own Ollama
+ GPU, this flavor ([`docker-compose.standalone.yml`](docker-compose.standalone.yml))
ships **no Ollama** — it scrapes whatever models live on the Ollama you point it
at, and adds an MCP server on top.

---

## What's in the stack

| Service | Port (default) | Role |
|---|---|---|
| `cloven_tectum_mcp` | `8802` | **MCP server** (streamable-HTTP at `/mcp`) — the front door for agents |
| `cloven_tectum_api` | `8800` | Web UI + REST API, 3-tier router, semantic memory |
| `cloven_tectum_fetcher` | `8801` | Research fetcher (news / reference / logs / network crawler) |
| `cloven_tectum_db` | `55432` | PostgreSQL 17 + pgvector (ships bundled; swappable) |
| _Ollama_ | _external_ | **Not bundled** — you provide it via `OLLAMA_HOST` |

Ports use a non-standard `88xx` / `555xx` band so the stack drops onto an
existing host without colliding with anything.

---

## Quick start

```bash
cp .env.standalone.example .env
# Edit .env — set OLLAMA_HOST to your Ollama machine (see below)
docker compose -f docker-compose.standalone.yml up -d --build
```

- UI / API → `http://<host>:8800`
- MCP endpoint → `http://<host>:8802/mcp`

The models in `.env` just set defaults; the live model list is scraped from your
Ollama's `/api/tags`, so it always reflects what's actually installed there.

---

## Pointing at your Ollama

This stack does not run Ollama. Set `OLLAMA_HOST` in `.env`:

| Where your Ollama runs | `OLLAMA_HOST` |
|---|---|
| Same Docker host as this stack | `http://host.docker.internal:11434` |
| Another machine (bare metal) | `http://192.168.1.50:11434` |

> **The Ollama box must listen on the network.** Start it with
> `OLLAMA_HOST=0.0.0.0` (and open port `11434` on its firewall) so it accepts LAN
> connections instead of localhost-only. Verify from this host with:
> `curl http://<ollama-ip>:11434/api/tags`

Required models must already be pulled on that instance:

```bash
ollama pull deepseek-r1:14b mistral-nemo:12b qwen2.5:7b llama3.2:3b nomic-embed-text
```

---

## The MCP tools

The MCP server exposes three tools over streamable-HTTP:

| Tool | What it does |
|---|---|
| `tectum_ask(question, models?, synthesis_model?, research?, depth?, use_memory?)` | Full 3-tier pipeline: memory check → direct/quorum → R1 synthesis. Returns the consensus narrative with a provenance line. |
| `tectum_fetch(query, mode?)` | Live research crawl (RSS / web / Wikipedia, intent-routed). Returns assembled, source-attributed context — independent of any model. |
| `tectum_recall(query, threshold?)` | Instant pgvector lookup over everything already answered. No inference. |

### Wiring it into an MCP client

For any client that supports a streamable-HTTP MCP server, point it at
`http://<host>:8802/mcp`. Example (`.mcp.json` / client config):

```json
{
  "mcpServers": {
    "tectum": {
      "type": "http",
      "url": "http://<host>:8802/mcp"
    }
  }
}
```

---

## Using an external Postgres instead of the bundled one

The stack ships its own pgvector DB by default. To use a Postgres you already
run, set its address in `.env`:

```
DATABASE_HOST=your-db-host
DATABASE_PORT=5432
```

then start only the app services (skip the bundled DB):

```bash
docker compose -f docker-compose.standalone.yml up -d --build \
  cloven_tectum_api cloven_tectum_fetcher cloven_tectum_mcp
```

Your external Postgres must have the `vector` extension available; apply
[`schema.sql`](tectum_framework/api_server/schema.sql) to it once before first run.

---

## How this differs from the bundled flavor

| | Bundled (`docker-compose.yml`) | Standalone (`docker-compose.standalone.yml`) |
|---|---|---|
| Ollama | Bundled + NVIDIA GPU passthrough | External — you provide it |
| Ports | Standard (8000 / 8001 / 5432) | Non-standard (8800 / 8801 / 55432) |
| MCP server | — | `cloven_tectum_mcp` on `8802` |
| Target | All-in-one demo on a GPU box | Persistent network service / Synology / MCP fleet |

See [README.md](README.md) for the full pipeline explanation, which both flavors share.

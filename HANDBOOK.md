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

## Known Quirks

- **R1 reasoning blocks**: DeepSeek-R1 doesn't always emit `<think>` tags. When `synthesis_thinking` is empty the UI shows no reasoning block — this is expected, not a bug.
- **Badge metadata on history reload**: Loading a past job via the history sidebar re-fetches from `/quorum/{id}`, which doesn't include `intent`/`from_memory` fields. Badges may not appear on reloaded jobs.
- **Memory match on first submit**: If you ask "speed of light" and it misses cache the first time, submitting it a second time will hit. The first run stores the embedding; the second run finds it.

---

*Add to this file as behaviors are confirmed, edge cases discovered, or the routing logic is tuned.*

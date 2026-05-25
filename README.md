# Cloven Distro TectumFW

**A modular, distributed AI quorum framework** — fan a question out to multiple LLMs, collect independent answers, synthesize a bias-filtered narrative.

---

## Architecture

```
POST /quorum  →  LangGraph graph  →  pgvector DB (history)
                      |
              [initialize] — pick models
                      |
         (parallel fan-out via Send)
           /          |          \
  [query_model]  [query_model]  [query_model]
     model A        model B        model C
           \          |          /
         (responses accumulated)
                      |
              [synthesize] — top-level LLM builds narrative
                      |
              stored to pgvector DB
```

**Services:** `cloven_tectum_api` (FastAPI + LangGraph) + `cloven_tectum_db` (pgvector:pg17).  
Connects to Ollama already running on the host — no duplicate model container.

---

## Quick Start

```bash
git clone https://github.com/cycotek/Cloven_Distro_TectumFW
cd Cloven_Distro_TectumFW
./serversetup.sh
```

Navigate to `http://localhost:8000/docs` for the interactive API.

---

## API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/models` | List available Ollama models |
| `POST` | `/quorum` | Submit question async → returns `job_id` |
| `GET` | `/quorum/{id}` | Get job status, all responses, narrative |
| `POST` | `/quorum/sync` | Submit and wait for full result |
| `GET` | `/health` | Health check |

### Example

```bash
# Sync quorum — waits for all models + synthesis
curl -X POST http://localhost:8000/quorum/sync \
  -H "Content-Type: application/json" \
  -d '{"question": "What are the risks of AI-generated code?"}'

# Async — submit then poll
JOB=$(curl -s -X POST http://localhost:8000/quorum \
  -H "Content-Type: application/json" \
  -d '{"question": "Explain the trolley problem."}' | python3 -c "import sys,json; print(json.load(sys.stdin)['job_id'])")
curl http://localhost:8000/quorum/$JOB
```

---

## Configuration (`.env`)

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_HOST` | `http://host.docker.internal:11434` | Ollama endpoint |
| `QUORUM_MODELS` | `mistral-nemo:12b,qwen2.5:7b,llama3.2:3b` | Models to query |
| `SYNTHESIS_MODEL` | `mistral-nemo:12b` | Model for final synthesis |
| `API_PORT` | `8000` | Port the API listens on |
| `DATABASE_*` | see `.env.example` | Postgres credentials |

---

## Teardown

```bash
./teardown.sh
```

---

## Author

Created by **Cloven** — _"No gods. No devils. Only uptime."_

<p align="center">
  <img src="assets/cloven_brain.png" alt="Tectum Logo" width="200"/>
</p>

---

## License

MIT License. Use freely, modify respectfully, and contribute if you dare.

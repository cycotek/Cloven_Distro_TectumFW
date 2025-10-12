<p align="center">
  <img src="assets/cloven_brain.png" alt="Tectum Logo" width="200"/>
</p>

# Cloven Distro: TectumFW 🧠🕸️

**Cloven_TectumFW** is a modular agent orchestration stack designed to route queries through multiple local or remote LLM endpoints (e.g., Gemma, GPT-4, Ollama) with quorum-based result merging, autonomous scraping agents, and fully containerized PostgreSQL-backed storage.

The name *Tectum* (Latin for "roof") represents the role this system plays: a narrative roof layered above scrapers, agents, and inference engines.

---

## ⚙️ Overview

```mermaid
graph TD
    A[Top LLM - Narrative Engine] --> B[Insert outbound query]
    B --> C{Postgres: outbound_requests}

    C --> D1[Scraper Agent 1]
    D1 --> E1[LLM Call: Gemma via Ollama]
    E1 --> F1[Insert response to inbound_responses]

    C --> D2[Scraper Agent 2]
    D2 --> E2[Web scrape: news.ycombinator.com]
    E2 --> F2[Insert response to inbound_responses]

    C --> D3[Scraper Agent N]
    D3 --> E3[LLM Call: OpenAI GPT-4]
    E3 --> F3[Insert response to inbound_responses]

    F1 --> G[Top LLM polls all responses]
    F2 --> G
    F3 --> G
    G --> H[Builds narrative answer]
```

---

## 🧩 Architecture

### Components:
- **Top LLM**: Decision layer; sends outbound queries to DB, collects results, builds narratives.
- **PostgreSQL**: Central broker for all requests and responses.
- **Scraper Agents**: Poll outbound requests, route to data sources or LLM endpoints.
- **LLMs**: Configurable inference endpoints (local or API).
- **Inserters**: Responsible for writing structured results back to the DB.

### Features:
- 🔄 **Quorum Reasoning** – Results are collected from 3+ LLMs to form a consensus.
- 📬 **Postgres-MQ Design** – Pub-sub via DB tables; dead-simple and durable.
- 🕸️ **Web + Model Fusion** – Mixes LLM queries with live scrapes for hybrid responses.
- 🔧 **Docker-Based** – Fully containerized, zero-install local deployment.
- 🎛️ **GPU Optional** – Ollama supports CUDA if configured properly.

---

## 📦 Stack

| Service           | Port  | Purpose                              |
|------------------|-------|--------------------------------------|
| WebUI             | 8080  | Frontend + management portal         |
| API               | 8000  | Main orchestration layer (Python)    |
| Ollama            | 11434 | Local LLM runtime for models         |
| Scrapers          | 8081+ | External fetchers + LLM callers      |
| Postgres          | 5432  | Request/response and metadata store  |

---

## 🚧 Status

- ✅ Local login, LLM execution, and WebUI operational
- 🔄 Scraper agent orchestration and quorum logic under active development
- 🧪 GPU acceleration (CUDA + nvidia-docker) available but optional
- 📈 Planned: Voice modules, narrative drift detection, Home Assistant bridge

---

## 👁️ Vision

Cloven_TectumFW aims to become a **general-purpose narrative synthesis stack**, suitable for use cases such as:

- Private assistant LLMs that **never touch the web**
- Autonomous agents that **refactor, fact-check, and quorum-check each other**
- Scrapers that **generate structured, sentiment-scored, or multi-perspective output**
- Federated model runners (e.g., Gemma locally, GPT-4 remotely) in consensus

---

> _“No gods. No devils. Only uptime.”_ – Cloven

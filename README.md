# Cloven Distro – Tectum Framework

> **Directive**: “No gods, no devils, only uptime.”

The **Cloven Tectum Framework** is a modular AI + infrastructure stack designed as a **brain-inspired distribution**.  
Like the human tectum orients the eyes toward relevant stimuli, this framework orients AI systems toward **signal over noise**.

---

## 📂 Project Structure

tectum_framework/
├─ api_server/ # FastAPI orchestration layer
├─ db/ # PostgreSQL + pgvector schema & migrations
├─ agents/ # Autonomous scrapers + inserters
│ ├─ scraper/
│ └─ inserter/
├─ webui/ # OpenWebUI with optional voice integration
├─ ollama/ # Ollama LLM runtime
├─ shared/ # Common utils (logging, db helpers)
config/ # Service-specific configs
logs/ # Mounted logs for observability
scripts/ # Init, migrations, helpers
tests/ # Unit + integration tests
docker-compose.yml # Multi-service orchestration
.env # Centralized config


---

## 🚀 Features

- Modular AI runtime with **Ollama + OpenWebUI**
- **FastAPI orchestration** with PostgreSQL backend
- **Agents** for scraping & automated ingestion
- Voice input/output support (STT + TTS planned)
- Secure, extensible API (JWT / API key ready)
- Observability with Prometheus + Grafana (roadmap)

---

## 🔧 Getting Started

```bash
git clone https://github.com/cycotek/Cloven_Distro_TectumFW.git
cd Cloven_Distro_TectumFW
cp .env.example .env   # configure your secrets
docker-compose up --build

🧩 Adding New AIs

The framework is designed for plug-and-play AI runtimes:

Drop new LLM models under ollama/

Add endpoints in api_server/

Register agents to push/pull from the DB

Each AI service is isolated but observable, making experiments safe and reversible.

📜 Philosophy

Uptime is truth: Stability over mythology

Redundancy is resilience: Narrative + technical

Glitches reveal depth: π as sentinel


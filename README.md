# Cloven_Tectum Framework

The Tectum in the human brain orients the body and eyes toward **relevant stimuli**.  
This framework applies the same principle: orient AI systems toward **meaningful signal**, shielding them from distortion and noise.  

---

## ⚙️ Build Info
- Version: 0.1.0
- Commit:  a39206d
- Date:    2025-09-28

---

# 🧠 Cloven_Tectum Framework

> *“The tectum in the human brain orients the body and eyes toward relevant stimuli.  
This framework applies the same principle: orient AI systems toward **meaningful signal**, shielding them from distortion and noise.”*

---

## 📖 Overview

The **Cloven_Tectum Framework (CTF)** is a modular, containerized AI framework designed for experimentation, integration, and resilience.  
It combines a robust backend (PostgreSQL + FastAPI), modern AI runtimes (Ollama, Open WebUI), and modular agents (scrapers, inserters) to create a **fault-tolerant narrative system** that detects distortion, maintains uptime, and generates actionable insights.

This project was built with a **DevOps-first mindset**:
- 🛠️ **Self-deploying bootstrap script (`serversetup.sh`)**
- 🐳 **Dockerized services with Compose orchestration**
- 🔄 **Iterative updates and auto-generated README metadata**
- 🧩 **Extensible design** for plugging in new AI models and agents

---

## 🗂️ Project Structure

Cloven_Distro_TectumFW/
├─ ABOUT.md # About page with project image + commit/version info
├─ assets/ # Static assets (logos, images, etc.)
├─ .env / .env.example # Environment configuration (DB, ports, etc.)
├─ tectum_framework/ # Core framework
│ ├─ api_server/ # FastAPI app (core API services)
│ ├─ ollama/ # Ollama container for LLM serving
│ ├─ agents/ # Modular agents
│ │ ├─ scraper/ # Scraping & ingestion logic
│ │ └─ inserter/ # Inserts scraped data into DB
├─ docker-compose.yml # Orchestrates all containers
├─ serversetup.sh # Bootstrapper (generates files, sets perms, launches stack)
├─ update_readme.sh # Auto-updates README from template + Git metadata
└─ README.template.md # Template used by update_readme.sh


---

## 🚀 Quickstart

### 1. Clone the repo
```bash
git clone https://github.com/cycotek/Cloven_Distro_TectumFW.git
cd Cloven_Distro_TectumFW
2. Bootstrap the stack
bash
Copy code
./serversetup.sh
Creates required directories

Generates .env (if missing)

Writes Dockerfiles + docker-compose.yml

Launches all services (api, ollama, db, webui, agents)

3. Access services
API docs → http://localhost:8000/docs

WebUI (OpenWebUI) → http://localhost:8080

⚙️ Services
Service	Description	Port
API Server	FastAPI for health checks, agents, integrations	8000
Database	PostgreSQL (with pgvector for embeddings)	5432
Ollama Runtime	Local LLM hosting	11434
OpenWebUI	Frontend for interacting with models	8080
Scraper Agent	Stub for scraping & ingesting external data	N/A
Inserter Agent	Stub for inserting into DB	N/A

🧩 Philosophy & Easter Eggs
This repo is as much philosophy as it is code:

“No gods, no devils, only uptime.” → The system prioritizes resilience and truth.

Narrative redundancy → Like fault tolerance in distributed systems, multiple narrative “replicas” defend against distortion.

Easter Eggs → Source code contains subtle references to Rick Astley’s “Never Gonna Give You Up.” A nod to persistence, uptime, and resilience.

Transparency → Logs, metrics, and self-healing workflows.

🔮 Roadmap
✅ Bootstrapper script (serversetup.sh)

✅ Basic FastAPI + Ollama + WebUI stack

✅ Agents for scraping/inserting

🔲 Narrative drift detection (DB-backed replicas)

🔲 Real-time metadata analysis (sentiment, credibility, demographics)

🔲 Home Assistant integration

🔲 GPU support variants (NVIDIA/AMD/CPU fallback)

🔲 Voice packages for OpenWebUI

📝 License
MIT License © 2025 Cycotek & Contributors
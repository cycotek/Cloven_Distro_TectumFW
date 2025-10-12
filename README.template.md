# Cloven_Tectum Framework

![Cloven Banner](assets/cloven_brain.png)

**Version**: `{{VERSION}}`  
**Commit**: `{{GIT_HASH}}`  
**Updated**: `{{DATE}}`

---

## 📖 Overview

The **Cloven_Tectum Framework (CTF)** is a framework for resilient stacks of services — repeatable, self‑deploying, and adaptable.  
It combines a robust backend (PostgreSQL + FastAPI), modern AI runtimes (Ollama, OpenWebUI), and modular agents (scrapers, inserters) to create a fault-tolerant narrative system.

This project is built with a DevOps‑first mindset:
- 🛠 Self‑deploying bootstrap (`serversetup.sh`)
- 🐳 Dockerized services with Compose orchestration
- 🔄 Iterative updates and auto-generated metadata
- 🧩 Extensible modular design

---

## 🗂️ Project Structure

```plaintext
Cloven_Distro_TectumFW/
├─ ABOUT.md                 # About page (vision + metadata)
├─ assets/                  # Static assets
├─ .env / .env.example      # Environment configuration (DB, ports, etc.)
├─ tectum_framework/        # Core framework
│  ├─ api_server/           # FastAPI app
│  ├─ ollama/               # Ollama container
│  ├─ agents/               # Modular agents
│  │  ├─ scraper/           # Scraper logic
│  │  └─ inserter/          # Inserter logic
├─ docker-compose.yml       # Orchestrates all containers
├─ serversetup.sh           # Bootstrapper
├─ update_readme.sh         # Generates README & ABOUT
└─ README.template.md       # Template with placeholders
```plaintext

---

## 🏗️ Usage & Quickstart

```bash
git clone <repo>
cd Cloven_Distro_TectumFW
./serversetup.sh
API docs: http://localhost:8000/docs

WebUI: http://localhost:8080

🔮 Roadmap
Narrative drift detection (replicas)

Sentiment, credibility, demographic lenses

GPU support & voice modules

Home Assistant & external plugin integration

🧩 Philosophy & Easter Eggs
“No gods, no devils, only uptime.”
Narrative redundancy as system architecture.
Subtle lyrics sprinkled in source.

© 2025 Cloven & Contributors
License: MIT

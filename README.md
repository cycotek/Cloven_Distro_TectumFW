# 🧠 Cloven_Tectum Framework

> *“The tectum in the human brain orients the body and eyes toward relevant stimuli.  
This framework applies the same principle: orient AI systems toward **meaningful signal**, shielding them from distortion and noise.”*

---

## ⚙️ Build Info
- Version: 0.1.0
- Commit:  b924394
- Date:    2025-10-11

---

## 📖 Overview

The **Cloven_Tectum Framework (CTF)** is a **framework for resilient stacks of services** — repeatable, self-deploying, and adaptable.  
It combines a **robust backend** (PostgreSQL + FastAPI), **modern AI runtimes** (Ollama, Open WebUI), and **modular agents** (scrapers, inserters) to create a **fault-tolerant narrative system**.  

This project was built with a **DevOps-first mindset**:
- 🛠️ **Self-deploying bootstrap script (`serversetup.sh`)**
- 🐳 **Dockerized services with Compose orchestration**
- 🔄 **Iterative updates and auto-generated README metadata**
- 🧩 **Extensible design** for plugging in new AI models and agents

---

## 🗂️ Project Structure

```plaintext
Cloven_Distro_TectumFW/
├─ ABOUT.md                 # About page (image, version, commit info)
├─ assets/                  # Static assets
├─ .env / .env.example      # Environment configuration (DB, ports, etc.)
├─ tectum_framework/        # Core framework
│  ├─ api_server/           # FastAPI app (core API services)
│  ├─ ollama/               # Ollama container for LLM serving
│  ├─ agents/               # Modular agents
│  │  ├─ scraper/           # Scraping & ingestion logic
│  │  └─ inserter/          # Inserts data into DB
├─ docker-compose.yml       # Orchestrates all containers
├─ serversetup.sh           # Bootstrapper (generates files, sets perms, launches stack)
├─ update_readme.sh         # Auto-updates README from template + Git metadata
└─ README.template.md       # Template used by update_readme.sh
```plaintext

---

## 🏗️ Stack Architecture

```mermaid
flowchart TB
    subgraph U[User Layer]
        A[WebUI] -->|Requests| API
    end

    subgraph F[Framework Layer]
        API[FastAPI Server] -->|Inserts| DB[(PostgreSQL + pgvector)]
        API --> Ollama[Ollama Runtime]
        API --> Agents[Scraper + Inserter]
    end

    subgraph S[Storage & State]
        DB[(PostgreSQL DB)]
    end

    subgraph V[Visualization]
        A[WebUI] -->|Models & Results| Ollama
    end
⚡ Parallel Task Execution (Multiple LLMs)
mermaid
Copy code
flowchart TB
    U[User / WebUI] -->|Task Request| G[Cloven_Tectum API]

    subgraph O[Ollama Runtime]
        L1[LLM Instance 1]
        L2[LLM Instance 2]
        L3[LLM Instance 3]
        L4[LLM Instance N]
    end

    G -->|Fan Out Tasks| L1
    G --> L2
    G --> L3
    G --> L4

    L1 -->|Partial Result| G
    L2 -->|Partial Result| G
    L3 -->|Partial Result| G
    L4 -->|Partial Result| G
    
    G -->|Aggregate & Respond| U
Explanation
A single user request → API fans out tasks to multiple Ollama-hosted models.
Each LLM runs in parallel, producing partial outputs.
Results are aggregated back at the API and returned as a unified response.
This pattern makes the system resilient, scalable, and fast.

🚀 Quickstart
1. Clone the repo
bash
Copy code
git clone https://github.com/cycotek/Cloven_Distro_TectumFW.git
cd Cloven_Distro_TectumFW
2. Bootstrap the stack
bash
Copy code
./serversetup.sh
This will:

Create required directories

Generate .env (if missing)

Write Dockerfiles + docker-compose.yml

Launch all services (API, Ollama, DB, WebUI, agents)

3. Access services
API docs → http://localhost:8000/docs

WebUI (OpenWebUI) → http://localhost:8080

🔮 Roadmap
✅ Bootstrapper script (serversetup.sh)
✅ Basic FastAPI + Ollama + WebUI stack
✅ Agents for scraping/inserting

🔲 Narrative drift detection (DB-backed replicas)
🔲 Real-time metadata analysis (sentiment, credibility, demographics)
🔲 Home Assistant integration
🔲 GPU support variants (NVIDIA/AMD/CPU fallback)
🔲 Voice packages for OpenWebUI

🧩 Philosophy & Easter Eggs
“No gods, no devils, only uptime.” → Resilience as philosophy.

Narrative redundancy → Multiple models defend against distortion.

Transparency → Logs, metrics, and self-healing workflows.

Easter Eggs → Source contains hidden lyrics & acknowledgements 😉.

📝 License
MIT License © 2025 Cycotek & Contributors
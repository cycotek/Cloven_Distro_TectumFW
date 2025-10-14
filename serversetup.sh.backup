#!/bin/bash

set -e

# === Settings ===
VERSION_FILE=".version"
ROOT_DIR="$(pwd)"
TFRAMEWORK_DIR="${ROOT_DIR}/tectum_framework"
AGENTS_DIR="${TFRAMEWORK_DIR}/agents"

# === Helpers ===
function bump_version() {
    if [[ -f $VERSION_FILE ]]; then
        OLD_VERSION=$(cat $VERSION_FILE)
    else
        OLD_VERSION="0.1.0"
    fi
    IFS='.' read -r MAJOR MINOR PATCH <<<"$OLD_VERSION"
    PATCH=$((PATCH + 1))
    NEW_VERSION="$MAJOR.$MINOR.$PATCH"
    echo "$NEW_VERSION" > $VERSION_FILE
    echo "[✓] Version bumped: $OLD_VERSION → $NEW_VERSION"
}

function create_dirs() {
    echo "[+] Creating directories..."
    mkdir -p \
        "${TFRAMEWORK_DIR}/api_server" \
        "${AGENTS_DIR}/scraper" \
        "${AGENTS_DIR}/inserter" \
        "${TFRAMEWORK_DIR}/ollama"
}

function write_stubs() {
    echo "[+] Writing Dockerfiles and app stubs..."

    cat > "${TFRAMEWORK_DIR}/api_server/main.py" <<EOF
from fastapi import FastAPI
app = FastAPI()

@app.get("/health")
def health():
    return {"status": "ok"}
EOF

    cat > "${TFRAMEWORK_DIR}/api_server/requirements.txt" <<EOF
fastapi
uvicorn
psycopg2-binary
EOF

    cat > "${AGENTS_DIR}/scraper/scraper.py" <<EOF
import requests
print("Scraper running...")
EOF

    cat > "${AGENTS_DIR}/scraper/requirements.txt" <<EOF
requests
EOF

    cat > "${AGENTS_DIR}/inserter/inserter.py" <<EOF
import psycopg2
print("Inserter running...")
EOF

    cat > "${AGENTS_DIR}/inserter/requirements.txt" <<EOF
psycopg2-binary
EOF

    cat > "${TFRAMEWORK_DIR}/ollama/Dockerfile" <<EOF
FROM ollama/ollama:latest
EOF

    # === Dockerfiles for agents/api ===
    echo 'FROM python:3.11
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt
CMD ["python3", "main.py"]' > "${TFRAMEWORK_DIR}/api_server/Dockerfile"

    echo 'FROM python:3.11
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt
CMD ["python3", "scraper.py"]' > "${AGENTS_DIR}/scraper/Dockerfile"

    echo 'FROM python:3.11
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt
CMD ["python3", "inserter.py"]' > "${AGENTS_DIR}/inserter/Dockerfile"
}

function write_docker_compose() {
    echo "[+] Writing docker-compose.yml..."

    cat > docker-compose.yml <<EOF
services:
  cloven_tectum_api:
    build:
      context: ./tectum_framework/api_server
    container_name: cloven_tectum_api
    ports:
      - "8000:8000"
    restart: unless-stopped
    environment:
      API_PORT: "8000"
      DATABASE_NAME: cloven_tectum
      DATABASE_PASS: tectum123
      DATABASE_PORT: "5432"
      DATABASE_USER: cloven
      OLLAMA_PORT: "11434"
      WEBUI_PORT: "8080"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 5
    depends_on:
      cloven_tectum_db:
        condition: service_started

  cloven_tectum_db:
    image: ankane/pgvector:latest
    container_name: cloven_tectum_db
    restart: always
    environment:
      POSTGRES_DB: cloven_tectum
      POSTGRES_USER: cloven
      POSTGRES_PASSWORD: tectum123
    ports:
      - "5432:5432"
    volumes:
      - cloven_db_data:/var/lib/postgresql/data

  cloven_tectum_inserter:
    build:
      context: ./tectum_framework/agents/inserter
    container_name: cloven_tectum_inserter
    restart: on-failure
    depends_on:
      cloven_tectum_api:
        condition: service_started
    environment:
      API_PORT: "8000"
      DATABASE_NAME: cloven_tectum
      DATABASE_PASS: tectum123
      DATABASE_PORT: "5432"
      DATABASE_USER: cloven
      OLLAMA_PORT: "11434"
      WEBUI_PORT: "8080"

  cloven_tectum_scraper:
    build:
      context: ./tectum_framework/agents/scraper
    container_name: cloven_tectum_scraper
    restart: on-failure
    depends_on:
      cloven_tectum_api:
        condition: service_started
    environment:
      API_PORT: "8000"
      DATABASE_NAME: cloven_tectum
      DATABASE_PASS: tectum123
      DATABASE_PORT: "5432"
      DATABASE_USER: cloven
      OLLAMA_PORT: "11434"
      WEBUI_PORT: "8080"

  cloven_tectum_ollama:
    build:
      context: ./tectum_framework/ollama
    container_name: cloven_tectum_ollama
    restart: always
    ports:
      - "11434:11434"
    environment:
      OLLAMA_HOST: 0.0.0.0:11434
    volumes:
      - ollama_models:/root/.ollama

  cloven_tectum_webui:
    image: ghcr.io/open-webui/open-webui:main
    container_name: cloven_tectum_webui
    restart: always
    ports:
      - "8080:8080"
    depends_on:
      cloven_tectum_ollama:
        condition: service_started
    environment:
      OLLAMA_HOST: http://cloven_tectum_ollama:11434
    volumes:
      - open-webui-data:/app/backend/data

volumes:
  cloven_db_data:
  ollama_models:
  open-webui-data:
EOF
}

function write_readme() {
    echo "[+] Updating README.md and ABOUT.md..."

    cat > README.md <<EOF
# Cloven Distro TectumFW

This is an automated containerized AI framework including FastAPI, Ollama LLMs, Open WebUI, vector DB, and ingest agents.

Run \`./serversetup.sh\` to build the environment.
Run \`./teardown.sh\` to destroy it.
EOF

    cat > ABOUT.md <<EOF
## About Cloven_Tectum Framework

This project builds a fully functional AI ingest stack with:

- 🧠 LLM (Ollama)
- 🌐 WebUI for chat
- 🧬 Vector DB (PostgreSQL + pgvector)
- 🔌 FastAPI service
- 🛰 Scraper & Inserter agents

Built with ❤️ by Cloven.
EOF
}

function write_teardown() {
    cat > teardown.sh <<EOF
#!/bin/bash
echo "[!] Stopping and cleaning up..."
docker compose down -v
echo "[!] Removing generated files..."
rm -rf tectum_framework docker-compose.yml README.md ABOUT.md .version
echo "[✓] Teardown complete."
EOF
    chmod +x teardown.sh
}

# === Run Setup ===
bump_version
create_dirs
write_stubs
write_docker_compose
write_readme
write_teardown

echo "[✓] Starting containers..."
docker compose up -d --build

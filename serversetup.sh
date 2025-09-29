#!/usr/bin/env bash
set -euo pipefail

# =========================
# Cloven_Tectum One-Click Bootstrap
# =========================
# Usage:
#   ./serversetup.sh            # generate files & compose UP
#   ./serversetup.sh --no-up    # generate files only
#   ./serversetup.sh --force    # overwrite existing files
#
# Guarantees:
# - Writes docker-compose.yml
# - Writes Dockerfiles & minimal code for api + agents
# - Creates .env if missing (with sane defaults)
# - Ensures perms; starts containers (unless --no-up)
#
# Never gonna give you up. 👋 source viewer.

FORCE=false
NO_UP=false
for a in "$@"; do
  case "$a" in
    --force) FORCE=true ;;
    --no-up) NO_UP=true ;;
    *) echo "[ERROR] Unknown flag: $a"; exit 1 ;;
  esac
done

log()  { echo "[*] $*"; }
warn() { echo "[!] $*"; }
err()  { echo "[ERROR] $*" >&2; exit 1; }

# Detect docker compose cmd
if docker compose version >/dev/null 2>&1; then
  DOCKER_COMPOSE="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  DOCKER_COMPOSE="docker-compose"
else
  err "docker compose not found. Install Docker Compose plugin or docker-compose."
fi

write_file() {
  # $1 = path, $2 = content
  local path="$1"
  if [[ -f "$path" && "$FORCE" == "false" ]]; then
    log "Skip (exists): $path"
    return 0
  fi
  mkdir -p "$(dirname "$path")"
  printf "%s" "$2" > "$path"
  log "Wrote: $path"
}

append_unique() {
  # $1 = path, $2 = line
  local path="$1" line="$2"
  touch "$path"
  if ! grep -qxF "$line" "$path" 2>/dev/null; then
    echo "$line" >> "$path"
    log "Appended to $(basename "$path"): $line"
  fi
}

# ---------- ensure base dirs ----------
log "Ensuring project directories..."
mkdir -p tectum_framework/{api_server,ollama,agents/{scraper,inserter}}
mkdir -p logs assets .git/hooks

# ---------- .gitignore ----------
write_file ".gitignore" "$(cat <<'EOF'
# Python
__pycache__/
*.pyc
*.pyo

# Local env
.env

# Docker runtime data
logs/
db_data/
ollama_models/
open-webui-data/
EOF
)"

# ---------- .env & example ----------
if [[ ! -f ".env" || "$FORCE" == "true" ]]; then
  write_file ".env" "$(cat <<'EOF'
DATABASE_USER=cloven_user
DATABASE_PASS=changeme
DATABASE_NAME=cloven_db
DATABASE_PORT=5432

API_PORT=8000
OLLAMA_PORT=11434
WEBUI_PORT=8080
EOF
)"
fi
write_file ".env.example" "$(cat .env)"

# ---------- API app ----------
write_file "tectum_framework/api_server/main.py" "$(cat <<'EOF'
from fastapi import FastAPI

app = FastAPI(title="Cloven Tectum API", version="0.1.0")

@app.get("/")
def root():
    return {"message": "Cloven Tectum online — uptime is truth."}

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/rickroll")
def rickroll():
    # never gonna run around and desert you
    return {"hint": "Never gonna let you down"}
EOF
)"

# ---------- Dockerfiles ----------
write_file "tectum_framework/api_server/Dockerfile" "$(cat <<'EOF'
FROM python:3.11-slim

WORKDIR /app
COPY ./ /app

# Minimal deps; DB libs can be added later
RUN pip install --no-cache-dir fastapi uvicorn[standard]

EXPOSE 8000
CMD ["uvicorn","main:app","--host","0.0.0.0","--port","8000"]
EOF
)"

write_file "tectum_framework/ollama/Dockerfile" "$(cat <<'EOF'
FROM ollama/ollama:latest
VOLUME /root/.ollama
EXPOSE 11434
CMD ["ollama","serve"]
EOF
)"

write_file "tectum_framework/agents/scraper/Dockerfile" "$(cat <<'EOF'
FROM python:3.11-slim
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir requests aiohttp beautifulsoup4
CMD ["python","scraper.py"]
EOF
)"

write_file "tectum_framework/agents/inserter/Dockerfile" "$(cat <<'EOF'
FROM python:3.11-slim
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir sqlalchemy[asyncio] asyncpg
CMD ["python","insert_nodes.py"]
EOF
)"

# ---------- Agent stubs so containers don't crash ----------
write_file "tectum_framework/agents/scraper/scraper.py" "$(cat <<'EOF'
import time, sys
print("[scraper] starting… (stub) never gonna make you cry")
try:
    while True:
        time.sleep(10)
        print("[scraper] heartbeat")
except KeyboardInterrupt:
    sys.exit(0)
EOF
)"

write_file "tectum_framework/agents/inserter/insert_nodes.py" "$(cat <<'EOF'
import time, sys
print("[inserter] starting… (stub) never gonna say goodbye")
try:
    while True:
        time.sleep(10)
        print("[inserter] heartbeat")
except KeyboardInterrupt:
    sys.exit(0)
EOF
)"

# ---------- docker-compose.yml ----------
# NOTE: no "version:" key (compose v2 deprecates it)
# API listens on container:8000 -> host:${API_PORT}
write_file "docker-compose.yml" "$(cat <<'EOF'
services:
  cloven_tectum_db:
    image: ankane/pgvector:latest
    container_name: cloven_tectum_db
    restart: always
    environment:
      POSTGRES_USER: ${DATABASE_USER}
      POSTGRES_PASSWORD: ${DATABASE_PASS}
      POSTGRES_DB: ${DATABASE_NAME}
    ports:
      - "${DATABASE_PORT}:5432"
    volumes:
      - cloven_db_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${DATABASE_USER}"]
      interval: 10s
      timeout: 5s
      retries: 5

  cloven_tectum_api:
    build: ./tectum_framework/api_server
    container_name: cloven_tectum_api
    restart: unless-stopped
    env_file:
      - .env
    depends_on:
      - cloven_tectum_db
    ports:
      - "${API_PORT}:8000"
    volumes:
      - ./tectum_framework/api_server:/app

  cloven_tectum_ollama:
    build: ./tectum_framework/ollama
    container_name: cloven_tectum_ollama
    restart: always
    ports:
      - "${OLLAMA_PORT}:11434"
    volumes:
      - ollama_models:/root/.ollama

  cloven_tectum_webui:
    image: ghcr.io/open-webui/open-webui:main
    container_name: cloven_tectum_webui
    restart: always
    depends_on:
      - cloven_tectum_ollama
    environment:
      - OLLAMA_HOST=http://cloven_tectum_ollama:11434
    ports:
      - "${WEBUI_PORT}:8080"
    volumes:
      - open-webui-data:/app/backend/data

  cloven_tectum_scraper:
    build: ./tectum_framework/agents/scraper
    container_name: cloven_tectum_scraper
    restart: on-failure
    env_file:
      - .env
    depends_on:
      - cloven_tectum_api

  cloven_tectum_inserter:
    build: ./tectum_framework/agents/inserter
    container_name: cloven_tectum_inserter
    restart: on-failure
    env_file:
      - .env
    depends_on:
      - cloven_tectum_api

volumes:
  cloven_db_data:
  ollama_models:
  open-webui-data:
EOF
)"

# ---------- perms ----------
chmod +x serversetup.sh || true

# ---------- bring up ----------
if [[ "$NO_UP" == "true" ]]; then
  log "Generation complete (skipping compose up due to --no-up)."
  exit 0
fi

log "Building & starting containers…"
$DOCKER_COMPOSE up -d --build

API_PORT="$(grep -E '^API_PORT=' .env | cut -d '=' -f2)"
WEBUI_PORT="$(grep -E '^WEBUI_PORT=' .env | cut -d '=' -f2)"

echo
echo "=== Online (expected) ==="
echo "API docs:  http://localhost:${API_PORT}/docs"
echo "WebUI:     http://localhost:${WEBUI_PORT}"
echo
echo "Check status:   $DOCKER_COMPOSE ps"
echo "Tail logs:      docker logs -f cloven_tectum_api"

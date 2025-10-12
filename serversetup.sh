#!/bin/bash

set -e

# ─── CONFIGURATION ─────────────────────────────────────────────────────────────
ENV_FILE=".env"
VERSION_FILE=".version"
README_TEMPLATE="README.template.md"
ABOUT_TEMPLATE="ABOUT.template.md"
README_OUTPUT="README.md"
ABOUT_OUTPUT="ABOUT.md"
LOG_FILE="build_log.txt"

# ─── FLAGS ─────────────────────────────────────────────────────────────────────
DRY_RUN=false

for arg in "$@"; do
    if [[ "$arg" == "--dry-run" ]]; then
        DRY_RUN=true
        echo "[Dry Run] No changes will be made."
    fi
done

# ─── CLEANUP ───────────────────────────────────────────────────────────────────
echo "[+] Checking for existing containers..."
if $DRY_RUN; then
    echo "[Dry Run] Would remove existing containers related to Cloven_Tectum"
else
    docker ps -a --filter "name=cloven_tectum_" --format "{{.Names}}" | while read -r name; do
        echo "[-] Removing container: $name"
        docker rm -f "$name"
    done
fi

# ─── VERSION BUMP ──────────────────────────────────────────────────────────────
if [[ ! -f "$VERSION_FILE" ]]; then
    echo "0.1.0" > "$VERSION_FILE"
fi

OLD_VERSION=$(cat "$VERSION_FILE")
IFS='.' read -r major minor patch <<< "$OLD_VERSION"
NEW_VERSION="$major.$minor.$((patch + 1))"
echo "$NEW_VERSION" > "$VERSION_FILE"
echo "[✓] Version bumped: $OLD_VERSION → $NEW_VERSION"

# ─── GIT INFO ──────────────────────────────────────────────────────────────────
GIT_HASH=$(git rev-parse --short HEAD || echo "unknown")
BUILD_DATE=$(date "+%Y-%m-%d")

# ─── ENV FILE ──────────────────────────────────────────────────────────────────
if [[ ! -f "$ENV_FILE" ]]; then
    echo "[+] Creating default .env"
    cat <<EOF > "$ENV_FILE"
# Auto-generated .env
DATABASE_USER=cloven
DATABASE_PASS=clovenpass
DATABASE_NAME=tectum
DATABASE_PORT=5432
API_PORT=8000
WEBUI_PORT=8080
OLLAMA_PORT=11434
EOF
fi

# ─── DOCKER COMPOSE ────────────────────────────────────────────────────────────
echo "[+] Writing docker-compose.yml..."
cat <<EOF > docker-compose.yml
version: '3.8'
services:
  cloven_tectum_db:
    image: ankane/pgvector:latest
    container_name: cloven_tectum_db
    restart: always
    environment:
      POSTGRES_USER: \${DATABASE_USER}
      POSTGRES_PASSWORD: \${DATABASE_PASS}
      POSTGRES_DB: \${DATABASE_NAME}
    ports:
      - "\${DATABASE_PORT}:5432"
    volumes:
      - cloven_db_data:/var/lib/postgresql/data

  cloven_tectum_api:
    build: ./tectum_framework/api_server
    container_name: cloven_tectum_api
    restart: unless-stopped
    env_file:
      - .env
    depends_on:
      - cloven_tectum_db
    ports:
      - "\${API_PORT}:8000"
    volumes:
      - ./tectum_framework/api_server:/app

  cloven_tectum_ollama:
    build: ./tectum_framework/ollama
    container_name: cloven_tectum_ollama
    restart: always
    ports:
      - "\${OLLAMA_PORT}:11434"
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
      - "\${WEBUI_PORT}:8080"
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

# ─── UPDATE MARKDOWN FILES ─────────────────────────────────────────────────────
echo "[+] Updating README.md and ABOUT.md..."
for template in "$README_TEMPLATE" "$ABOUT_TEMPLATE"; do
    if [[ -f "$template" ]]; then
        sed -e "s|{{VERSION}}|$NEW_VERSION|g" \
            -e "s|{{GIT_HASH}}|$GIT_HASH|g" \
            -e "s|{{DATE}}|$BUILD_DATE|g" \
            "$template" > "${template%.template.md}.md"
    fi
done

# ─── DOCKER COMPOSE UP ─────────────────────────────────────────────────────────
if $DRY_RUN; then
    echo "[Dry Run] Would run: docker compose up -d --build"
else
    echo "[✓] Starting containers..."
    docker compose up -d --build
fi

# ─── DONE ──────────────────────────────────────────────────────────────────────
echo -e "\n[✔] Cloven_Tectum is ready. Access:\n"
echo "• API Docs:        http://localhost:8000/docs"
echo "• WebUI (OpenUI):  http://localhost:8080"
echo -e "\n[✔] Version: $NEW_VERSION | Commit: $GIT_HASH | Date: $BUILD_DATE"

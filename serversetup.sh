#!/bin/bash
# serversetup.sh - Bootstrapper for Cloven_Tectum Framework

set -e

###############################
# 📦 Metadata & Versioning
###############################
VERSION_FILE=".version"
ABOUT_TEMPLATE="ABOUT.template.md"
README_TEMPLATE="README.template.md"

if [ ! -f "$VERSION_FILE" ]; then
  echo "0.1.0" > "$VERSION_FILE"
fi

OLD_VERSION=$(cat "$VERSION_FILE")
IFS='.' read -r major minor patch <<< "$OLD_VERSION"
NEW_VERSION="$major.$minor.$((patch + 1))"
echo "$NEW_VERSION" > "$VERSION_FILE"
echo "[✓] Version bumped: $OLD_VERSION → $NEW_VERSION"

DATE=$(date -u +"%Y-%m-%d")
GIT_HASH=$(git rev-parse --short HEAD 2>/dev/null || echo "dev")

###############################
# 🧱 Create Directory Structure
###############################
echo "[+] Creating directories..."
mkdir -p tectum_framework/api_server
mkdir -p tectum_framework/ollama
mkdir -p tectum_framework/agents/scraper
mkdir -p tectum_framework/agents/inserter
mkdir -p assets

###############################
# 📄 Generate Core Files
###############################

echo "[+] Writing Dockerfiles and app stubs..."

# API Server Dockerfile
cat > tectum_framework/api_server/Dockerfile <<EOF
FROM python:3.11
WORKDIR /app
COPY . .
RUN pip install fastapi uvicorn psycopg2-binary
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
EOF

# API Server Main App
cat > tectum_framework/api_server/main.py <<EOF
from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def read_root():
    return {"message": "Cloven Tectum API is live."}
EOF

# Ollama Dockerfile
cat > tectum_framework/ollama/Dockerfile <<EOF
FROM ollama/ollama:latest
ENV OLLAMA_HOST=0.0.0.0:11434
EXPOSE 11434
CMD ["serve"]
EOF

# Scraper Dockerfile
cat > tectum_framework/agents/scraper/Dockerfile <<EOF
FROM python:3.11
WORKDIR /app
COPY . .
RUN pip install requests
CMD ["python", "main.py"]
EOF

# Scraper main.py
cat > tectum_framework/agents/scraper/main.py <<EOF
print("[Scraper] Agent starting... (stub)")
EOF

# Inserter Dockerfile
cat > tectum_framework/agents/inserter/Dockerfile <<EOF
FROM python:3.11
WORKDIR /app
COPY . .
RUN pip install psycopg2-binary
CMD ["python", "main.py"]
EOF

# Inserter main.py
cat > tectum_framework/agents/inserter/main.py <<EOF
print("[Inserter] Agent starting... (stub)")
EOF

###############################
# 🐳 Compose File
###############################
echo "[+] Writing docker-compose.yml..."
cat > docker-compose.yml <<EOF
version: '3.9'
services:
  cloven_tectum_api:
    build: ./tectum_framework/api_server
    container_name: cloven_tectum_api
    environment:
      API_PORT: 8000
    ports:
      - "8000:8000"
    restart: unless-stopped

  cloven_tectum_db:
    image: ankane/pgvector:latest
    container_name: cloven_tectum_db
    environment:
      POSTGRES_DB: cloven_tectum
      POSTGRES_USER: cloven
      POSTGRES_PASSWORD: tectum123
    ports:
      - "5432:5432"
    volumes:
      - cloven_db_data:/var/lib/postgresql/data
    restart: always

  cloven_tectum_ollama:
    build: ./tectum_framework/ollama
    container_name: cloven_tectum_ollama
    ports:
      - "11434:11434"
    volumes:
      - ollama_models:/root/.ollama
    restart: always

  cloven_tectum_webui:
    image: ghcr.io/open-webui/open-webui:main
    container_name: cloven_tectum_webui
    depends_on:
      - cloven_tectum_ollama
    environment:
      OLLAMA_HOST: http://cloven_tectum_ollama:11434
    ports:
      - "8080:8080"
    volumes:
      - open-webui-data:/app/backend/data
    restart: always

  cloven_tectum_scraper:
    build: ./tectum_framework/agents/scraper
    container_name: cloven_tectum_scraper
    depends_on:
      - cloven_tectum_api
    restart: on-failure

  cloven_tectum_inserter:
    build: ./tectum_framework/agents/inserter
    container_name: cloven_tectum_inserter
    depends_on:
      - cloven_tectum_api
    restart: on-failure

volumes:
  cloven_db_data:
  ollama_models:
  open-webui-data:
EOF

###############################
# 📝 Auto-generate Docs
###############################
echo "[+] Updating README.md and ABOUT.md..."

sed -e "s/{{VERSION}}/$NEW_VERSION/" \
    -e "s/{{DATE}}/$DATE/" \
    -e "s/{{GIT_HASH}}/$GIT_HASH/" \
    "$README_TEMPLATE" > README.md

sed -e "s/{{VERSION}}/$NEW_VERSION/" \
    -e "s/{{DATE}}/$DATE/" \
    -e "s/{{GIT_HASH}}/$GIT_HASH/" \
    "$ABOUT_TEMPLATE" > ABOUT.md

###############################
# 🚀 Deploy Services
###############################
echo "[✓] Starting containers..."
docker compose up -d --build
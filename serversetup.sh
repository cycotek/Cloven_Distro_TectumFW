#!/bin/bash

set -e

PROJECT_NAME="Cloven_Tectum"
VERSION_FILE=".version"
DRY_RUN=false

# --- Helpers ---
info()  { echo -e "\033[1;34m[+]\033[0m $1"; }
done_() { echo -e "\033[1;32m[✓]\033[0m $1"; }
warn()  { echo -e "\033[1;33m[!]\033[0m $1"; }

# --- Dry run check ---
if [[ "$1" == "--dry-run" ]]; then
  DRY_RUN=true
  info "Running in dry-run mode..."
fi

# --- Shut down old containers ---
info "Checking for existing containers..."
if ! $DRY_RUN; then
  docker ps -a --filter "name=cloven_tectum_" --format "{{.Names}}" | \
    xargs -r docker rm -f
fi

# --- Version bump ---
if [ -f "$VERSION_FILE" ]; then
  CUR_VER=$(cat $VERSION_FILE)
  MAJOR=$(echo "$CUR_VER" | cut -d. -f1)
  MINOR=$(echo "$CUR_VER" | cut -d. -f2)
  PATCH=$(echo "$CUR_VER" | cut -d. -f3)
  PATCH=$((PATCH+1))
  NEW_VER="$MAJOR.$MINOR.$PATCH"
else
  NEW_VER="0.1.0"
fi

echo "$NEW_VER" > "$VERSION_FILE"
done_ "Version bumped: $CUR_VER → $NEW_VER"

# --- Create folder structure ---
mkdir -p tectum_framework/api_server
mkdir -p tectum_framework/ollama
mkdir -p tectum_framework/agents/scraper
mkdir -p tectum_framework/agents/inserter

# --- Create default main.py for agents ---
for agent in scraper inserter; do
  AGENT_PATH="tectum_framework/agents/$agent/main.py"
  if [ ! -f "$AGENT_PATH" ]; then
    cat <<EOF > "$AGENT_PATH"
print("[$agent agent] running...")
EOF
    done_ "Created placeholder: $AGENT_PATH"
  fi
done

# --- Dockerfiles ---
cat <<EOF > tectum_framework/api_server/Dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install fastapi uvicorn psycopg2-binary sqlalchemy
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
EOF

cat <<EOF > tectum_framework/ollama/Dockerfile
FROM ollama/ollama:latest
VOLUME /root/.ollama
EXPOSE 11434
EOF

for agent in scraper inserter; do
cat <<EOF > tectum_framework/agents/$agent/Dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . .
CMD ["python", "main.py"]
EOF
done

# --- .env file ---
if [ ! -f .env ]; then
cat <<EOF > .env
DATABASE_USER=cloven
DATABASE_PASS=tectum123
DATABASE_NAME=cloven_tectum
DATABASE_PORT=5432
API_PORT=8000
OLLAMA_PORT=11434
WEBUI_PORT=8080
EOF
  done_ "Created default .env"
fi

# --- docker-compose.yml ---
cat <<EOF > docker-compose.yml
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
    env_file: .env
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
    env_file: .env
    depends_on:
      - cloven_tectum_api

  cloven_tectum_inserter:
    build: ./tectum_framework/agents/inserter
    container_name: cloven_tectum_inserter
    restart: on-failure
    env_file: .env
    depends_on:
      - cloven_tectum_api

volumes:
  cloven_db_data:
  ollama_models:
  open-webui-data:
EOF

done_ "Writing docker-compose.yml..."

# --- Inject version & metadata into markdowns ---
GIT_HASH=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
BUILD_DATE=$(date +%F)

sed "s/{{VERSION}}/$NEW_VER/g; s/{{GIT_HASH}}/$GIT_HASH/g; s/{{DATE}}/$BUILD_DATE/g" README.template.md > README.md
sed "s/{{VERSION}}/$NEW_VER/g; s/{{GIT_HASH}}/$GIT_HASH/g; s/{{DATE}}/$BUILD_DATE/g" ABOUT.template.md > ABOUT.md
done_ "Updating README.md and ABOUT.md..."

# --- Compose up ---
if ! $DRY_RUN; then
  docker compose up -d --build
  done_ "Starting containers..."
else
  warn "Dry-run mode: Skipped starting containers"
fi

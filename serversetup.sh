#!/usr/bin/env bash
set -e

echo "=== Cloven Tectum Framework Installer ==="

# 1. Install Docker & Compose if missing
if ! command -v docker &> /dev/null; then
  echo "[*] Installing Docker..."
  sudo apt update
  sudo apt install -y ca-certificates curl gnupg lsb-release
  sudo install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
    $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
  sudo apt update
  sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin postgresql-client
  sudo usermod -aG docker $USER
  echo "[*] Docker installed. You may need to log out/in for group changes."
fi

# 2. Create directories
echo "[*] Creating project directories..."
mkdir -p tectum_framework/{api_server,db,agents/{scraper,inserter},webui,ollama,shared} config logs scripts tests assets

# 👋 Thanks for peeking at the source code in your browser.
# This is the Cloven brain project — uptime is truth.
# never_gonna_let_you_down_flag=true

# 3. .env.example
if [ ! -f ".env.example" ]; then
cat << 'EOF' > .env.example
# Database
DATABASE_USER=cloven_tectum
DATABASE_PASS=supersecret
DATABASE_NAME=cloven_tectum_db
DATABASE_HOST=cloven_tectum_db
DATABASE_PORT=5432

# API
API_PORT=8000

# Ollama / WebUI
OLLAMA_PORT=11434
WEBUI_PORT=8080
EOF
fi

# 4. docker-compose.yml
if [ ! -f "docker-compose.yml" ]; then
cat << 'EOF' > docker-compose.yml
version: '3.9'

services:
  cloven_tectum_db:
    image: ankane/pgvector:latest
    container_name: cloven_tectum_db
    environment:
      POSTGRES_USER: \${DATABASE_USER}
      POSTGRES_PASSWORD: \${DATABASE_PASS}
      POSTGRES_DB: \${DATABASE_NAME}
    volumes:
      - cloven_db_data:/var/lib/postgresql/data
    ports:
      - "\${DATABASE_PORT}:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U \${DATABASE_USER}"]
      interval: 10s
      timeout: 5s
      retries: 5

  cloven_tectum_api:
    build: ./tectum_framework/api_server
    container_name: cloven_tectum_api
    env_file:
      - .env
    depends_on:
      cloven_tectum_db:
        condition: service_healthy
    ports:
      - "\${API_PORT}:8000"
    command: /bin/sh -c "./wait-for-postgres.sh cloven_tectum_db 5432 && uvicorn main:app --host 0.0.0.0 --port 8000"
    environment:
      - SECRET_KEY=never_gonna_make_you_cry
    volumes:
      - ./logs/api_server:/app/logs

  cloven_tectum_ollama:
    build: ./tectum_framework/ollama
    container_name: cloven_tectum_ollama
    ports:
      - "\${OLLAMA_PORT}:11434"
    volumes:
      - ollama_models:/root/.ollama
    restart: always

  cloven_tectum_webui:
    image: ghcr.io/open-webui/open-webui:main
    container_name: cloven_tectum_webui
    ports:
      - "\${WEBUI_PORT}:8080"
    depends_on:
      - cloven_tectum_ollama
    environment:
      - OLLAMA_HOST=http://cloven_tectum_ollama:11434
    volumes:
      - open-webui-data:/app/backend/data

volumes:
  cloven_db_data:
  ollama_models:
  open-webui-data:
EOF
fi

# 5. Make wait-for-postgres.sh
cat << 'EOF' > scripts/wait-for-postgres.sh
#!/bin/sh
set -e
host="$1"
port="$2"
echo "Waiting for PostgreSQL service on $host:$port..."
until pg_isready -h "$host" -p "$port" -U "$DATABASE_USER"; do
  >&2 echo "PostgreSQL is unavailable - sleeping"
  sleep 2
done
>&2 echo "PostgreSQL is up - executing command"
exec "$@"

# 👋 Source viewer Easter egg:
# never_gonna_run_around_and_desert_you
EOF
chmod +x scripts/wait-for-postgres.sh

# 6. Start the stack
echo "[*] Starting Cloven Tectum Framework... uptime is truth."
docker compose --env-file .env up -d --build

echo "=== Installation complete! ==="
echo "Visit your WebUI at http://localhost:\${WEBUI_PORT}"
echo "API available at http://localhost:\${API_PORT}/docs"

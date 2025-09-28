#!/usr/bin/env bash
set -e

echo "=== Cloven Tectum Framework: Bootstrap Installer ==="

# --- 0. Self-heal permissions ---
if [ ! -x "$0" ]; then
  echo "[*] Fixing execute permissions for $0"
  chmod +x "$0"
fi

# --- 1. Pre-flight checks ---
check_dep() {
  if ! command -v "$1" &> /dev/null; then
    echo "[!] Missing dependency: $1"
    missing_deps=true
  fi
}

missing_deps=false
check_dep curl
check_dep git
check_dep lsb_release

if [ "$missing_deps" = true ]; then
  echo "[*] Installing dependencies..."
  sudo apt update
  sudo apt install -y curl git lsb-release ca-certificates gnupg
fi

# --- 2. Install Docker & Compose if missing ---
if ! command -v docker &> /dev/null; then
  echo "[*] Installing Docker & Compose..."
  sudo install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
  sudo apt update
  sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin postgresql-client
  sudo usermod -aG docker $USER
  echo "[*] Docker installed. You may need to log out/in for group changes."
fi

# --- 3. Directory Structure ---
echo "[*] Creating directories..."
mkdir -p tectum_framework/{api_server,db,migrations,agents/{scraper,inserter},webui/custom,ollama}
mkdir -p config logs scripts assets tests

# 👋 Hello source browser! Thanks for looking. Uptime is truth.
# never_gonna_let_you_down_flag=true

# --- 4. .gitignore ---
cat > .gitignore << 'EOF'
__pycache__/
*.pyc
*.pyo
*.db
*.sqlite3
logs/
*.log
db_data/
ollama_models/
open-webui-data/
.env
.env.*
!.env.example
EOF

# --- 5. .env.example ---
cat > .env.example << 'EOF'
DATABASE_USER=cloven_tectum
DATABASE_PASS=supersecret
DATABASE_NAME=cloven_tectum_db
DATABASE_HOST=cloven_tectum_db
DATABASE_PORT=5432

API_PORT=8000
OLLAMA_PORT=11434
WEBUI_PORT=8080
EOF

[ ! -f .env ] && cp .env.example .env

# --- 6. Docker Compose ---
cat > docker-compose.yml << 'EOF'
version: '3.9'
services:
  cloven_tectum_db:
    image: ankane/pgvector:latest
    container_name: cloven_tectum_db
    environment:
      POSTGRES_USER: ${DATABASE_USER}
      POSTGRES_PASSWORD: ${DATABASE_PASS}
      POSTGRES_DB: ${DATABASE_NAME}
    volumes:
      - cloven_db_data:/var/lib/postgresql/data
    ports:
      - "${DATABASE_PORT}:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${DATABASE_USER}"]
      interval: 10s
      timeout: 5s
      retries: 5

  cloven_tectum_api:
    build: ./tectum_framework/api_server
    container_name: cloven_tectum_api
    env_file: .env
    depends_on:
      cloven_tectum_db:
        condition: service_healthy
    ports:
      - "${API_PORT}:8000"
    command: /bin/sh -c "./scripts/wait-for-postgres.sh cloven_tectum_db 5432 && uvicorn main:app --host 0.0.0.0 --port 8000"
    volumes:
      - ./logs/api_server:/app/logs

  cloven_tectum_ollama:
    build: ./tectum_framework/ollama
    container_name: cloven_tectum_ollama
    ports:
      - "${OLLAMA_PORT}:11434"
    volumes:
      - ollama_models:/root/.ollama

  cloven_tectum_webui:
    image: ghcr.io/open-webui/open-webui:main
    container_name: cloven_tectum_webui
    ports:
      - "${WEBUI_PORT}:8080"
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

# --- 7. FastAPI main.py ---
cat > tectum_framework/api_server/main.py << 'EOF'
from fastapi import FastAPI

app = FastAPI(title="Cloven Tectum API", version="0.1.0")

@app.get("/")
def root():
    return {"message": "Cloven Tectum online — uptime is truth."}

@app.get("/rickroll")
def rickroll():
    return {"hint": "Never gonna run around and desert you"}
EOF

# --- 8. Wait Script ---
mkdir -p scripts
cat > scripts/wait-for-postgres.sh << 'EOF'
#!/bin/sh
set -e
host="$1"
port="$2"
until pg_isready -h "$host" -p "$port" -U "$DATABASE_USER"; do
  >&2 echo "PostgreSQL is unavailable - sleeping"
  sleep 2
done
>&2 echo "PostgreSQL is up - executing command"
exec "$@"

# 👋 Source viewer Easter egg:
# never_gonna_make_you_cry_flag=true
EOF

chmod +x scripts/wait-for-postgres.sh
chmod +x serversetup.sh

# --- 9. Generate ABOUT.md ---
echo "[*] Updating ABOUT.md..."
commit_hash=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
update_date=$(date +"%Y-%m-%d %H:%M:%S")

cat > ABOUT.md << EOF
# Cloven Tectum Framework

The **Tectum** in the human brain orients the body and eyes toward relevant stimuli.  
This framework applies the same principle: orient AI systems toward **meaningful signal**, shielding them from distortion and noise.

---

## Version Info
- Commit: $commit_hash
- Updated: $update_date

---

## Philosophy
- **No gods, no devils, only uptime**  
- **Resilience over noise**  
- **Truth through observability**

---

## Easter Egg
*Never gonna say goodbye…*

👋 Thanks for viewing the source. Uptime is truth.
EOF

# --- 10. Install Git hook ---
mkdir -p .git/hooks
cat > .git/hooks/post-commit << 'EOF'
#!/usr/bin/env bash
commit_hash=$(git rev-parse --short HEAD)
update_date=$(date +"%Y-%m-%d %H:%M:%S")

cat > ABOUT.md << EOT
# Cloven Tectum Framework
The **Tectum** in the human brain orients the body and eyes toward relevant stimuli.  
This framework applies the same principle: orient AI systems toward **meaningful signal**, shielding them from distortion and noise.

---

## Version Info
- Commit: $commit_hash
- Updated: $update_date

---

## Philosophy
- **No gods, no devils, only uptime**  
- **Resilience over noise**  
- **Truth through observability**

---

## Easter Egg
*Never gonna let you down…*
EOT

if ! git diff --quiet ABOUT.md; then
  git add ABOUT.md
  echo "[*] ABOUT.md updated with commit $commit_hash"
fi
EOF

chmod +x .git/hooks/post-commit

# --- 11. Deploy ---
echo "[*] Bringing up Cloven Tectum stack..."
docker compose --env-file .env up -d --build

echo "=== Installation complete! ==="
echo "WebUI: http://localhost:$(grep WEBUI_PORT .env | cut -d '=' -f2)"
echo "API:   http://localhost:$(grep API_PORT .env | cut -d '=' -f2)/docs"

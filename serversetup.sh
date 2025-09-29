#!/usr/bin/env bash
set -euo pipefail

echo "=== Cloven_Tectum Framework: Full Bootstrap ==="

# --- Directories ---
echo "[*] Creating project directories..."
mkdir -p tectum_framework/{ollama,api_server,agents/{scraper,inserter}}
mkdir -p assets
mkdir -p .git/hooks

# --- Dockerfiles ---
echo "[*] Generating Dockerfiles..."

# Ollama
cat > tectum_framework/ollama/Dockerfile <<'EOF'
FROM ollama/ollama:latest
VOLUME /root/.ollama
CMD ["ollama", "serve"]
EOF

# API Server
cat > tectum_framework/api_server/Dockerfile <<'EOF'
FROM python:3.11-slim
WORKDIR /app
COPY ./ /app
RUN pip install --no-cache-dir fastapi uvicorn[standard] sqlalchemy[asyncio] asyncpg psycopg2-binary
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
EOF

# Scraper Agent
cat > tectum_framework/agents/scraper/Dockerfile <<'EOF'
FROM python:3.11-slim
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir requests beautifulsoup4 aiohttp
CMD ["python", "scraper.py"]
EOF

# Inserter Agent
cat > tectum_framework/agents/inserter/Dockerfile <<'EOF'
FROM python:3.11-slim
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir sqlalchemy[asyncio] asyncpg
CMD ["python", "insert_nodes.py"]
EOF

# --- Env Files ---
echo "[*] Setting up environment files..."
cat > .env.example <<'EOF'
API_PORT=8000
WEBUI_PORT=8080
DATABASE_USER=cloven_user
DATABASE_PASS=changeme
DATABASE_NAME=cloven_db
DATABASE_PORT=5432
EOF

if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "[INFO] .env created from example (edit as needed)."
fi

# --- README template ---
if [ ! -f "README.template.md" ]; then
    cat > README.template.md <<'EOF'
# Cloven_Tectum Framework

**Version**: {{VERSION}}  
**Commit**: {{GIT_HASH}}  
**Date**: {{DATE}}

API runs on port **{{API_PORT}}**  
WebUI runs on port **{{WEBUI_PORT}}**

The **Tectum** in the brain orients the body and eyes toward relevant stimuli.  
This framework applies the same principle: orient AI systems toward **meaningful signal**, shielding them from distortion and noise.
EOF
fi

# --- Update script ---
cat > update_readme.sh <<'EOF'
#!/usr/bin/env bash
set -e

if [ ! -f ".env" ]; then
  echo "[ERROR] .env file missing. Run: cp .env.example .env && edit it with your secrets."
  exit 1
fi

VERSION="0.1.0"
GIT_HASH=$(git rev-parse --short HEAD 2>/dev/null || echo "no-git")
DATE=$(date +"%Y-%m-%d")
API_PORT=$(grep API_PORT .env | cut -d '=' -f2)
WEBUI_PORT=$(grep WEBUI_PORT .env | cut -d '=' -f2)

sed -e "s/{{VERSION}}/$VERSION/" \
    -e "s/{{GIT_HASH}}/$GIT_HASH/" \
    -e "s/{{DATE}}/$DATE/" \
    -e "s/{{API_PORT}}/$API_PORT/" \
    -e "s/{{WEBUI_PORT}}/$WEBUI_PORT/" \
    README.template.md > README.md

echo "[INFO] README.md updated with version, commit, and date."
EOF

chmod +x update_readme.sh

# --- Git hook ---
cat > .git/hooks/post-commit <<'EOF'
#!/usr/bin/env bash
./update_readme.sh
git add README.md
git commit --amend --no-edit || true
EOF
chmod +x .git/hooks/post-commit

# --- Permissions ---
chmod +x serversetup.sh

echo "=== Bootstrap Complete ==="
echo "Next steps:"
echo "  1. Edit .env with your real secrets"
echo "  2. Run: docker compose up -d"

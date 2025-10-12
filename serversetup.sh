#!/usr/bin/env bash
set -euo pipefail

# =========================
# Cloven_Tectum One-Click Bootstrap
# =========================
# Usage:
#   ./serversetup.sh              # generate files & compose UP
#   ./serversetup.sh --no-up      # generate files only
#   ./serversetup.sh --force      # overwrite existing files
#   ./serversetup.sh --purge      # remove volumes and rebuild clean
#   ./serversetup.sh --dry-run    # simulate the above
#
# Never gonna give you up. Never gonna let you down. 🖤

FORCE=false
NO_UP=false
PURGE=false
DRY_RUN=false

for a in "$@"; do
  case "$a" in
    --force) FORCE=true ;;
    --no-up) NO_UP=true ;;
    --purge) PURGE=true ;;
    --dry-run) DRY_RUN=true ;;
    *) echo "[ERROR] Unknown flag: $a"; exit 1 ;;
  esac
done

log()  { echo -e "[*] $*"; }
warn() { echo -e "[!] $*"; }
err()  { echo -e "[ERROR] $*" >&2; exit 1; }

# Docker Compose
if docker compose version >/dev/null 2>&1; then
  DOCKER_COMPOSE="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  DOCKER_COMPOSE="docker-compose"
else
  err "docker compose not found. Install Docker Compose plugin or docker-compose."
fi

# Check and shut down running containers from this project
if [[ "$DRY_RUN" == false ]]; then
  log "Checking for existing containers..."
  $DOCKER_COMPOSE down || true
fi

# Purge volumes if requested
if [[ "$PURGE" == true ]]; then
  log "Purging volumes..."
  if [[ "$DRY_RUN" == false ]]; then
    $DOCKER_COMPOSE down -v || true
  else
    log "[dry-run] Would run: $DOCKER_COMPOSE down -v"
  fi
fi

# Core paths
mkdir -p tectum_framework/{api_server,ollama,agents/{scraper,inserter}} logs assets .git/hooks

# Validate .env
if grep -q "changeme" .env 2>/dev/null; then
  warn "Insecure .env password detected — change DATABASE_PASS."
fi

# Git pre-commit to avoid bad commits
if [[ ! -f ".git/hooks/pre-commit" ]]; then
  cat <<'EOF' > .git/hooks/pre-commit
#!/bin/bash
if git diff --cached --name-only | grep -E '\.env|ollama_models|open-webui-data'; then
  echo "Pre-commit: Do not commit sensitive or runtime data."
  exit 1
fi
EOF
  chmod +x .git/hooks/pre-commit
  log "Added pre-commit hook."
fi

# Optional: Git + timestamp metadata
echo "Build: $(date -Iseconds)" > build_info.txt
git rev-parse HEAD >> build_info.txt 2>/dev/null || echo "(not in git)" >> build_info.txt

# Start Docker Compose (unless skipped)
if [[ "$NO_UP" == false ]]; then
  log "Building and starting containers..."
  if [[ "$DRY_RUN" == false ]]; then
    $DOCKER_COMPOSE up -d --build
  else
    log "[dry-run] Would run: $DOCKER_COMPOSE up -d --build"
  fi
fi

# Wait briefly then check API health
if [[ "$DRY_RUN" == false ]]; then
  sleep 3
  API_PORT=$(grep -E '^API_PORT=' .env | cut -d '=' -f2)
  WEBUI_PORT=$(grep -E '^WEBUI_PORT=' .env | cut -d '=' -f2)

  log "Checking API health..."
  curl -sf http://localhost:$API_PORT/health && echo "[✓] API is healthy" || echo "[X] API not responding"

  log "Checking /rickroll..."
  curl -s http://localhost:$API_PORT/rickroll | grep -q 'Never gonna let you down' && log "Sanity test passed." || warn "Rickroll sanity test failed."

  log "Checking WebUI: http://localhost:$WEBUI_PORT"

  # Ollama model check (example: gemma)
  if docker exec cloven_tectum_ollama ollama list | grep -q "gemma"; then
    log "Ollama model 'gemma' already available."
  else
    log "Pulling default model: gemma:2b"
    docker exec cloven_tectum_ollama ollama pull gemma:2b || warn "Model pull failed"
  fi

  log "Setup complete."
else
  log "Dry run complete. No changes made."
fi

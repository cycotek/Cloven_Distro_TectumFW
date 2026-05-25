#!/bin/bash

set -e

VERSION_FILE=".version"

function bump_version() {
    if [[ -f $VERSION_FILE ]]; then
        OLD=$(cat $VERSION_FILE)
    else
        OLD="0.2.0"
    fi
    IFS='.' read -r MAJOR MINOR PATCH <<< "$OLD"
    PATCH=$((PATCH + 1))
    NEW="$MAJOR.$MINOR.$PATCH"
    echo "$NEW" > $VERSION_FILE
    echo "[✓] Version bumped: $OLD → $NEW"
}

function ensure_env() {
    if [[ ! -f .env ]]; then
        echo "[+] Creating .env from .env.example"
        echo "[!] Edit .env and set DATABASE_PASS before using in production"
        cp .env.example .env
    else
        echo "[✓] .env already exists"
    fi
}

bump_version
ensure_env

echo "[✓] Starting containers..."
docker compose up -d --build

API_PORT=$(grep '^API_PORT' .env | cut -d= -f2 | tr -d ' ' || echo 8000)
echo ""
echo "[✓] Cloven Tectum is up."
echo "    API docs:  http://localhost:${API_PORT}/docs"
echo "    Models:    http://localhost:${API_PORT}/models"
echo "    Health:    http://localhost:${API_PORT}/health"

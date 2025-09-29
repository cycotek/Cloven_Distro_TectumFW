#!/usr/bin/env bash
set -e

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
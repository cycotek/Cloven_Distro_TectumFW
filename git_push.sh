#!/usr/bin/env bash
# git_push.sh — authenticated git push using credentials from .env
#
# Usage (from WSL2 terminal or Windows Git Bash):
#   bash git_push.sh
#   bash git_push.sh "your commit message here"
#
# Setup (one-time):
#   1. Generate a GitHub token at https://github.com/settings/tokens (scope: repo)
#   2. Add these two lines to your .env file:
#        GITHUB_USER=your_github_username
#        GITHUB_TOKEN=ghp_your_token_here
#   That's it — this script reads them at runtime, nothing is hardcoded.

set -euo pipefail
cd "$(dirname "$0")"

# ── Load .env ─────────────────────────────────────────────────────────────────
if [[ ! -f .env ]]; then
    echo "ERROR: .env not found. Copy .env.example to .env and fill in GITHUB_USER + GITHUB_TOKEN."
    exit 1
fi

# Export only GITHUB_USER and GITHUB_TOKEN from .env (safe — ignores other vars)
while IFS='=' read -r key value; do
    [[ "$key" =~ ^#.*$ || -z "$key" ]] && continue
    key="${key// /}"
    value="${value// /}"
    if [[ "$key" == "GITHUB_USER" || "$key" == "GITHUB_TOKEN" ]]; then
        export "$key=$value"
    fi
done < .env

if [[ -z "${GITHUB_USER:-}" || -z "${GITHUB_TOKEN:-}" ]]; then
    echo "ERROR: GITHUB_USER and GITHUB_TOKEN must be set in .env"
    echo "  Example:"
    echo "    GITHUB_USER=cycotek"
    echo "    GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx"
    exit 1
fi

# ── Fix stale index lock if present ───────────────────────────────────────────
if [[ -f .git/index.lock ]]; then
    echo "Removing stale .git/index.lock..."
    rm -f .git/index.lock
fi

# ── Stage any unstaged changes to tracked files, or accept explicit message ──
COMMIT_MSG="${1:-}"
if [[ -n "$(git status --porcelain)" ]]; then
    git add -A
    if [[ -z "$COMMIT_MSG" ]]; then
        # Auto-generate a message listing changed files
        CHANGED=$(git diff --cached --name-only | tr '\n' ' ')
        COMMIT_MSG="chore: update ${CHANGED}"
    fi
    echo "Committing: $COMMIT_MSG"
    git commit -m "$COMMIT_MSG"
else
    echo "Nothing new to commit — pushing existing HEAD."
fi

# ── Build authenticated remote URL (never stored in git config) ───────────────
REPO="github.com/cycotek/Cloven_Distro_TectumFW.git"
AUTH_URL="https://${GITHUB_USER}:${GITHUB_TOKEN}@${REPO}"

echo "Pushing to GitHub..."
git push "$AUTH_URL" main

echo ""
echo "Done. Latest commits:"
git log --oneline -5

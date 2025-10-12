#!/bin/bash
echo "[!] Stopping and cleaning up..."
docker compose down -v
echo "[!] Removing generated files..."
rm -rf tectum_framework docker-compose.yml README.md ABOUT.md .version
echo "[✓] Teardown complete."

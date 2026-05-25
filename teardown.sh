#!/bin/bash
echo "[!] Stopping containers and removing volumes..."
docker compose down -v
echo "[✓] Teardown complete. Source files preserved."

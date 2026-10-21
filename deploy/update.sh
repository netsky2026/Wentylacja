#!/usr/bin/env bash
# Aktualizacja do najnowszej wersji z GitHuba. Uruchom: sudo bash deploy/update.sh
set -euo pipefail
cd "$(dirname "$0")"
git -C .. pull
docker compose up -d --build
docker image prune -f >/dev/null
echo -e "\033[1;32m✔ Zaktualizowano. Dane zostały bez zmian.\033[0m"

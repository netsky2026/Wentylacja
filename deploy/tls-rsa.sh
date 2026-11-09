#!/usr/bin/env bash
# Przełącza certyfikat (Caddy + Mosquitto 8883) na RSA 2048 – zgodność ze sterownikami TLS 1.2.
# Uruchamiane automatycznie przez update.sh; można też ręcznie: sudo bash deploy/tls-rsa.sh
set -euo pipefail
cd "$(dirname "$0")"
DOMAIN=$(grep '^DOMAIN=' .env | cut -d= -f2- | tr -d '"' | tr -d "'")
KEY="/data/caddy/certificates/*/$DOMAIN/$DOMAIN.key"
if docker compose exec -T web sh -c "cat $KEY 2>/dev/null" | grep -q "EC PRIVATE KEY"; then
  echo "Zmiana certyfikatu na RSA dla $DOMAIN..."
  docker compose exec -T web sh -c "rm -rf /data/caddy/certificates/*/$DOMAIN"
  docker compose restart web >/dev/null
  for _ in $(seq 1 36); do
    sleep 5
    docker compose exec -T web sh -c "cat $KEY 2>/dev/null" | grep -q "RSA PRIVATE KEY" && break
  done
  docker compose exec -T web sh -c "cat $KEY 2>/dev/null" | grep -q "RSA PRIVATE KEY" \
    || { echo "UWAGA: nowy certyfikat RSA jeszcze nie gotowy – uruchom ponownie: sudo bash deploy/tls-rsa.sh"; exit 0; }
  echo "Certyfikat RSA gotowy."
fi
docker compose restart mosquitto >/dev/null
echo "Broker MQTT (8883) uruchomiony ponownie – TLS 1.2/1.3, certyfikat RSA."

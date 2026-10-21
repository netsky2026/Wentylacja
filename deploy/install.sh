#!/usr/bin/env bash
# Instalator "Marco Polo Wentylacja" dla Ubuntu 22.04/24.04. Uruchom: sudo bash deploy/install.sh
set -euo pipefail
cd "$(dirname "$0")"

G='\033[1;32m'; Y='\033[1;33m'; R='\033[1;31m'; N='\033[0m'
ok()   { echo -e "${G}✔ $*${N}"; }
info() { echo -e "${Y}➜ $*${N}"; }
die()  { echo -e "${R}✘ $*${N}"; exit 1; }

[ "$(id -u)" = 0 ] || die "Uruchom z sudo:  sudo bash $0"

info "Krok 1/6: instaluję potrzebne programy (to potrwa 1–3 minuty)…"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq git curl openssl ufw dnsutils >/dev/null
command -v docker >/dev/null || curl -fsSL https://get.docker.com | sh >/dev/null
systemctl enable --now docker >/dev/null
ok "Programy zainstalowane"

info "Krok 2/6: zapora sieciowa"
ufw allow OpenSSH >/dev/null; ufw allow 80/tcp >/dev/null; ufw allow 443/tcp >/dev/null; ufw allow 8883/tcp >/dev/null
ufw --force enable >/dev/null
ok "Otwarte porty: 22 (logowanie), 80/443 (strona), 8883 (sterowniki)"

if [ -f .env ]; then
  info "Plik .env już istnieje – używam istniejących ustawień."
  set -a; . ./.env; set +a
else
  info "Krok 3/6: kilka pytań"
  read -rp "Adres strony (domena, np. wentylacja.mojaferma.pl): " DOMAIN
  DOMAIN=$(echo "$DOMAIN" | sed -E 's#^https?://##; s#/.*$##' | tr 'A-Z' 'a-z')
  [ -n "$DOMAIN" ] || die "Nie podano domeny"
  read -rp "Twój e-mail (login administratora): " ADMIN_EMAIL
  [[ "$ADMIN_EMAIL" == *@*.* ]] || die "Niepoprawny e-mail"
  while true; do
    read -rsp "Hasło administratora (min. 8 znaków, bez znaku '): " ADMIN_PASSWORD; echo
    read -rsp "Powtórz hasło: " P2; echo
    [ "$ADMIN_PASSWORD" = "$P2" ] || { echo "Hasła różnią się, spróbuj jeszcze raz."; continue; }
    [ ${#ADMIN_PASSWORD} -ge 8 ] || { echo "Za krótkie hasło."; continue; }
    [[ "$ADMIN_PASSWORD" != *"'"* ]] || { echo "Hasło nie może zawierać znaku '."; continue; }
    break
  done
  MQTT_PREFIX=wentylacja
  MQTT_PASS=$(openssl rand -hex 24)
  cat > .env <<EOF
DOMAIN='$DOMAIN'
DB_NAME='wentylacja'
MQTT_PREFIX='$MQTT_PREFIX'
JWT_SECRET='$(openssl rand -hex 32)'
BROKER_SECRET='$(openssl rand 32 | base64 | tr '+/' '-_')'
ADMIN_EMAIL='$ADMIN_EMAIL'
ADMIN_PASSWORD='$ADMIN_PASSWORD'
MQTT_USER='admin'
MQTT_PASS='$MQTT_PASS'
SMTP_HOST=
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_FROM=
SMTP_USE_SSL=false
SMSAPI_TOKEN=
SMSAPI_FROM=Test
EOF
  chmod 600 .env
  ok "Ustawienia zapisane w $(pwd)/.env"
fi

info "Krok 4/6: sprawdzam, czy domena wskazuje na ten serwer"
MYIP=$(curl -4 -s https://api.ipify.org || true)
DNSIP=$(dig +short A "$DOMAIN" @1.1.1.1 | tail -1)
if [ "$MYIP" != "$DNSIP" ]; then
  echo -e "${R}Domena $DOMAIN wskazuje na: '${DNSIP:-brak}', a ten serwer ma IP: $MYIP${N}"
  echo "Ustaw rekord A domeny na $MYIP (instrukcja: INSTRUKCJA_PROSTA.md, krok 3) i odczekaj 10–30 min."
  read -rp "Kontynuować mimo to? (t/N): " A; [[ "$A" =~ ^[tT]$ ]] || exit 1
else
  ok "Domena $DOMAIN → $MYIP"
fi

info "Krok 5/6: buduję i uruchamiam aplikację (pierwszy raz 5–10 minut)…"
if ! docker compose run --rm --entrypoint "" mosquitto test -f /mosquitto/data/dynamic-security.json; then
  docker compose run --rm --entrypoint "" mosquitto \
    mosquitto_ctrl dynsec init /mosquitto/data/dynamic-security.json admin "$MQTT_PASS" >/dev/null
  NEW_BROKER=1
fi
docker compose up -d --build web backend mongo

info "Czekam na certyfikat HTTPS (do 3 minut)…"
for i in $(seq 1 36); do
  if docker compose exec -T web sh -c "ls /data/caddy/certificates/*/$DOMAIN/$DOMAIN.crt" >/dev/null 2>&1; then CERT=1; break; fi
  sleep 5
done
[ "${CERT:-}" = 1 ] || die "Brak certyfikatu. Sprawdź domenę (krok 4) i uruchom skrypt ponownie. Logi: docker compose logs web"
ok "Certyfikat HTTPS gotowy"

info "Krok 6/6: broker MQTT dla sterowników"
docker compose up -d mosquitto
sleep 5
if [ "${NEW_BROKER:-}" = 1 ]; then
  C="docker compose exec -T mosquitto mosquitto_ctrl -h localhost -p 1883 -u admin -P $MQTT_PASS dynsec"
  $C createRole gateway
  $C addRoleACL gateway publishClientSend "$MQTT_PREFIX/#" allow
  $C addRoleACL gateway publishClientReceive "$MQTT_PREFIX/#" allow
  $C addRoleACL gateway subscribePattern "$MQTT_PREFIX/#" allow
  $C addClientRole admin gateway
fi
docker compose restart backend >/dev/null

( crontab -l 2>/dev/null | grep -v wentylacja-backup ; \
  echo "0 3 * * * mkdir -p /opt/backup && cd $(pwd) && docker compose exec -T mongo mongodump --archive --gzip > /opt/backup/wentylacja-\$(date +\%F).gz # wentylacja-backup" ; \
  echo "0 4 * * 1 cd $(pwd) && docker compose restart mosquitto # wentylacja-backup" ; \
  echo "0 5 * * * find /opt/backup -name 'wentylacja-*.gz' -mtime +30 -delete # wentylacja-backup" ) | crontab -
ok "Codzienna kopia bazy: /opt/backup (30 dni)"

echo
echo -e "${G}==============================================${N}"
echo -e "${G}  GOTOWE!  Otwórz:  https://$DOMAIN${N}"
echo -e "${G}  Login:  $ADMIN_EMAIL  (hasło – to, które podałeś)${N}"
echo -e "${G}  Sterowniki łączą się z: $DOMAIN, port 8883, TLS${N}"
echo -e "${G}==============================================${N}"

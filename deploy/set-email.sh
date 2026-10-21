#!/usr/bin/env bash
# Ustawienie wysyłki maili z alarmami. Uruchom: sudo bash deploy/set-email.sh
set -euo pipefail
cd "$(dirname "$0")"
G='\033[1;32m'; R='\033[1;31m'; N='\033[0m'
[ "$(id -u)" = 0 ] || { echo "Uruchom z sudo:  sudo bash $0"; exit 1; }
[ -f .env ] || { echo -e "${R}Brak pliku .env – najpierw uruchom install.sh${N}"; exit 1; }

read -rp "Adres skrzynki, z której wychodzą alarmy (np. alarmy@marcopolo-wentylacja.pl): " FROM
[[ "$FROM" == *@*.* ]] || { echo -e "${R}Niepoprawny e-mail${N}"; exit 1; }
while true; do
  read -rsp "Hasło do tej skrzynki: " PASS; echo
  [ -n "$PASS" ] && [[ "$PASS" != *"'"* ]] && break
  echo "Hasło nie może być puste ani zawierać znaku '."
done
read -rp "Serwer SMTP [smtp.mail.ovh.net]: " HOST; HOST=${HOST:-smtp.mail.ovh.net}
read -rp "Port [465]: " PORT; PORT=${PORT:-465}
SSL=false; [ "$PORT" = 465 ] && SSL=true

grep -vE '^SMTP_(HOST|PORT|USERNAME|PASSWORD|FROM|USE_SSL)=' .env > .env.new || true
cat >> .env.new <<EOF
SMTP_HOST='$HOST'
SMTP_PORT='$PORT'
SMTP_USERNAME='$FROM'
SMTP_PASSWORD='$PASS'
SMTP_FROM='$FROM'
SMTP_USE_SSL='$SSL'
EOF
mv .env.new .env && chmod 600 .env
echo "Zapisano. Uruchamiam ponownie aplikację…"
docker compose up -d backend >/dev/null 2>&1
sleep 8

read -rp "Na jaki adres wysłać mail testowy? " TO
[[ "$TO" =~ ^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$ ]] || { echo -e "${R}Niepoprawny e-mail${N}"; exit 1; }
RES=$(docker compose exec -T backend python -c "import notify; print(notify.deliver('email', '$TO', 'Test – Marco Polo Wentylacja', 'To jest testowa wiadomość. Wysyłka alarmów działa.'))")
if [[ "$RES" == *"'sent'"* ]]; then
  echo -e "${G}✔ Wysłano! Sprawdź skrzynkę $TO (także folder SPAM).${N}"
else
  echo -e "${R}✘ Nie udało się: $RES${N}"
  echo "Sprawdź hasło do skrzynki. Możesz spróbować portu 587 – uruchom skrypt jeszcze raz."
fi

# Uruchomienie „Marco Polo Wentylacja” na własnym serwerze VPS

> **Początkujący:** użyj prostszej instrukcji `INSTRUKCJA_PROSTA.md` i automatycznego instalatora `install.sh`.
> Poniżej jest wersja ręczna dla zaawansowanych.

Instrukcja dla serwera z **Ubuntu 22.04 lub 24.04** (OVH, Hetzner, Contabo, home.pl itp.).
Wystarczy: 2 vCPU, 2–4 GB RAM, 40 GB dysku.

Na serwerze działa wszystko w kontenerach Docker:

| Usługa | Rola |
|---|---|
| `web` (Caddy) | strona + automatyczny certyfikat HTTPS (Let's Encrypt), przekazuje `/api` do backendu |
| `backend` | serwer aplikacji (FastAPI) |
| `mongo` | baza danych |
| `mosquitto` | **Twój prywatny broker MQTT** – port **8883 (TLS)** dla sterowników |

Każdy sterownik dodany w aplikacji dostaje automatycznie **własne konto w brokerze** z dostępem tylko do swoich tematów.

---

## 1. Domena
U swojego rejestratora domen dodaj rekord **A** wskazujący na adres IP serwera, np.:
```
wentylacja.twojadomena.pl  ->  51.68.xxx.xxx
```
Odczekaj kilka minut (sprawdzisz: `ping wentylacja.twojadomena.pl`).

## 2. Przygotowanie serwera (jednorazowo)
Zaloguj się na serwer (`ssh root@IP`) i wklej:
```bash
apt update && apt -y upgrade
curl -fsSL https://get.docker.com | sh
apt -y install git ufw
ufw allow OpenSSH && ufw allow 80 && ufw allow 443 && ufw allow 8883 && ufw --force enable
```

## 3. Pobranie aplikacji
W czacie Emergent kliknij **„Save to GitHub”**, a potem na serwerze:
```bash
git clone https://github.com/TWOJ_LOGIN/TWOJE_REPO.git /opt/wentylacja
cd /opt/wentylacja/deploy
cp env.example .env
```

## 4. Ustawienia (`.env`)
Wygeneruj tajne klucze:
```bash
python3 -c "import secrets;print(secrets.token_hex(32))"     # -> JWT_SECRET
docker run --rm python:3.11-slim sh -c "pip -q install cryptography && python -c 'from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())'"   # -> BROKER_SECRET
```
Otwórz plik: `nano .env` i uzupełnij:
- `DOMAIN` – Twoja domena (bez https://)
- `JWT_SECRET`, `BROKER_SECRET` – wygenerowane wyżej
- `ADMIN_EMAIL`, `ADMIN_PASSWORD` – Twoje konto głównego administratora
- `MQTT_PASS` – hasło administratora brokera (wymyśl mocne)
- `MQTT_PREFIX` – początek tematów MQTT (np. `wentylacja`)

Zapis: `Ctrl+O`, `Enter`, wyjście: `Ctrl+X`.

## 5. Broker MQTT – konto administratora (jednorazowo)
```bash
docker compose run --rm --entrypoint "" mosquitto \
  mosquitto_ctrl dynsec init /mosquitto/data/dynamic-security.json admin
```
Wpisz **to samo hasło co `MQTT_PASS`** (dwa razy).

## 6. Pierwsze uruchomienie
```bash
docker compose up -d --build web backend mongo
```
Poczekaj 1–2 minuty i otwórz `https://TWOJA_DOMENA` – powinna pojawić się strona logowania (Caddy w tym czasie pobierze certyfikat).
Teraz uruchom broker (korzysta z tego samego certyfikatu):
```bash
docker compose up -d mosquitto
```

## 7. Uprawnienia serwera aplikacji w brokerze (jednorazowo)
Zamień `HASLO` na `MQTT_PASS`, a `wentylacja` na Twój `MQTT_PREFIX`:
```bash
C="docker compose exec mosquitto mosquitto_ctrl -u admin -P HASLO dynsec"
$C createRole gateway
$C addRoleACL gateway publishClientSend 'wentylacja/#' allow
$C addRoleACL gateway publishClientReceive 'wentylacja/#' allow
$C addRoleACL gateway subscribePattern 'wentylacja/#' allow
$C addClientRole admin gateway
docker compose restart backend
```

## 8. Gotowe – pierwsze kroki w aplikacji
1. Zaloguj się kontem `ADMIN_EMAIL`.
2. **Ustawienia → Klienci i sterowniki**: dodaj klienta, potem sterownik (ID, liczba komór).
   Po dodaniu zobaczysz **login, hasło i tematy MQTT** – przekaż je instalatorowi bramki sterownika Fatek.
   Bramka łączy się z: `TWOJA_DOMENA`, port **8883**, **TLS włączony**.
3. Ikona palety przy kliencie: logo, nazwa, kolory i **link klienta** (`https://TWOJA_DOMENA/?klient=nazwa`) – wyślij go klientowi, zobaczy swoje logo przy logowaniu i może zainstalować aplikację na telefonie.
4. Do testów możesz zaznaczyć przy sterowniku **„Symulator”**.

---

## Powiadomienia o alarmach (e-mail / SMS) – opcjonalnie, w dowolnym momencie
Bez tych kluczy aplikacja działa normalnie, a powiadomienia są tylko zapisywane (status „brak kanału”).
W `nano .env` uzupełnij:
- **E-mail (SMTP)** – dane od Twojej poczty (np. home.pl, OVH, Gmail z hasłem aplikacji):
  `SMTP_HOST`, `SMTP_PORT` (587 lub 465), `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM` (adres nadawcy),
  `SMTP_USE_SSL=true` tylko dla portu 465.
- **SMS (SMSAPI.pl)** – załóż konto na smsapi.pl → *Tokeny API* → wygeneruj token z prawem wysyłki SMS:
  `SMSAPI_TOKEN=...`, `SMSAPI_FROM=Test` (albo zatwierdzone w SMSAPI pole nadawcy, np. `Ferma`).

Potem: `docker compose up -d backend` i w aplikacji **Ustawienia → Odbiorcy alarmów → Wyślij test**.
Status każdego powiadomienia (wysłano / błąd / brak kanału) widać pod „Ostatnie powiadomienia”.

---


## Aktualizacja aplikacji (po zmianach w Emergent)
W czacie Emergent: **„Save to GitHub”**, potem na serwerze:
```bash
cd /opt/wentylacja && git pull && cd deploy && docker compose up -d --build
```
Dane (baza, logo, konta brokera) zostają bez zmian.

## Kopia zapasowa bazy (zalecane codziennie)
```bash
mkdir -p /opt/backup
crontab -e
```
Dopisz linie:
```
0 3 * * * cd /opt/wentylacja/deploy && docker compose exec -T mongo mongodump --archive --gzip > /opt/backup/wentylacja-$(date +\%F).gz
0 4 * * 1 cd /opt/wentylacja/deploy && docker compose restart mosquitto
```
(druga linia raz w tygodniu odświeża certyfikat TLS w brokerze)

Przywracanie: `docker compose exec -T mongo mongorestore --archive --gzip --drop < /opt/backup/PLIK.gz`

## Format danych dla bramki sterownika
Bramka **wysyła** co 1–5 s na temat `PREFIX/ID_STEROWNIKA/state` (JSON):
```json
{"chambers":[{"id":0,"temp":21.4,"setpoint":20,"humidity":66,"co2":1450,"on":true,"heating":false,
  "mode":"auto","curtain_left":35,"curtain_right":38,"chimney":40}],
 "plant":{"power_kw":3.2,"power_kwh":1520.4,"water_lpm":2.1,"water_total_l":45210}}
```
- `chambers` – dokładnie tyle komór, ile ustawiono przy sterowniku (`id` od 0).
- `curtain_left/right`, `chimney` – **% otwarcia** (aplikacja pokazuje kurtyny jako % zamknięcia).
- Opcjonalnie w każdej komorze: `water_total_l` – **stan wodomierza komory** (litry, licznik narastający) i `water_lpm` – przepływ l/min.
  `plant.power_kwh` – stan licznika prądu (kWh, narastający). Z tych liczników aplikacja liczy zużycie dzienne, w okresie chowu i w dowolnym zakresie dat.

Bramka **odbiera** komendy z tematu `PREFIX/ID_STEROWNIKA/command`:
```json
{"type":"set_setpoint","chamber":0,"value":21.5}
{"type":"set_mode","chamber":0,"value":"manual"}
{"type":"set_vent","chamber":0,"value":{"curtain_left":60,"chimney":30}}
```

## Problemy
- Logi: `docker compose logs -f backend` (lub `web`, `mosquitto`).
- Strona nie działa → sprawdź rekord DNS i czy porty 80/443 są otwarte.
- Broker się restartuje → certyfikat jeszcze nie pobrany: najpierw musi działać strona (krok 6), potem `docker compose restart mosquitto`.
- Broker szuka certyfikatu w katalogu Caddy (`/caddy/caddy/certificates/<wystawca>/<domena>`) – działa zarówno z Let's Encrypt, jak i ZeroSSL.

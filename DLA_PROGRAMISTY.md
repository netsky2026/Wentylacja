# Marco Polo Wentylacja – dokumentacja dla programisty

System do zdalnego podglądu i sterowania wentylacją komór w chlewniach. Sterowniki **Fatek PLC (seria M)** łączą się przez **MQTT (TLS)**. Aplikacja jest **multi-tenant**: superadmin (Marco Polo) zarządza klientami (fermami), ich sterownikami i użytkownikami.

Produkcja: `https://marcopolo-wentylacja.pl` (VPS OVH, Docker Compose, katalog `/opt/wentylacja`).

---

## 1. Stos technologiczny

| Warstwa | Technologia |
|---|---|
| Backend | Python 3.11, FastAPI, Motor (MongoDB async), paho-mqtt, openpyxl, Pillow |
| Frontend | React (CRA + craco), TailwindCSS, shadcn/ui, lucide-react, recharts, sonner, axios |
| Baza | MongoDB 7 |
| Broker MQTT | Eclipse Mosquitto 2, dynamic-security plugin, TLS na porcie 8883 |
| Reverse proxy / HTTPS | Caddy (automatyczne certyfikaty Let's Encrypt) |
| Powiadomienia | SMTP OVH (e-mail), SMSAPI.pl (SMS, wymaga tokenu) |
| PWA | `frontend/public/manifest.json`, `sw.js`, ikony |

## 2. Struktura repozytorium

```
backend/
  server.py        # cały API, WebSocket, MQTT, symulator, raporty Excel, zadania w tle
  auth.py          # logowanie JWT (cookies httpOnly + CSRF), role, użytkownicy
  notify.py        # wysyłka e-mail (SMTP) i SMS (SMSAPI.pl)
  assets/          # marco-polo.png – domyślne logo w raportach Excel
  tests/           # testy pytest (test_iterationNN_*.py) – uderzają w działające API
frontend/
  src/App.js       # routing stanów: strona powitalna / logowanie / panel
  src/api.js       # axios + odświeżanie sesji, URL backendu z REACT_APP_BACKEND_URL
  src/i18n.js      # wszystkie teksty PL / EN
  src/index.css    # motywy kolorystyczne (CSS variables, [data-theme="..."])
  src/components/  # widoki i karty (OverviewView, ChamberScreen, DataView, SettingsView, ...)
  public/          # ikony PWA, logo marco-polo.png, welcome.jpg, sw.js
deploy/
  docker-compose.yml, backend.Dockerfile, frontend.Dockerfile, Caddyfile
  mosquitto/mosquitto.conf.tpl
  install.sh       # pierwsza instalacja na czystym VPS (Ubuntu)
  update.sh        # aktualizacja: git pull + docker compose up -d --build
  set-email.sh     # konfiguracja SMTP w deploy/.env
  env.example      # wzór pliku deploy/.env
  requirements.prod.txt, frontend-yarn-lock.txt
memory/PRD.md      # lista funkcji i historia zmian
```

## 3. Uruchomienie lokalne

Wymagania: Python 3.11, Node 18+ z Yarn, MongoDB, opcjonalnie Mosquitto.

**Backend**
```bash
cd backend
pip install -r requirements.txt
# plik backend/.env, np.:
# MONGO_URL=mongodb://localhost:27017
# DB_NAME=wentylacja
# JWT_SECRET=<losowy 64 znaki>
# BROKER_SECRET=<klucz Fernet: python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())">
# ADMIN_EMAIL=admin@chlewnia.pl
# ADMIN_PASSWORD=<hasło>
# MQTT_PREFIX=wentylacja
# FRONTEND_URL=http://localhost:3000
# LOGO_DIR=./data/logos
# (opcjonalnie) MQTT_USER, MQTT_PASS, MQTT_DYNSEC, SMTP_*, SMSAPI_*
uvicorn server:app --host 0.0.0.0 --port 8001 --reload
```
Przy starcie tworzy się konto superadmina z `ADMIN_EMAIL` / `ADMIN_PASSWORD` oraz indeksy w bazie.

**Frontend**
```bash
cd frontend
# frontend/.env: REACT_APP_BACKEND_URL=http://localhost:8001
yarn install
yarn start
```
Używaj **yarn**, nie npm. Wszystkie ścieżki API mają prefiks `/api`.

**Testy**
```bash
cd backend && pytest tests/ -q     # testy wymagają działającego backendu i danych testowych
```

## 4. Zmienne środowiskowe (produkcja: `deploy/.env`, NIE ma go w repo)

| Zmienna | Opis |
|---|---|
| `DOMAIN` | domena, np. `marcopolo-wentylacja.pl` |
| `DB_NAME` | nazwa bazy MongoDB |
| `JWT_SECRET` | sekret do podpisywania tokenów sesji |
| `BROKER_SECRET` | klucz Fernet; szyfruje hasła MQTT zapisane w bazie |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | konto superadmina tworzone przy starcie |
| `MQTT_PREFIX` | prefiks tematów MQTT |
| `MQTT_USER`, `MQTT_PASS` | konto admina Mosquitto (używane przez backend i dynamic-security) |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_USE_SSL` | poczta (OVH) |
| `SMSAPI_TOKEN`, `SMSAPI_FROM` | SMS przez SMSAPI.pl (puste = SMS wyłączone) |

`docker-compose.yml` ustawia dodatkowo: `MONGO_URL`, `MQTT_HOST=mosquitto`, `MQTT_PORT=1883`, `MQTT_DYNSEC=1`, `LOGO_DIR=/data/logos`, `FRONTEND_URL`.

## 5. Role i uwierzytelnianie

- Role (rosnąco): `viewer` → `operator` → `admin` → `superadmin` (`auth.py`, `ROLES`, dekorator `require(role)`).
  - **viewer** – podgląd; **operator** – sterowanie, wstawienia (chowy); **admin** – ustawienia swojej fermy, użytkownicy, stawki, raporty; **superadmin** – wszyscy klienci, sterowniki, broker, strona główna.
- Logowanie: `POST /api/auth/login`. Tokeny JWT w ciasteczkach httpOnly. Każde żądanie zmieniające dane wymaga nagłówka `X-CSRF-Token` z wartością ciasteczka `csrf`. Blokada konta po wielu nieudanych próbach (`login_attempts`).
- Użytkownik klienta ma `client_id`; superadmin `client_id = null` i przekazuje `?client_id=` w endpointach fermy (`client_scope()`).

## 6. MQTT – komunikacja ze sterownikiem

- Każdy sterownik (`devices`) ma własne konto w Mosquitto (dynamic-security). Dane logowania: `GET /api/devices/{id}/credentials` (superadmin).
- Tematy:
  - stan (PLC → serwer): `{MQTT_PREFIX}/{device_id}/state`
  - polecenia (serwer → PLC): `{MQTT_PREFIX}/{device_id}/command`
- Format stanu (JSON), walidowany w `sanitize_state()`:
```json
{
  "model": "Fatek FBs-M",
  "chambers": [
    {"id": 0, "on": true, "heating": false, "mode": "auto",
     "temp": 21.5, "setpoint": 22, "humidity": 65, "co2": 1200,
     "curtain_left": 40, "curtain_right": 40, "chimney": 30,
     "water_lpm": 3.2, "water_total_l": 15432.0,
     "manual": {"curtain_left": 50, "curtain_right": 50, "chimney": 20}}
  ],
  "plant": {"power_kw": 4.1, "power_kwh": 12345.6, "water_lpm": 20.0, "water_total_l": 99999.0}
}
```
  Liczba elementów `chambers` musi się zgadzać z liczbą komór sterownika (id od 0). `water_total_l` i `power_kwh` to **liczniki narastające**. Serwer liczy z nich dzienne przyrosty (`accumulate_meters` → kolekcja `meter_daily`).
- Polecenia (JSON): `{"type": "set_setpoint" | "set_mode" | "set_vent", "chamber": 0, "value": ...}`
  - `set_setpoint`: liczba 5–35; `set_mode`: `"auto"`/`"manual"`; `set_vent`: `{"curtain_left": 0-100, "curtain_right": 0-100, "chimney": 0-100}`.
- Test połączenia: `POST /api/devices/{id}/ping` wysyła `{"type":"ping","request_id"}`; sterownik odsyła `"ack": request_id` w stanie. Podgląd: `GET /api/devices/{id}/mqtt-debug` (ostatnia surowa wiadomość, powód odrzucenia – `state_error`, ostatnie polecenie, ping) – dane tylko w pamięci.
- Sterowniki z flagą `simulated` są symulowane w backendzie (klasa symulatora w `server.py`), do testów bez PLC.
- Codziennie o ustawionej godzinie (domyślnie 00:00, osobno dla każdej fermy) komory w trybie ręcznym wracają do AUTO (`midnight_auto`, `reset_manual_to_auto`).

## 7. Zadania w tle (start w `lifespan` w `server.py`)

- `history_sampler` – co 15 s zapisuje historię pomiarów (`plc_history`, `plc_plant_history`).
- `alarm_notifier` – alarmy temperatury i CO₂ → e-mail/SMS do odbiorców (`alarm_settings`).
- `conn_monitor` – co 10 s: zdarzenia offline/online (kolekcja `conn_state`), alarm po `alarm_settings.offline_min` (domyślnie 5 min) do odbiorców klienta + `ADMIN_EMAIL`, wiadomość o przywróceniu.
- `ws_revalidator` – zamyka sesje WebSocket usuniętych lub zmienionych użytkowników.
- `midnight_auto` – powrót do AUTO oraz `monthly_tick`, czyli raport miesięczny 1. dnia miesiąca o 6:00 (Excel w załączniku do adminów klienta).

## 8. Baza danych (MongoDB) – kolekcje

| Kolekcja | Zawartość |
|---|---|
| `users` | email, password_hash (bcrypt), role, client_id, theme |
| `clients` | display_name, slug, theme, logo_path/logo_version, auto_return, monthly_report, rates {kwh, m3} |
| `devices` | device_id, client_id, nazwa, liczba komór, chamber_names, simulated |
| `broker_config` | ustawienia brokera (host, port, tls, prefix, zaszyfrowane hasło) |
| `plc_history`, `plc_plant_history` | historia pomiarów komór / całej chlewni |
| `meter_daily`, `meter_last` | dzienne zużycie (kWh, woda per komora) i ostatnie stany liczników |
| `cycles` | wstawienia (rzuty): device_id, chamber, start, end, animals, started_by, ended_by |
| `chamber_thresholds`, `device_thresholds` | progi alarmowe |
| `alarm_settings`, `alarm_state`, `alarm_notifications` | odbiorcy alarmów i historia wysyłek |
| `plc_events` | dziennik zdarzeń |
| `monthly_reports` | znaczniki wysłanych raportów miesięcznych |
| `site_settings` | strona główna Marco Polo: phone, email, address, website, logo |
| `contact_requests` | limit formularza kontaktowego (TTL 1 h) |
| `login_attempts` | blokada logowania (TTL) |

## 9. Najważniejsze endpointy (`/api/...`)

- Auth: `POST auth/login`, `auth/logout`, `auth/refresh`, `GET auth/me`, `PUT auth/password`, `PUT auth/preferences`, `GET/POST/DELETE users`
- Klienci i sterowniki: `GET/POST/PATCH/DELETE clients`, `clients/{id}/logo`, `GET/POST/PATCH/DELETE devices`, `devices/{id}/credentials`, `PUT broker`
- Sterowanie: `POST devices/{id}/command`, progi `devices/{id}/thresholds`, nazwy komór `PUT devices/{id}/chambers/{n}/name`
- Dane: `devices/{id}/history`, `usage/daily`, `usage/range` (+ `/xlsx`, `/csv`), `history/xlsx`, `history/csv`
- Chowy: `GET devices/{id}/cycles?chamber=`, `POST devices/{id}/chambers/{n}/cycles`, `POST devices/{id}/cycles/{cid}/end`, `GET devices/{id}/cycles/export?fmt=xlsx|csv`
- Ustawienia fermy: `auto-return`, `monthly-report` (+ `/send`), `rates`, `alarm-settings` (+ `/test`)
- Publiczne: `public/site`, `public/site/logo`, `public/contact`, `public/branding/{slug}`, `public/logo/{slug}`, `public/manifest[/{slug}]`
- Strona główna (superadmin): `PUT site`, `POST/DELETE site/logo`
- WebSocket na żywo: `/api/ws`

## 10. Logika biznesowa – ważne szczegóły

- **Koszt rzutu w komorze** (`cycle_view`, `chamber_kwh`): woda liczona z licznika komory. Prąd jest mierzony tylko dla całej chlewni, więc kWh z każdego dnia dzielone jest po równo na komory, w których tego dnia trwa rzut. Koszt = zużycie × stawki klienta (`clients.rates`).
- **Raporty Excel** (`xlsx_bytes`): w nagłówku logo klienta (`client_logo`), a gdy klient go nie ma – logo Marco Polo (`backend/assets/marco-polo.png`). Zostawiane jest 5 wierszy na logo, nagłówek tabeli jest w wierszu 6.
- **Branding**: link `/?klient=<slug>` (kod QR) zapamiętuje klienta i pokazuje jego ekran logowania w jego kolorze. Zwykły adres `/` zawsze pokazuje zieloną stronę główną Marco Polo.
- **Motywy**: `frontend/src/index.css`, atrybut `data-theme` na `<html>`. Motyw użytkownika ma pierwszeństwo przed motywem klienta.
- **PDF dla technika** (`techsheet.py`, reportlab + czcionki DejaVu w `backend/assets/fonts`): `GET /api/devices/{id}/techsheet.pdf` (superadmin, bez hasła).
- **Logo** są zapisywane na dysku w `LOGO_DIR` (wolumen Docker `logos`).
- Czas lokalny: `Europe/Warsaw` (`local_day()`).

## 11. Wdrożenie i serwer

- Pierwsza instalacja: `sudo git clone <repo> /opt/wentylacja && sudo bash /opt/wentylacja/deploy/install.sh`
- Aktualizacja: `sudo bash /opt/wentylacja/deploy/update.sh` (robi `git pull` i przebudowuje kontenery; dane zostają).
- Podgląd: `cd /opt/wentylacja/deploy && sudo docker compose ps` oraz `sudo docker compose logs --tail 100 backend web mosquitto`
- Porty: 80/443 (Caddy), 8883 (MQTT TLS dla sterowników). Certyfikat TLS Mosquitto jest kopiowany z Caddy przy starcie kontenera; restart Mosquitto raz w tygodniu (cron).
- **Kopie zapasowe**: codziennie o 3:00 `mongodump` do `/opt/backup` (30 dni). Przywracanie:
  `cd /opt/wentylacja/deploy && sudo docker compose exec -T mongo mongorestore --archive --gzip --drop < /opt/backup/wentylacja-RRRR-MM-DD.gz`
- Zmiany zależności: backend – dopisz pakiet do `backend/requirements.txt` **i** `deploy/requirements.prod.txt`; frontend – `yarn add` i skopiuj `frontend/yarn.lock` do `deploy/frontend-yarn-lock.txt`.

## 12. Do zrobienia / znane tematy

- **SMS**: kod SMSAPI.pl gotowy, potrzebny `SMSAPI_TOKEN` w `deploy/.env`.
- **Refaktor `server.py`** (~1900 linii): warto podzielić na routery (`devices`, `reports`, `cycles`, `site`, `mqtt`).
- `cycle_ctx` wczytuje całą historię `meter_daily` sterownika; przy dużej historii warto zawęzić do zakresu dat rzutów.
- Formularz kontaktowy: limit 3 wiadomości na IP na godzinę i 30 globalnie; IP z ostatniego wpisu `X-Forwarded-For` (Caddy).

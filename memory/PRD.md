# Chłodnia MQTT — zarządzanie 3 komorami (Fatek PLC)

## Problem statement
"aplikacja mqt do sterownik aplc fatek" → aplikacja mobilna do zarządzania 3 komorami chłodni.
Ekran główny: 3 komory z odczytami czujników temperatura / wilgotność / CO₂.
Dane szczegółowe i ustawienia w osobnej zakładce. Prosty, mobilny interfejs.

## User choices
- Broker: HiveMQ public (broker.hivemq.com:1883)
- Hardware: brak — symulowany sterownik Fatek (chłodnia)
- Język: PL + EN
- UI: mobilny, mało danych na głównym ekranie

## Architecture
Symulator chłodni (własny klient MQTT) ⇄ HiveMQ ⇄ FastAPI gateway ⇄ React (WS+HTTP).
- device_id: `chlodnia-01`, prefix `emgt-fatek-7f3a9c`
- Temat stanu `{prefix}/chlodnia-01/state`, komend `{prefix}/chlodnia-01/command`
- Mongo: `plc_states`, `plc_events`; WebSocket `/api/ws`

## Model komory
temp, setpoint, humidity, co2, on, cooling, compressor, defrost, door_open, alarm.
Termostat z histerezą, auto-chłodzenie, ręczne rozmrażanie, alarm gdy temp > nastawa+5°C.

## Komendy
- set_setpoint(chamber, °C), chamber_power(chamber, bool), defrost(chamber, bool)

## Implemented (2026-10-20)
- Backend: symulator 3 komór z czujnikami temp/wilgotność/CO₂, pełny round-trip MQTT (zweryfikowany)
- Frontend mobilny: zakładka Komory (3 karty: 3 czujniki + status + nastawa +/- + wł/wył + rozmroź), zakładka Dane (tabela surowa, symulator, ustawienia brokera, dziennik zdarzeń), przełącznik PL/EN, pasek połączenia
- Alarm wizualny na karcie komory + wpis w dzienniku

## Backlog
- P1: wykresy historii (temp/wilgotność/CO₂) w zakładce Dane
- P1: edytowalne nastawy progów alarmu / wilgotności
- P2: autoryzacja, broker TLS produkcyjny, powiadomienia push o alarmach

## 2026-06 Update (Piggery main screen)
- Main screen refactored to piggery: full-width chamber tiles (temp, humidity, CO2), curtains as windows with roller blinds (value = % closed, 100 = closed; backend sends % open, UI shows 100-open), chimney as circular gauge, heating indicator.
- Plant tile at bottom: power kW + kWh total, water l/min + m3 total.
- Removed cold-store leftovers (defrost/cooling/door). Simulator humidity/CO2 made mean-reverting.
- Next: Dane tab (history charts for new metrics, thresholds UI, push notifications), testing agent run.

## 2026-06 Update 2 (Navigation + Dane + Ustawienia)
- Bottom nav: Komory | Dane | Ustawienia; top chamber switch (Komora 1/2/3); each chamber has its own screen.
- Dane: plant tile (power/water), history charts (temp, humidity, CO2, curtains % closed + chimney, plant power/water), event log.
- Ustawienia: per-chamber setpoint +/-, alarm thresholds save, notifications, simulator, broker info.
- Backend: history stores curtains/chimney + plant history; alarm event fires on threshold change; command validation (chamber 0-2, numeric setpoint).
- Tested: iteration_2, iteration_3 (100%).
- Backlog: manual curtain/chimney control, daily consumption chart, CSV export.

## 2026-06 Update 3
- Manual ventilation: per-chamber AUTO/RĘCZNY (set_mode), sliders (set_vent; curtains in UI as % closed, protocol % open); simulator keeps `manual` targets.
- Daily usage 7 days (GET /api/usage/daily) bar charts; CSV export (GET /api/history/csv?chamber&hours, ';' + BOM, Europe/Warsaw time).
- Broker settings form (PUT /api/broker: host, port, user, password, TLS, prefix, device_id), saved in Mongo broker_config, reconnects gateway+simulator.
- Online window 10s. Tested iteration_4 (backend 42/42, frontend 100%).
- Backlog: PWA (add to home screen), encrypt broker password, CSV export of plant usage.

## 2026-06 Update 4 (PWA)
- Installable PWA "Marco Polo Wentylacja": manifest (standalone, id /), icons (green pig on dark bg) 192/512/maskable/apple-touch, sw.js (navigation network-first, cache mpw-v4; API/WS untouched), apple meta tags, safe-area padding, InstallCard in Ustawienia, logo in header.
- Tested iteration_5 (frontend 100%).
- Production TODO: real Fatek via Modbus→MQTT gateway, private broker with TLS, app login, SMS/e-mail alarms, deploy (stable URL), native store app via Deploy → "Add Mobile App".

## 2026-06 Update 5 (Security hardening after audit)
- JWT cookie auth (auth.py): bcrypt, access 15 min + refresh 30 d, token version revoked on password change, per-account lockout (5/15 min, TTL index), roles viewer/operator/admin, admin user management, password change. Admin seeded from .env.
- All /api data/control endpoints + WS require login; origin guard (Origin == FRONTEND_URL or Origin host == Host); CORS = FRONTEND_URL.
- Broker: SSRF block (host must resolve to public IP), password Fernet-encrypted (BROKER_SECRET).
- MQTT: only exact state topic, strict sanitize (exactly chambers 0..2, finite numbers); CSV cell escaping; events/history limits clamped.
- Tested iteration_6/7. Known accepted limits: lockout can be triggered on a known email (15-min DoS), DNS-rebinding TOCTOU on admin-only broker change, public HiveMQ broker unauthenticated until user sets a private broker.

## 2026-06 Update 6
- Alarm notifications (MOCKED delivery, provider TBD by user): admin recipients list (email/SMS) in Ustawienia, notify on alarm start, reminder every 30 min, end-of-alarm notice; state persisted (alarm_state); stored in alarm_notifications; test send.
- Action history: events carry meta.user; Dane event log shows user + filters (Wszystkie/Działania/Alarmy).
- Green accent theme (#34A56A).
- Tested iteration_8/9 (100%).
- Next: connect real e-mail/SMS provider (Resend/Twilio), deploy when user decides.

## 2026-06 Update 7 (Multi-tenant)
- Clients -> PLC devices (1..n per client) -> chambers (1..10 per device). Collections: clients, devices{device_id,client_id,name,chambers,simulated,mqtt_username,mqtt_password_enc}, device_thresholds, history/plant/events with device_id(+client_id).
- Topics {prefix}/{device_id}/state|command on one shared broker; per-device MQTT credentials generated (to configure on broker ACL + PLC gateway).
- Roles: superadmin (manages clients/devices/broker), client admin (own users + alarm recipients), operator, viewer. WS broadcasts filtered by client.
- Simulator per device (simulated flag). Legacy data migrated to client "Marco Polo"/device chlodnia-01.
- API now device-scoped: /api/devices, /api/devices/{id}/command|thresholds|history|history/csv|usage/daily, /api/events?device_id, /api/alarm-settings?client_id, /api/clients.

## 2026-06 Update 8 (Themes & client branding)
- 4 themes via CSS vars on html[data-theme]: green (default), light (sunlight), blue, amber. Effective = user.theme || client.theme || green.
- Client branding (superadmin, Fleet card → palette): display_name, default theme, logo (Emergent Object Storage, resized 256px PNG; GET /api/clients/{id}/logo auth-scoped). /api/branding, PUT /api/auth/preferences.
- Tested iteration_12/13. Note: storage has no delete API → replaced logos are orphaned (tiny).
- VPS note: object storage uses EMERGENT_LLM_KEY; on own VPS swap to local disk/S3.

## 2026-06 Update 9
- Overview tab (Przegląd) for users with >1 device: all controllers, alarms first, mini chamber cells; tap opens device.
- Client link /?klient=<slug>: public branding/logo/manifest endpoints (/api/public/*), login screen + PWA icon/name per client; slug editor in BrandEditor.
- VPS package /app/deploy: docker-compose (Caddy+backend+Mongo+Mosquitto dynsec), Dockerfiles, Caddyfile, mosquitto.conf.tpl, .env.example, DEPLOY_VPS.md (PL). Backend: MQTT_DYNSEC=1 auto-provisions per-device broker accounts/ACL; LOGO_DIR=local logo storage; MQTT_USER/MQTT_PASS env.
- Tested iteration_14 (backend 34/34, frontend 100%); deploy files statically reviewed only (not run). Production yarn build verified.
- Pending: Resend e-mail (needs API key).

## 2026-06 update
- Removed Emergent Object Storage dependency: logos always stored on local disk (LOGO_DIR env, required; preview: /app/backend/data/logos, VPS: docker volume /data/logos). Existing logo migrated.
- Real alarm delivery: backend/notify.py — e-mail via SMTP (SMTP_HOST/PORT/USERNAME/PASSWORD/FROM/USE_SSL), SMS via SMSAPI.pl (SMSAPI_TOKEN/SMSAPI_FROM). Keys optional; missing channel => status "not_configured". Per-notification status sent/failed/not_configured shown in UI. Docs in deploy/DEPLOY_VPS.md, keys in deploy/.env.example.
- Light theme contrast: --warn-text/--warn-bg/--warn-border vars; RĘCZNY badge as pill; alarm banner uses theme vars.
- Stale test_auth_security.py already absent.
## Backlog
- P1: User enters real SMTP/SMSAPI keys and tests delivery
- P2: SMSAPI delivery callbacks, per-client alarm sender name
- 2026-06: deploy/install.sh (one-command Ubuntu installer: docker, ufw, .env generation, DNS check, dynsec init w/ password arg, cert wait, ACL, backup cron), deploy/update.sh, deploy/INSTRUKCJA_PROSTA.md (layman guide: OVH VPS, domain, DNS A, GitHub token, SSH). Not executed end-to-end (no Docker in preview) — user to run on VPS.
- 2026-06: WelcomeScreen landing (/ for guests without brand_slug; ?klient= skips to login), login back button, GET /api/public/site + PUT /api/site (superadmin contact phone/email, SiteCard in Settings), hero /public/welcome.jpg
- 2026-06: Platform (site) logo upload (POST/DELETE /api/site/logo, GET /api/public/site/logo, /api/public/manifest; client manifest falls back to site logo), QR poster dialog per client (qrcode lib, QrDialog.jsx), welcome forces green theme. Tested iteration_15 (100%). User VPS IP 51.222.200.183 (OVH Beauharnois, Canada).
- 2026-06: QR poster now includes 4-step install instructions (PL/EN) for printing. User staying with Canada VPS.
- LEARNING: platform git does NOT commit frontend/yarn.lock -> copy kept at deploy/frontend-yarn-lock.txt (re-copy after any yarn add!). Backend prod deps: deploy/requirements.prod.txt
- 2026-06: PRODUCTION LIVE on user's OVH VPS (Canada) https://marcopolo-wentylacja.pl (IP 51.222.200.183), repo github.com/netsky2026/wentylacja, installed at /opt/wentylacja via deploy/install.sh. HTTPS + MQTT TLS 8883 verified (Let's Encrypt). Updates: Save to GitHub -> on VPS: cd /opt/wentylacja && sudo git pull && sudo bash deploy/update.sh
- 2026-06: auto client slug (unique_slug, migrate_slugs, unique partial index), QR button in client row (client-qr-<id>), install.sh broker ACL now idempotent+verified (fixes offline device after failed first install). Tested iteration_17.
- 2026-06: deploy/set-email.sh (interactive SMTP setup in .env + restart + test send). OVH mail SMTP: smtp.mail.ovh.net:465 SSL, user = full address.

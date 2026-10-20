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

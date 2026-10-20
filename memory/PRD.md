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

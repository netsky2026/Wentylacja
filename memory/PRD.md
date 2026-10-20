# Fatek PLC — MQTT Panel

## Problem statement
"aplikacja mqt do sterownik aplc fatek" — web app to control a Fatek PLC over MQTT.
Controller speaks MQTT, connects through a broker on a server, backend server talks to the app.

## User choices
- Broker: HiveMQ public test broker (broker.hivemq.com:1883)
- Hardware: none — use a simulated Fatek FBs PLC
- Language: bilingual Polish + English (switcher)

## Architecture
Simulated Fatek FBs PLC (own MQTT client) ⇄ HiveMQ broker ⇄ FastAPI gateway (own MQTT client) ⇄ React app (WS + HTTP).
- Topic prefix: `emgt-fatek-7f3a9c` (MQTT_PREFIX in backend/.env)
- State topic: `{prefix}/plc-01/state`, Command topic: `{prefix}/plc-01/command`
- MongoDB: `plc_states` (state history), `plc_events` (event log)
- WebSocket: `/api/ws` pushes live state + events

## Implemented (2026-10-20)
- Backend gateway + full MQTT round-trip through HiveMQ (verified)
- Simulated Fatek PLC: inputs X (fluctuating sensors), outputs Y, relays M, data registers R, run/stop
- REST: /api/health, /api/config, /api/device/{id}/state, /api/device/{id}/command, /api/events, /api/simulator/toggle
- React dashboard: status chips, PLC run/stop, X/Y/M grids, R register read/write, live event log with filters, broker settings, PL/EN switch, simulator toggle
- Dark industrial theme (Barlow Condensed + JetBrains Mono)

## Backlog / Next
- P1: Multiple devices, history charts (recharts) for registers
- P1: Editable broker settings from UI (reconnect)
- P2: Auth, TLS broker for production, alarm thresholds on registers

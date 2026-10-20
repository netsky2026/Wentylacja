"""
Fatek PLC MQTT gateway + cold-store (chłodnia) simulator with 3 chambers.

Architecture:
  Simulated Fatek FBs PLC (cold store) <--MQTT--> HiveMQ broker <--MQTT--> FastAPI backend <--WS/HTTP--> React app

The simulator models a cold store with 3 chambers (komory). Each chamber has a
temperature, a setpoint, a thermostat (automatic cooling with hysteresis), manual
defrost, a door sensor and an alarm. It owns its own MQTT client (acts as the device),
publishes chamber state and consumes commands. The backend owns a separate MQTT client
that subscribes to state and publishes user commands, so the whole round-trip travels
through the public broker just like a real Fatek controller.
"""
from fastapi import FastAPI, APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import json
import time
import asyncio
import logging
import threading
import random
import uuid
from pathlib import Path
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Optional

import paho.mqtt.client as mqtt
from pydantic import BaseModel, Field

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("fatek")

MONGO_URL = os.environ['MONGO_URL']
DB_NAME = os.environ['DB_NAME']
MQTT_HOST = os.environ.get('MQTT_HOST', 'broker.hivemq.com')
MQTT_PORT = int(os.environ.get('MQTT_PORT', '1883'))
MQTT_PREFIX = os.environ.get('MQTT_PREFIX', 'emgt-fatek-7f3a9c').strip('/')

DEVICE_ID = "chlodnia-01"

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def state_topic(device_id: str) -> str:
    return f"{MQTT_PREFIX}/{device_id}/state"


def command_topic(device_id: str) -> str:
    return f"{MQTT_PREFIX}/{device_id}/command"


# ============================================================
# Simulated cold store (external device, own MQTT client)
# ============================================================
class ColdStoreSimulator:
    def __init__(self):
        self.enabled = True
        self.chambers = [
            {"id": 0, "name": "Komora 1", "temp": -16.0, "setpoint": -18.0,
             "humidity": 85.0, "co2": 420.0,
             "on": True, "cooling": False, "defrost": False, "door_open": False,
             "compressor": False, "alarm": False, "_defrost_ticks": 0},
            {"id": 1, "name": "Komora 2", "temp": 4.5, "setpoint": 2.0,
             "humidity": 90.0, "co2": 650.0,
             "on": True, "cooling": False, "defrost": False, "door_open": False,
             "compressor": False, "alarm": False, "_defrost_ticks": 0},
            {"id": 2, "name": "Komora 3", "temp": 6.0, "setpoint": 4.0,
             "humidity": 88.0, "co2": 500.0,
             "on": False, "cooling": False, "defrost": False, "door_open": False,
             "compressor": False, "alarm": False, "_defrost_ticks": 0},
        ]
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.mc = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"fatek-sim-{uuid.uuid4().hex[:8]}",
        )
        self.mc.on_connect = self._on_connect
        self.mc.on_message = self._on_message

    def _on_connect(self, c, u, flags, rc, props):
        logger.info("SIM connected rc=%s", rc)
        c.subscribe(command_topic(DEVICE_ID), qos=1)

    def _on_message(self, c, u, msg):
        try:
            cmd = json.loads(msg.payload.decode())
        except Exception:
            return
        self.apply_command(cmd)
        self.publish()

    def apply_command(self, cmd: dict):
        t = cmd.get("type")
        ci = int(cmd.get("chamber", -1))
        if not (0 <= ci < len(self.chambers)):
            return
        ch = self.chambers[ci]
        if t == "set_setpoint":
            try:
                ch["setpoint"] = max(-40.0, min(20.0, float(cmd.get("value"))))
            except (TypeError, ValueError):
                pass
        elif t == "chamber_power":
            ch["on"] = bool(cmd.get("value"))
            if not ch["on"]:
                ch["cooling"] = ch["compressor"] = ch["defrost"] = False
        elif t == "defrost":
            if ch["on"]:
                ch["defrost"] = bool(cmd.get("value"))
                ch["_defrost_ticks"] = 30 if ch["defrost"] else 0
                if ch["defrost"]:
                    ch["cooling"] = ch["compressor"] = False

    def _step(self):
        for ch in self.chambers:
            if not ch["on"]:
                # drift toward ambient when off
                ch["temp"] += 0.15
                ch["cooling"] = ch["compressor"] = False
                ch["alarm"] = False
                self._sensors(ch)
                continue
            # random door events
            if random.random() < 0.03:
                ch["door_open"] = not ch["door_open"]
            if ch["defrost"]:
                ch["_defrost_ticks"] -= 1
                ch["temp"] += 0.4
                if ch["_defrost_ticks"] <= 0:
                    ch["defrost"] = False
            else:
                sp = ch["setpoint"]
                # thermostat hysteresis
                if ch["temp"] > sp + 0.5:
                    ch["cooling"] = True
                elif ch["temp"] <= sp - 0.5:
                    ch["cooling"] = False
                if ch["cooling"]:
                    ch["temp"] -= 0.35
                    ch["compressor"] = True
                else:
                    ch["temp"] += 0.08
                    ch["compressor"] = False
                if ch["door_open"]:
                    ch["temp"] += 0.2
            ch["alarm"] = ch["temp"] > ch["setpoint"] + 5.0
            ch["temp"] = round(ch["temp"], 1)
            self._sensors(ch)

    def _sensors(self, ch):
        # humidity drifts; rises with defrost/door, falls with active cooling
        drift = 0.0
        if ch["defrost"] or ch["door_open"]:
            drift += 0.6
        if ch["compressor"]:
            drift -= 0.4
        drift += random.uniform(-0.3, 0.3)
        ch["humidity"] = round(max(40.0, min(99.0, ch["humidity"] + drift)), 1)
        # CO2 rises when door open, slowly decays otherwise
        if ch["door_open"]:
            ch["co2"] += random.uniform(5, 20)
        else:
            ch["co2"] += random.uniform(-8, 4)
        ch["co2"] = round(max(400.0, min(5000.0, ch["co2"])), 0)

    def _loop(self):
        while not self._stop.is_set():
            self._step()
            self.publish()
            self._stop.wait(1.0)

    def snapshot(self) -> dict:
        return {
            "device_id": DEVICE_ID,
            "model": "Fatek FBs-24MC",
            "chambers": [
                {k: v for k, v in ch.items() if not k.startswith("_")}
                for ch in self.chambers
            ],
            "ts": now_iso(),
        }

    def publish(self):
        if not self.enabled:
            return
        try:
            self.mc.publish(state_topic(DEVICE_ID), json.dumps(self.snapshot()), qos=1)
        except Exception as e:
            logger.warning("SIM publish failed: %s", e)

    def start(self):
        self.mc.connect_async(MQTT_HOST, MQTT_PORT, keepalive=60)
        self.mc.loop_start()
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        try:
            self.mc.loop_stop()
            self.mc.disconnect()
        except Exception:
            pass


# ============================================================
# Backend gateway MQTT client (subscriber + commander)
# ============================================================
class Gateway:
    def __init__(self):
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.ws_clients: set[WebSocket] = set()
        self.latest_state: Optional[dict] = None
        self.last_seen: Optional[float] = None
        self.connected = False
        self.mc = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"fatek-api-{uuid.uuid4().hex[:8]}",
        )
        self.mc.on_connect = self._on_connect
        self.mc.on_disconnect = self._on_disconnect
        self.mc.on_message = self._on_message

    def _on_connect(self, c, u, flags, rc, props):
        self.connected = True
        logger.info("GATEWAY connected rc=%s", rc)
        c.subscribe(f"{MQTT_PREFIX}/+/state", qos=1)
        self._schedule_event("info", "Połączono z brokerem MQTT", {"host": MQTT_HOST})

    def _on_disconnect(self, c, u, flags, rc, props):
        self.connected = False
        logger.warning("GATEWAY disconnected rc=%s", rc)
        self._schedule_event("warning", "Rozłączono z brokerem MQTT", {})

    def _on_message(self, c, u, msg):
        try:
            payload = json.loads(msg.payload.decode())
        except Exception:
            return
        prev = self.latest_state
        self.latest_state = payload
        self.last_seen = time.time()
        self._detect_alarms(prev, payload)
        self._schedule_persist(msg.topic, payload)
        self._schedule_broadcast({"type": "state", "topic": msg.topic, "payload": payload})

    def _detect_alarms(self, prev, cur):
        if not cur.get("chambers"):
            return
        prev_map = {c["id"]: c for c in (prev.get("chambers", []) if prev else [])}
        for ch in cur["chambers"]:
            was = prev_map.get(ch["id"], {}).get("alarm", False)
            if ch.get("alarm") and not was:
                self._schedule_event("warning", f"ALARM: {ch['name']} {ch['temp']}°C", {"chamber": ch["id"]})

    def _schedule_persist(self, topic, payload):
        if self.loop and not self.loop.is_closed():
            asyncio.run_coroutine_threadsafe(self._persist(topic, payload), self.loop)

    def _schedule_broadcast(self, data):
        if self.loop and not self.loop.is_closed():
            asyncio.run_coroutine_threadsafe(broadcast(self, data), self.loop)

    def _schedule_event(self, level, message, meta):
        if self.loop and not self.loop.is_closed():
            asyncio.run_coroutine_threadsafe(self._event(level, message, meta), self.loop)

    async def _persist(self, topic, payload):
        doc = {"device_id": payload.get("device_id", DEVICE_ID), "topic": topic,
               "payload": payload, "received_at": now_iso()}
        await db.plc_states.insert_one(doc)

    async def _event(self, level, message, meta):
        doc = {"level": level, "message": message, "meta": meta, "ts": now_iso()}
        await db.plc_events.insert_one(doc)
        d = dict(doc)
        d.pop("_id", None)
        await broadcast(self, {"type": "event", "event": d})

    def log_event_sync(self, level, message, meta):
        self._schedule_event(level, message, meta)

    def publish_command(self, device_id: str, cmd: dict) -> bool:
        info = self.mc.publish(command_topic(device_id), json.dumps(cmd), qos=1)
        return info.rc == mqtt.MQTT_ERR_SUCCESS

    def is_online(self) -> bool:
        return self.last_seen is not None and (time.time() - self.last_seen) < 5

    def start(self, loop):
        self.loop = loop
        self.mc.connect_async(MQTT_HOST, MQTT_PORT, keepalive=60)
        self.mc.loop_start()

    def stop(self):
        try:
            self.mc.loop_stop()
            self.mc.disconnect()
        except Exception:
            pass


gateway = Gateway()
simulator = ColdStoreSimulator()


async def broadcast(gw: Gateway, data: dict):
    dead = []
    for ws in list(gw.ws_clients):
        try:
            await ws.send_json(data)
        except Exception:
            dead.append(ws)
    for ws in dead:
        gw.ws_clients.discard(ws)


@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_running_loop()
    gateway.start(loop)
    simulator.start()
    yield
    simulator.stop()
    gateway.stop()
    client.close()


app = FastAPI(lifespan=lifespan)
api = APIRouter(prefix="/api")


class CommandIn(BaseModel):
    type: str = Field(pattern=r"^(set_setpoint|chamber_power|defrost)$")
    chamber: int
    value: Any = None


@api.get("/")
async def root():
    return {"message": "Fatek MQTT cold-store gateway"}


@api.get("/config")
async def get_config():
    return {
        "broker_host": MQTT_HOST,
        "broker_port": MQTT_PORT,
        "prefix": MQTT_PREFIX,
        "device_id": DEVICE_ID,
        "state_topic": state_topic(DEVICE_ID),
        "command_topic": command_topic(DEVICE_ID),
        "chambers": len(simulator.chambers),
    }


@api.get("/health")
async def health():
    return {
        "ok": True,
        "broker_connected": gateway.connected,
        "device_online": gateway.is_online(),
        "simulator_enabled": simulator.enabled,
    }


@api.get("/device/{device_id}/state")
async def device_state(device_id: str):
    if gateway.latest_state:
        return {"online": gateway.is_online(), "state": gateway.latest_state}
    doc = await db.plc_states.find_one({"device_id": device_id}, sort=[("received_at", -1)])
    if not doc:
        return {"online": False, "state": None}
    doc.pop("_id", None)
    return {"online": gateway.is_online(), "state": doc.get("payload")}


@api.post("/device/{device_id}/command")
async def device_command(device_id: str, cmd: CommandIn):
    if "/" in device_id or len(device_id) > 64:
        raise HTTPException(400, "invalid device_id")
    body = cmd.model_dump()
    body["request_id"] = uuid.uuid4().hex
    if not gateway.publish_command(device_id, body):
        raise HTTPException(503, "MQTT publish failed")
    name = f"Komora {cmd.chamber + 1}"
    if cmd.type == "set_setpoint":
        msg = f"{name}: nastawa = {cmd.value}°C"
    elif cmd.type == "chamber_power":
        msg = f"{name}: {'włączona' if cmd.value else 'wyłączona'}"
    else:
        msg = f"{name}: rozmrażanie {'ON' if cmd.value else 'OFF'}"
    gateway.log_event_sync("command", msg, body)
    return {"queued": True, "request_id": body["request_id"]}


@api.get("/events")
async def events(limit: int = 100):
    docs = await db.plc_events.find({}, {"_id": 0}).sort("ts", -1).to_list(limit)
    return {"events": docs}


@api.post("/simulator/toggle")
async def simulator_toggle(enable: bool = True):
    simulator.enabled = enable
    gateway.log_event_sync("info", f"Symulator {'włączony' if enable else 'wyłączony'}", {})
    return {"simulator_enabled": simulator.enabled}


@app.websocket("/api/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    gateway.ws_clients.add(ws)
    if gateway.latest_state:
        await ws.send_json({"type": "state", "topic": state_topic(DEVICE_ID),
                            "payload": gateway.latest_state})
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        gateway.ws_clients.discard(ws)
    except Exception:
        gateway.ws_clients.discard(ws)


app.include_router(api)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

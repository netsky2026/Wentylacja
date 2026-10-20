"""
Fatek PLC MQTT gateway + simulator.

Architecture:
  Simulated Fatek FBs PLC  <--MQTT-->  HiveMQ broker  <--MQTT-->  FastAPI backend  <--WS/HTTP-->  React app

The simulator acts as an external device: it owns its own MQTT client, subscribes to
its command topic and publishes its state to the broker. The backend owns a separate
MQTT client that subscribes to state topics and publishes user commands. This makes the
full round-trip travel through the public broker, exactly like a real Fatek controller.
"""
from fastapi import FastAPI, APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import json
import asyncio
import logging
import threading
import random
import uuid
from pathlib import Path
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Optional, List

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

DEVICE_ID = "plc-01"
NUM_X = 8   # discrete inputs (read-only sensors)
NUM_Y = 8   # discrete outputs (coils)
NUM_M = 8   # internal relays
NUM_R = 6   # 16-bit data registers

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def state_topic(device_id: str) -> str:
    return f"{MQTT_PREFIX}/{device_id}/state"


def command_topic(device_id: str) -> str:
    return f"{MQTT_PREFIX}/{device_id}/command"


# ============================================================
# Simulated Fatek FBs PLC  (external device, own MQTT client)
# ============================================================
class FatekSimulator:
    def __init__(self):
        self.enabled = True
        self.running = True            # PLC run/stop state
        self.x = [False] * NUM_X       # inputs
        self.y = [False] * NUM_Y       # outputs
        self.m = [False] * NUM_M       # relays
        self.r = [0] * NUM_R           # data registers
        self.r[0] = 230                # e.g. voltage
        self.r[1] = 50                 # e.g. frequency
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
        if t == "plc_run":
            self.running = bool(cmd.get("value"))
        elif t == "set_output":
            i = int(cmd.get("index", -1))
            if cmd.get("target") == "Y" and 0 <= i < NUM_Y:
                self.y[i] = bool(cmd.get("value"))
            elif cmd.get("target") == "M" and 0 <= i < NUM_M:
                self.m[i] = bool(cmd.get("value"))
        elif t == "set_register":
            i = int(cmd.get("index", -1))
            if 0 <= i < NUM_R:
                self.r[i] = int(cmd.get("value", 0)) & 0xFFFF

    def _loop(self):
        tick = 0
        while not self._stop.is_set():
            if self.running:
                # simulate fluctuating sensor inputs
                for i in range(NUM_X):
                    if random.random() < 0.15:
                        self.x[i] = not self.x[i]
                # R2 = rising counter, R3 = pseudo temperature
                self.r[2] = (self.r[2] + 1) & 0xFFFF
                self.r[3] = 200 + int(50 * random.random())  # 20.0-25.0 C x10
                self.r[4] = sum(self.y) * 100
            self.publish()
            tick += 1
            self._stop.wait(1.0)

    def snapshot(self) -> dict:
        return {
            "device_id": DEVICE_ID,
            "model": "Fatek FBs-24MC",
            "running": self.running,
            "x": list(self.x),
            "y": list(self.y),
            "m": list(self.m),
            "r": list(self.r),
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
        self.latest_state = payload
        self.last_seen = asyncio.get_event_loop().time() if False else None
        import time
        self.last_seen = time.time()
        self._schedule_persist(msg.topic, payload)
        self._schedule_broadcast({"type": "state", "topic": msg.topic, "payload": payload})

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
        import time
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
simulator = FatekSimulator()


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


# ----- Models -----
class CommandIn(BaseModel):
    type: str = Field(pattern=r"^(plc_run|set_output|set_register)$")
    target: Optional[str] = None
    index: Optional[int] = None
    value: Any = None


# ----- Routes -----
@api.get("/")
async def root():
    return {"message": "Fatek MQTT gateway"}


@api.get("/config")
async def get_config():
    return {
        "broker_host": MQTT_HOST,
        "broker_port": MQTT_PORT,
        "prefix": MQTT_PREFIX,
        "device_id": DEVICE_ID,
        "state_topic": state_topic(DEVICE_ID),
        "command_topic": command_topic(DEVICE_ID),
        "layout": {"x": NUM_X, "y": NUM_Y, "m": NUM_M, "r": NUM_R},
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
    # human readable log
    if cmd.type == "plc_run":
        msg = f"Komenda: PLC {'START' if cmd.value else 'STOP'}"
    elif cmd.type == "set_output":
        msg = f"Komenda: {cmd.target}{cmd.index} = {'ON' if cmd.value else 'OFF'}"
    else:
        msg = f"Komenda: R{cmd.index} = {cmd.value}"
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
    # push current snapshot immediately
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

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
from fastapi.responses import StreamingResponse
from motor.motor_asyncio import AsyncIOMotorClient
import os
import json
import time
import asyncio
import logging
import threading
import random
import uuid
import copy
from pathlib import Path
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
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

DEVICE_ID = "chlodnia-01"
MQTT_USER = ""
MQTT_PASS = ""
MQTT_TLS = False
SAMPLE_S = 15

# per-chamber alarm thresholds (loaded from Mongo at startup, defaults below)
DEFAULT_THRESHOLDS = {
    0: {"temp_max": 26.0, "co2_max": 3000.0},
    1: {"temp_max": 28.0, "co2_max": 3000.0},
    2: {"temp_max": 30.0, "co2_max": 3000.0},
}
THRESHOLDS: dict = dict(DEFAULT_THRESHOLDS)

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_client(tag: str) -> mqtt.Client:
    c = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                    client_id=f"{tag}-{uuid.uuid4().hex[:8]}")
    if MQTT_USER:
        c.username_pw_set(MQTT_USER, MQTT_PASS or None)
    if MQTT_TLS:
        c.tls_set()
    return c


def state_topic(device_id: str) -> str:
    return f"{MQTT_PREFIX}/{device_id}/state"


def command_topic(device_id: str) -> str:
    return f"{MQTT_PREFIX}/{device_id}/command"


# ============================================================
# Simulated piggery (chlewnia) — external device, own MQTT client
# ============================================================
class PiggerySimulator:
    def __init__(self):
        self.enabled = True
        # chamber: temp control via ventilation (curtains L/R + chimneys) and heating
        self.chambers = [
            {"id": 0, "name": "Komora 1", "temp": 21.0, "setpoint": 20.0,
             "humidity": 65.0, "co2": 900.0, "on": True, "heating": False,
             "curtain_left": 30.0, "curtain_right": 30.0, "chimney": 40.0, "alarm": False},
            {"id": 1, "name": "Komora 2", "temp": 24.5, "setpoint": 22.0,
             "humidity": 70.0, "co2": 1100.0, "on": True, "heating": False,
             "curtain_left": 50.0, "curtain_right": 55.0, "chimney": 60.0, "alarm": False},
            {"id": 2, "name": "Komora 3", "temp": 18.0, "setpoint": 24.0,
             "humidity": 60.0, "co2": 800.0, "on": False, "heating": False,
             "curtain_left": 0.0, "curtain_right": 0.0, "chimney": 0.0, "alarm": False},
        ]
        # whole-plant metering
        self.plant = {"power_kw": 0.0, "power_kwh": 128.4, "water_lpm": 0.0, "water_total_l": 5420.0}
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.mc: Optional[mqtt.Client] = None
        for ch in self.chambers:
            ch["mode"] = "auto"
            ch["manual"] = {"curtain_left": ch["curtain_left"], "curtain_right": ch["curtain_right"],
                          "chimney": ch["chimney"]}

    def mqtt_start(self):
        self.mc = make_client("fatek-sim")
        self.mc.on_connect = self._on_connect
        self.mc.on_message = self._on_message
        self.mc.connect_async(MQTT_HOST, MQTT_PORT, keepalive=60)
        self.mc.loop_start()

    def mqtt_stop(self):
        try:
            self.mc.loop_stop()
            self.mc.disconnect()
        except Exception:
            pass

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
                ch["setpoint"] = max(5.0, min(35.0, float(cmd.get("value"))))
            except (TypeError, ValueError):
                pass
        elif t == "set_mode":
            if cmd.get("value") in ("auto", "manual"):
                ch["mode"] = cmd["value"]
                if ch["mode"] == "manual":
                    ch["manual"] = {k: ch[k] for k in ("curtain_left", "curtain_right", "chimney")}
        elif t == "set_vent":
            val = cmd.get("value") or {}
            for k in ("curtain_left", "curtain_right", "chimney"):
                if isinstance(val.get(k), (int, float)) and not isinstance(val.get(k), bool):
                    ch["manual"][k] = max(0.0, min(100.0, float(val[k])))
        elif t == "chamber_power":
            ch["on"] = bool(cmd.get("value"))
            if not ch["on"]:
                ch["heating"] = False
                ch["curtain_left"] = ch["curtain_right"] = ch["chimney"] = 0.0

    @staticmethod
    def _approach(cur, target, rate):
        if cur < target:
            return min(target, cur + rate)
        return max(target, cur - rate)

    def _step(self):
        for ch in self.chambers:
            if not ch["on"]:
                ch["temp"] += (18.0 - ch["temp"]) * 0.02  # drift to barn ambient
                ch["curtain_left"] = self._approach(ch["curtain_left"], 0.0, 4)
                ch["curtain_right"] = self._approach(ch["curtain_right"], 0.0, 4)
                ch["chimney"] = self._approach(ch["chimney"], 0.0, 4)
                ch["heating"] = False
                ch["alarm"] = False
                self._sensors(ch)
                continue
            sp = ch["setpoint"]
            err = ch["temp"] - sp  # >0 too warm -> ventilate; <0 too cold -> heat
            # ventilation demand 0..100 from how far above setpoint
            target_vent = max(0.0, min(100.0, (err + 1.0) * 28.0))
            if ch["mode"] == "manual":
                tl, tr, tc = ch["manual"]["curtain_left"], ch["manual"]["curtain_right"], ch["manual"]["chimney"]
            else:
                tl, tr, tc = target_vent, min(100.0, target_vent + 4), target_vent
            ch["curtain_left"] = round(self._approach(ch["curtain_left"], tl, 3), 1)
            ch["curtain_right"] = round(self._approach(ch["curtain_right"], tr, 3), 1)
            ch["chimney"] = round(self._approach(ch["chimney"], tc, 4), 1)
            ch["heating"] = err < -1.0
            # temperature dynamics
            vent = (ch["curtain_left"] + ch["curtain_right"] + ch["chimney"]) / 3.0
            ch["temp"] += 0.05  # animal body heat
            ch["temp"] -= vent * 0.004  # ventilation cooling
            if ch["heating"]:
                ch["temp"] += 0.18
            ch["temp"] += random.uniform(-0.05, 0.05)
            ch["temp"] = round(ch["temp"], 1)
            ch["alarm"] = False  # thresholds evaluated by backend gateway
            self._sensors(ch)
        self._meter()

    def _sensors(self, ch):
        vent = (ch["curtain_left"] + ch["curtain_right"] + ch["chimney"]) / 3.0 if ch["on"] else 0.0
        # humidity: animals add, ventilation removes
        hum_target = (78.0 - vent * 0.3) if ch["on"] else 60.0
        ch["humidity"] += (hum_target - ch["humidity"]) * 0.03 + random.uniform(-0.3, 0.3)
        ch["humidity"] = round(max(35.0, min(99.0, ch["humidity"])), 1)
        # CO2: animals raise it, ventilation lowers it
        co2_target = (2400.0 - vent * 18.0) if ch["on"] else 500.0
        ch["co2"] += (co2_target - ch["co2"]) * 0.03 + random.uniform(-10, 10)
        ch["co2"] = round(max(400.0, min(6000.0, ch["co2"])), 0)

    def _meter(self):
        # power: base + fans (chimney) + heaters
        fans = sum(ch["chimney"] for ch in self.chambers if ch["on"]) / 100.0
        heat = sum(1 for ch in self.chambers if ch.get("heating"))
        power = 1.2 + fans * 2.5 + heat * 3.0 + random.uniform(-0.2, 0.2)
        self.plant["power_kw"] = round(max(0.0, power), 2)
        self.plant["power_kwh"] = round(self.plant["power_kwh"] + power / 3600.0, 3)
        # water: animals drink (fluctuating)
        active = sum(1 for ch in self.chambers if ch["on"])
        lpm = active * random.uniform(0.6, 2.2)
        self.plant["water_lpm"] = round(lpm, 2)
        self.plant["water_total_l"] = round(self.plant["water_total_l"] + lpm / 60.0, 2)

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
            "plant": dict(self.plant),
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
        self.mqtt_start()
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self.mqtt_stop()


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
        self.mc: Optional[mqtt.Client] = None

    def mqtt_start(self):
        self.mc = make_client("fatek-api")
        self.mc.on_connect = self._on_connect
        self.mc.on_disconnect = self._on_disconnect
        self.mc.on_message = self._on_message
        self.mc.connect_async(MQTT_HOST, MQTT_PORT, keepalive=60)
        self.mc.loop_start()

    def mqtt_stop(self):
        try:
            self.mc.loop_stop()
            self.mc.disconnect()
        except Exception:
            pass
        self.connected = False

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
        self.annotate(payload)
        self.latest_state = payload
        self.last_seen = time.time()
        self._detect_alarms(prev, payload)
        self._schedule_persist(msg.topic, payload)
        self._schedule_broadcast({"type": "state", "topic": msg.topic, "payload": payload})

    def annotate(self, payload):
        """Overlay the monitoring app's alarm thresholds onto each chamber."""
        for ch in payload.get("chambers", []):
            th = THRESHOLDS.get(ch["id"], {})
            tmax = th.get("temp_max")
            cmax = th.get("co2_max")
            ch["temp_max"] = tmax
            ch["co2_max"] = cmax
            ch["temp_alarm"] = bool(ch.get("on") and tmax is not None and ch["temp"] > tmax)
            ch["co2_alarm"] = bool(cmax is not None and ch["co2"] > cmax)
            ch["alarm"] = bool(ch["temp_alarm"] or ch["co2_alarm"])
        return payload

    def _detect_alarms(self, prev, cur):
        if not cur.get("chambers"):
            return
        prev_map = {c["id"]: c for c in (prev.get("chambers", []) if prev else [])}
        for ch in cur["chambers"]:
            was = prev_map.get(ch["id"], {}).get("alarm", False)
            if ch.get("alarm") and not was:
                reasons = []
                if ch.get("temp_alarm"):
                    reasons.append(f"temp {ch['temp']}°C > {ch.get('temp_max')}°C")
                if ch.get("co2_alarm"):
                    reasons.append(f"CO₂ {int(ch['co2'])} > {int(ch.get('co2_max'))} ppm")
                reason = ", ".join(reasons)
                title = f"ALARM: {ch['name']}"
                self._schedule_event("warning", f"{title} — {reason}", {"chamber": ch["id"]})
                self._schedule_broadcast({"type": "alarm", "chamber": ch["id"],
                                          "title": title, "body": reason})

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
        self.mqtt_start()

    def stop(self):
        self.mqtt_stop()


gateway = Gateway()
simulator = PiggerySimulator()


async def broadcast(gw: Gateway, data: dict):
    dead = []
    for ws in list(gw.ws_clients):
        try:
            await ws.send_json(data)
        except Exception:
            dead.append(ws)
    for ws in dead:
        gw.ws_clients.discard(ws)


async def load_thresholds():
    global THRESHOLDS
    THRESHOLDS = dict(DEFAULT_THRESHOLDS)
    async for doc in db.chamber_thresholds.find({}):
        THRESHOLDS[doc["chamber"]] = {"temp_max": doc["temp_max"], "co2_max": doc["co2_max"]}


def set_broker_globals(cfg: dict):
    global MQTT_HOST, MQTT_PORT, MQTT_USER, MQTT_PASS, MQTT_TLS, MQTT_PREFIX, DEVICE_ID
    MQTT_HOST = cfg["host"]
    MQTT_PORT = int(cfg["port"])
    MQTT_USER = cfg.get("username") or ""
    MQTT_PASS = cfg.get("password") or ""
    MQTT_TLS = bool(cfg.get("tls"))
    MQTT_PREFIX = cfg["prefix"].strip("/")
    DEVICE_ID = cfg["device_id"]


async def load_broker():
    doc = await db.broker_config.find_one({"_id": "main"})
    if doc:
        set_broker_globals(doc)


async def history_sampler():
    """Persist a downsampled history point per chamber every 15s for charts."""
    while True:
        await asyncio.sleep(15)
        st = gateway.latest_state
        if not st or not st.get("chambers") or not gateway.is_online():
            continue
        ts = now_iso()
        docs = [{"chamber": ch["id"], "name": ch["name"], "temp": ch["temp"],
                 "humidity": ch["humidity"], "co2": ch["co2"],
                 "curtain_left": ch.get("curtain_left"), "curtain_right": ch.get("curtain_right"),
                 "chimney": ch.get("chimney"), "ts": ts}
                for ch in st["chambers"]]
        plant = st.get("plant") or {}
        try:
            await db.plc_history.insert_many(docs)
            if plant:
                await db.plc_plant_history.insert_one(
                    {"power_kw": plant.get("power_kw"), "water_lpm": plant.get("water_lpm"), "ts": ts})
        except Exception as e:
            logger.warning("history insert failed: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_running_loop()
    await load_thresholds()
    await load_broker()
    try:
        await db.plc_history.create_index("ts")
    except Exception:
        pass
    gateway.start(loop)
    simulator.start()
    sampler = asyncio.create_task(history_sampler())
    yield
    sampler.cancel()
    simulator.stop()
    gateway.stop()
    client.close()


app = FastAPI(lifespan=lifespan)
api = APIRouter(prefix="/api")


class CommandIn(BaseModel):
    type: str = Field(pattern=r"^(set_setpoint|chamber_power|set_mode|set_vent)$")
    chamber: int = Field(ge=0, le=2)
    value: Any = None


class BrokerIn(BaseModel):
    host: str = Field(min_length=1, max_length=255, pattern=r"^[A-Za-z0-9.\-]+$")
    port: int = Field(ge=1, le=65535)
    username: str = Field(default="", max_length=128)
    password: Optional[str] = Field(default=None, max_length=256)
    tls: bool = False
    prefix: str = Field(min_length=1, max_length=128, pattern=r"^[^#+]+$")
    device_id: str = Field(min_length=1, max_length=64, pattern=r"^[^/#+]+$")


class ThresholdIn(BaseModel):
    temp_max: float
    co2_max: float


@api.get("/")
async def root():
    return {"message": "Fatek MQTT piggery gateway"}


@api.get("/config")
async def get_config():
    return {
        "broker_host": MQTT_HOST,
        "broker_port": MQTT_PORT,
        "username": MQTT_USER,
        "has_password": bool(MQTT_PASS),
        "tls": MQTT_TLS,
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
    if cmd.type == "set_setpoint" and (isinstance(cmd.value, bool) or not isinstance(cmd.value, (int, float))):
        raise HTTPException(422, "value must be a number")
    if cmd.type == "set_mode" and cmd.value not in ("auto", "manual"):
        raise HTTPException(422, "value must be auto|manual")
    if cmd.type == "set_vent":
        v = cmd.value
        if not isinstance(v, dict) or not v or any(
                k not in ("curtain_left", "curtain_right", "chimney") or isinstance(x, bool)
                or not isinstance(x, (int, float)) or not 0 <= x <= 100 for k, x in v.items()):
            raise HTTPException(422, "invalid vent values")
    body = cmd.model_dump()
    body["request_id"] = uuid.uuid4().hex
    if not gateway.publish_command(device_id, body):
        raise HTTPException(503, "MQTT publish failed")
    name = f"Komora {cmd.chamber + 1}"
    if cmd.type == "set_setpoint":
        msg = f"{name}: nastawa = {cmd.value}°C"
    elif cmd.type == "set_mode":
        msg = f"{name}: tryb {'RĘCZNY' if cmd.value == 'manual' else 'AUTO'}"
    elif cmd.type == "set_vent":
        lbl = {"curtain_left": "kurtyna L zamkn.", "curtain_right": "kurtyna P zamkn.", "chimney": "komin otw."}
        msg = f"{name}: " + ", ".join(
            f"{lbl[k]} {round(100 - x) if k != 'chimney' else round(x)}%" for k, x in cmd.value.items())
    else:
        msg = f"{name}: {'włączona' if cmd.value else 'wyłączona'}"
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


@api.get("/thresholds")
async def get_thresholds():
    return {"thresholds": [{"chamber": k, **v} for k, v in sorted(THRESHOLDS.items())]}


@api.put("/thresholds/{chamber}")
async def set_threshold(chamber: int, body: ThresholdIn):
    if chamber not in DEFAULT_THRESHOLDS:
        raise HTTPException(404, "unknown chamber")
    THRESHOLDS[chamber] = {"temp_max": body.temp_max, "co2_max": body.co2_max}
    await db.chamber_thresholds.update_one(
        {"chamber": chamber},
        {"$set": {"chamber": chamber, "temp_max": body.temp_max, "co2_max": body.co2_max}},
        upsert=True,
    )
    gateway.log_event_sync(
        "info", f"Komora {chamber + 1}: progi temp ≤ {body.temp_max}°C, CO₂ ≤ {int(body.co2_max)} ppm", {})
    # re-evaluate current state against new thresholds immediately
    if gateway.latest_state:
        prev = copy.deepcopy(gateway.latest_state)
        gateway.annotate(gateway.latest_state)
        gateway._detect_alarms(prev, gateway.latest_state)
    return {"ok": True, "thresholds": THRESHOLDS[chamber]}


@api.get("/history")
async def history(hours: int = 3):
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    docs = await db.plc_history.find(
        {"ts": {"$gte": since}}, {"_id": 0}).sort("ts", 1).to_list(6000)
    out: dict = {}
    for d in docs:
        out.setdefault(str(d["chamber"]), []).append(d)
    plant = await db.plc_plant_history.find(
        {"ts": {"$gte": since}}, {"_id": 0}).sort("ts", 1).to_list(2000)
    return {"history": out, "plant": plant}


@api.put("/broker")
async def set_broker(body: BrokerIn):
    cfg = body.model_dump()
    if cfg["password"] is None:
        cfg["password"] = MQTT_PASS
    await db.broker_config.update_one({"_id": "main"}, {"$set": cfg}, upsert=True)
    await asyncio.to_thread(gateway.mqtt_stop)
    await asyncio.to_thread(simulator.mqtt_stop)
    set_broker_globals(cfg)
    gateway.latest_state = None
    gateway.last_seen = None
    gateway.mqtt_start()
    simulator.mqtt_start()
    gateway.log_event_sync("info", f"Zmieniono broker: {MQTT_HOST}:{MQTT_PORT}", {})
    return await get_config()


@api.get("/usage/daily")
async def usage_daily(days: int = 7):
    days = max(1, min(60, days))
    start = (datetime.now(timezone.utc) - timedelta(days=days - 1)).date()
    rows = await db.plc_plant_history.aggregate([
        {"$match": {"ts": {"$gte": start.isoformat()}}},
        {"$group": {"_id": {"$substr": ["$ts", 0, 10]},
                    "p": {"$sum": "$power_kw"}, "w": {"$sum": "$water_lpm"}}},
    ]).to_list(100)
    by = {r["_id"]: r for r in rows}
    out = []
    for i in range(days):
        d = (start + timedelta(days=i)).isoformat()
        r = by.get(d, {"p": 0, "w": 0})
        out.append({"date": d, "kwh": round(r["p"] * SAMPLE_S / 3600, 2),
                    "water_m3": round(r["w"] * SAMPLE_S / 60 / 1000, 3)})
    return {"days": out}


@api.get("/history/csv")
async def history_csv(chamber: int, hours: int = 24):
    if chamber not in DEFAULT_THRESHOLDS:
        raise HTTPException(404, "unknown chamber")
    hours = max(1, min(24 * 31, hours))
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    cursor = db.plc_history.find({"chamber": chamber, "ts": {"$gte": since}}, {"_id": 0}).sort("ts", 1)

    def fmt(v):
        return "" if v is None else str(v).replace(".", ",")

    async def gen():
        yield "\ufeffczas;temperatura_C;wilgotnosc_%;co2_ppm;kurtyna_L_zamkn_%;kurtyna_P_zamkn_%;komin_otw_%\n"
        async for d in cursor:
            cl, cr = d.get("curtain_left"), d.get("curtain_right")
            ts = datetime.fromisoformat(d["ts"]).astimezone().strftime("%Y-%m-%d %H:%M:%S")
            yield ";".join([ts, fmt(d.get("temp")), fmt(d.get("humidity")), fmt(d.get("co2")),
                            fmt(None if cl is None else round(100 - cl, 1)),
                            fmt(None if cr is None else round(100 - cr, 1)), fmt(d.get("chimney"))]) + "\n"

    fname = f"komora{chamber + 1}_{hours}h_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    return StreamingResponse(gen(), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="{fname}"'})


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

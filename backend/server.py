"""Multi-tenant Fatek PLC MQTT gateway for piggery ventilation (clients -> PLC devices -> chambers)."""
from fastapi import FastAPI, APIRouter, HTTPException, WebSocket, WebSocketDisconnect, Depends, Request, UploadFile, File
from fastapi.responses import JSONResponse, StreamingResponse, Response
import io
import requests
from PIL import Image
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import re
import json
import time
import math
import copy
import socket
import secrets
import asyncio
import logging
import threading
import random
import uuid
import ipaddress
from zoneinfo import ZoneInfo
from pathlib import Path
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from typing import Any, Optional, List

import paho.mqtt.client as mqtt
from bson import ObjectId
from cryptography.fernet import Fernet, InvalidToken
from pydantic import BaseModel, Field

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

import auth  # noqa: E402
import notify  # noqa: E402
from auth import require  # noqa: E402

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("fatek")

MONGO_URL = os.environ['MONGO_URL']
DB_NAME = os.environ['DB_NAME']
FRONTEND_URL = os.environ["FRONTEND_URL"].rstrip("/")
MQTT_HOST = os.environ['MQTT_HOST']
MQTT_PORT = int(os.environ['MQTT_PORT'])
MQTT_PREFIX = os.environ['MQTT_PREFIX'].strip('/')
MQTT_USER = os.environ.get("MQTT_USER", "")
MQTT_PASS = os.environ.get("MQTT_PASS", "")
MQTT_TLS = False
SAMPLE_S = 15
ALARM_REMIND_S = 30 * 60
DEFAULT_TH = {"temp_max": 28.0, "co2_max": 3000.0}
LEGACY_DEVICE = "chlodnia-01"
FERNET = Fernet(os.environ["BROKER_SECRET"].encode())

LOGO_DIR = Path(os.environ["LOGO_DIR"])
STORAGE_APP = "marco-polo-wentylacja"


def put_object(path: str, data: bytes) -> dict:
    f = LOGO_DIR / path
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(data)
    return {"path": path}


def get_object(path: str) -> bytes:
    f = LOGO_DIR / path
    if not f.is_file():
        raise HTTPException(404, "No logo")
    return f.read_bytes()


THEME_RX = r"^(green|light|blue|amber)$"

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

DEVICES: dict = {}     # device_id -> {client_id, client_name, name, chambers, simulated}
THRESHOLDS: dict = {}  # (device_id, chamber) -> {temp_max, co2_max}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def state_topic(device_id: str) -> str:
    return f"{MQTT_PREFIX}/{device_id}/state"


def command_topic(device_id: str) -> str:
    return f"{MQTT_PREFIX}/{device_id}/command"


def make_client(tag: str) -> mqtt.Client:
    c = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id=f"{tag}-{uuid.uuid4().hex[:8]}")
    if MQTT_USER:
        c.username_pw_set(MQTT_USER, MQTT_PASS or None)
    if MQTT_TLS:
        c.tls_set()
    return c


def encrypt_secret(v: str) -> str:
    return FERNET.encrypt(v.encode()).decode() if v else ""


def decrypt_secret(v: str) -> str:
    try:
        return FERNET.decrypt(v.encode()).decode() if v else ""
    except InvalidToken:
        logger.warning("secret could not be decrypted")
        return ""


def th_for(device_id: str, chamber: int) -> dict:
    return THRESHOLDS.get((device_id, chamber), DEFAULT_TH)


# ============================================================
# Simulated Fatek PLC (one per simulated device, own MQTT client)
# ============================================================
class PiggerySimulator:
    def __init__(self, device_id: str, n: int):
        self.device_id = device_id
        self.enabled = True
        rnd = random.Random(device_id)
        self.chambers = []
        for i in range(n):
            sp = 20.0 + (i % 3) * 2
            self.chambers.append({
                "id": i, "temp": round(sp + rnd.uniform(-1.5, 2.0), 1), "setpoint": sp, "humidity": 65.0 + rnd.uniform(0, 8),
                "co2": 900.0 + rnd.uniform(0, 400), "on": True, "heating": False, "mode": "auto",
                "curtain_left": 30.0, "curtain_right": 30.0, "chimney": 40.0,
                "manual": {"curtain_left": 30.0, "curtain_right": 30.0, "chimney": 40.0}})
        self.plant = {"power_kw": 0.0, "power_kwh": round(rnd.uniform(50, 200), 1), "water_lpm": 0.0,
                      "water_total_l": round(rnd.uniform(2000, 8000), 1)}
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.mc: Optional[mqtt.Client] = None

    def mqtt_start(self):
        self.mc = make_client(f"sim-{self.device_id}"[:20])
        self.mc.on_connect = lambda c, u, f, rc, p: c.subscribe(command_topic(self.device_id), qos=1)
        self.mc.on_message = self._on_message
        self.mc.connect_async(MQTT_HOST, MQTT_PORT, keepalive=60)
        self.mc.loop_start()

    def mqtt_stop(self):
        try:
            self.mc.disconnect()
            self.mc.loop_stop()
        except Exception:
            pass

    def _on_message(self, c, u, msg):
        try:
            cmd = json.loads(msg.payload.decode())
        except Exception:
            return
        self.apply_command(cmd)
        self.publish()

    def apply_command(self, cmd: dict):
        t = cmd.get("type")
        try:
            ci = int(cmd.get("chamber", -1))
        except (TypeError, ValueError):
            return
        if not (0 <= ci < len(self.chambers)):
            return
        ch = self.chambers[ci]
        if t == "set_setpoint" and isinstance(cmd.get("value"), (int, float)):
            ch["setpoint"] = max(5.0, min(35.0, float(cmd["value"])))
        elif t == "set_mode" and cmd.get("value") in ("auto", "manual"):
            ch["mode"] = cmd["value"]
            if ch["mode"] == "manual":
                ch["manual"] = {k: ch[k] for k in VENT_FIELDS}
        elif t == "set_vent":
            for k, v in (cmd.get("value") or {}).items():
                if k in VENT_FIELDS and isinstance(v, (int, float)) and not isinstance(v, bool):
                    ch["manual"][k] = max(0.0, min(100.0, float(v)))
        elif t == "chamber_power":
            ch["on"] = bool(cmd.get("value"))
            if not ch["on"]:
                ch["heating"] = False

    @staticmethod
    def _approach(cur, target, rate):
        return min(target, cur + rate) if cur < target else max(target, cur - rate)

    def _step(self):
        for ch in self.chambers:
            if not ch["on"]:
                ch["temp"] += (18.0 - ch["temp"]) * 0.02
                for k in VENT_FIELDS:
                    ch[k] = self._approach(ch[k], 0.0, 4)
                ch["heating"] = False
                self._sensors(ch)
                continue
            err = ch["temp"] - ch["setpoint"]
            target = max(0.0, min(100.0, (err + 1.0) * 28.0))
            if ch["mode"] == "manual":
                tl, tr, tc = (ch["manual"][k] for k in VENT_FIELDS)
            else:
                tl, tr, tc = target, min(100.0, target + 4), target
            ch["curtain_left"] = round(self._approach(ch["curtain_left"], tl, 3), 1)
            ch["curtain_right"] = round(self._approach(ch["curtain_right"], tr, 3), 1)
            ch["chimney"] = round(self._approach(ch["chimney"], tc, 4), 1)
            ch["heating"] = err < -1.0
            vent = (ch["curtain_left"] + ch["curtain_right"] + ch["chimney"]) / 3.0
            ch["temp"] += 0.05 - vent * 0.004 + (0.18 if ch["heating"] else 0) + random.uniform(-0.05, 0.05)
            ch["temp"] = round(ch["temp"], 1)
            self._sensors(ch)
        fans = sum(ch["chimney"] for ch in self.chambers if ch["on"]) / 100.0
        heat = sum(1 for ch in self.chambers if ch["heating"])
        power = max(0.0, 1.2 + fans * 2.5 + heat * 3.0 + random.uniform(-0.2, 0.2))
        self.plant["power_kw"] = round(power, 2)
        self.plant["power_kwh"] = round(self.plant["power_kwh"] + power / 3600.0, 3)
        lpm = sum(1 for ch in self.chambers if ch["on"]) * random.uniform(0.6, 2.2)
        self.plant["water_lpm"] = round(lpm, 2)
        self.plant["water_total_l"] = round(self.plant["water_total_l"] + lpm / 60.0, 2)

    @staticmethod
    def _sensors(ch):
        vent = (ch["curtain_left"] + ch["curtain_right"] + ch["chimney"]) / 3.0 if ch["on"] else 0.0
        hum_t = (78.0 - vent * 0.3) if ch["on"] else 60.0
        ch["humidity"] = round(max(35.0, min(99.0, ch["humidity"] + (hum_t - ch["humidity"]) * 0.03 + random.uniform(-0.3, 0.3))), 1)
        co2_t = (2400.0 - vent * 18.0) if ch["on"] else 500.0
        ch["co2"] = round(max(400.0, min(6000.0, ch["co2"] + (co2_t - ch["co2"]) * 0.03 + random.uniform(-10, 10))), 0)

    def snapshot(self) -> dict:
        return {"device_id": self.device_id, "model": "Fatek FBs-24MC (symulator)",
                "chambers": copy.deepcopy(self.chambers), "plant": dict(self.plant), "ts": now_iso()}

    def publish(self):
        if not self.enabled or not self.mc:
            return
        try:
            self.mc.publish(state_topic(self.device_id), json.dumps(self.snapshot()), qos=1)
        except Exception as e:
            logger.warning("SIM publish failed: %s", e)

    def _loop(self):
        while not self._stop.is_set():
            self._step()
            self.publish()
            self._stop.wait(1.0)

    def start(self):
        self.mqtt_start()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self.mqtt_stop()


class SimManager:
    def __init__(self):
        self.sims: dict = {}

    def sync(self):
        wanted = {d: v["chambers"] for d, v in DEVICES.items() if v["simulated"]}
        for d in list(self.sims):
            if d not in wanted or len(self.sims[d].chambers) != wanted[d]:
                self.sims.pop(d).stop()
        for d, n in wanted.items():
            if d not in self.sims:
                self.sims[d] = PiggerySimulator(d, n)
                self.sims[d].start()

    def restart_mqtt(self):
        for s in self.sims.values():
            s.mqtt_stop()
            s.mqtt_start()

    def stop_all(self):
        for s in self.sims.values():
            s.stop()
        self.sims.clear()


# ============================================================
# Payload validation
# ============================================================
NUM_FIELDS = ("temp", "setpoint", "humidity", "co2", "curtain_left", "curtain_right", "chimney")
VENT_FIELDS = ("curtain_left", "curtain_right", "chimney")
PLANT_FIELDS = ("power_kw", "power_kwh", "water_lpm", "water_total_l")


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def ch_name(device_id: str, cid: int) -> str:
    d = DEVICES.get(device_id) or {}
    return d.get("chamber_names", {}).get(str(cid)) or f"Komora {cid + 1}"


def sanitize_state(p, device_id: str) -> Optional[dict]:
    """Accept only well-formed numeric state with exactly the device's chambers; drop anything else."""
    n = DEVICES[device_id]["chambers"]
    if not isinstance(p, dict) or not isinstance(p.get("chambers"), list):
        return None
    ids = [c.get("id") if isinstance(c, dict) else None for c in p["chambers"]]
    if len(ids) != n or not all(_num(i) for i in ids) or sorted(int(i) for i in ids) != list(range(n)):
        return None
    chambers = []
    for ch in sorted(p["chambers"], key=lambda c: int(c["id"])):
        cid = int(ch["id"])
        out = {"id": cid, "name": ch_name(device_id, cid), "on": bool(ch.get("on")), "heating": bool(ch.get("heating")),
               "mode": "manual" if ch.get("mode") == "manual" else "auto"}
        for k in NUM_FIELDS:
            if not _num(ch.get(k)):
                return None
            out[k] = float(ch[k])
        man = ch.get("manual")
        if isinstance(man, dict):
            out["manual"] = {k: float(man[k]) for k in VENT_FIELDS if _num(man.get(k))}
        chambers.append(out)
    plant_in = p.get("plant") if isinstance(p.get("plant"), dict) else {}
    return {"device_id": device_id, "model": str(p.get("model", ""))[:64], "chambers": chambers,
            "plant": {k: float(plant_in[k]) for k in PLANT_FIELDS if _num(plant_in.get(k))}, "ts": now_iso()}


def annotate(device_id: str, payload: dict) -> dict:
    for ch in payload["chambers"]:
        th = th_for(device_id, ch["id"])
        ch["temp_max"], ch["co2_max"] = th["temp_max"], th["co2_max"]
        ch["temp_alarm"] = bool(ch["on"] and ch["temp"] > th["temp_max"])
        ch["co2_alarm"] = bool(ch["co2"] > th["co2_max"])
        ch["alarm"] = ch["temp_alarm"] or ch["co2_alarm"]
    return payload


def alarm_reason(ch: dict) -> str:
    r = []
    if ch.get("temp_alarm"):
        r.append(f"temperatura {ch['temp']}°C > {ch.get('temp_max')}°C")
    if ch.get("co2_alarm"):
        r.append(f"CO₂ {int(ch['co2'])} ppm > {int(ch.get('co2_max'))} ppm")
    return ", ".join(r)


def dev_label(device_id: str) -> str:
    d = DEVICES.get(device_id, {})
    return f"{d.get('client_name', '')} / {d.get('name', device_id)}"


# ============================================================
# Gateway
# ============================================================
class Gateway:
    def __init__(self):
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.ws_clients: dict = {}  # ws -> user
        self.states: dict = {}
        self.last_seen: dict = {}
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
            self.mc.disconnect()
            self.mc.loop_stop()
        except Exception:
            pass
        self.connected = False

    def _on_connect(self, c, u, flags, rc, props):
        self.connected = True
        c.subscribe(f"{MQTT_PREFIX}/+/state", qos=1)
        self.schedule(log_event("info", "Połączono z brokerem MQTT", {"host": MQTT_HOST}))

    def _on_disconnect(self, c, u, flags, rc, props):
        self.connected = False

    def _on_message(self, c, u, msg):
        parts = msg.topic.split("/")
        if len(parts) < 2 or "/".join(parts[:-2]) != MQTT_PREFIX or parts[-1] != "state":
            return
        device_id = parts[-2]
        if device_id not in DEVICES:
            return
        try:
            payload = sanitize_state(json.loads(msg.payload.decode()), device_id)
        except Exception:
            return
        if payload is None:
            return
        prev = self.states.get(device_id)
        annotate(device_id, payload)
        self.states[device_id] = payload
        self.last_seen[device_id] = time.time()
        self.detect_alarms(device_id, prev, payload)
        self.schedule(broadcast({"type": "state", "payload": payload}, DEVICES[device_id]["client_id"]))

    def detect_alarms(self, device_id, prev, cur):
        was = {c["id"]: c.get("alarm") for c in (prev or {}).get("chambers", [])}
        for ch in cur["chambers"]:
            if ch["alarm"] and not was.get(ch["id"]):
                title = f"ALARM: {dev_label(device_id)} – {ch_name(device_id, ch['id'])}"
                reason = alarm_reason(ch)
                self.schedule(log_event("warning", f"{title} — {reason}", {"chamber": ch["id"]}, device_id))
                self.schedule(broadcast({"type": "alarm", "device_id": device_id, "title": title, "body": reason},
                                        DEVICES[device_id]["client_id"]))

    def schedule(self, coro):
        if self.loop and not self.loop.is_closed():
            asyncio.run_coroutine_threadsafe(coro, self.loop)
        else:
            coro.close()

    def publish_command(self, device_id: str, cmd: dict) -> bool:
        return self.mc.publish(command_topic(device_id), json.dumps(cmd), qos=1).rc == mqtt.MQTT_ERR_SUCCESS

    def is_online(self, device_id: str) -> bool:
        t = self.last_seen.get(device_id)
        return t is not None and time.time() - t < 10


gateway = Gateway()
sims = SimManager()


async def broadcast(data: dict, client_id: Optional[str]):
    for ws, user in list(gateway.ws_clients.items()):
        if user["role"] != "superadmin" and user.get("client_id") != client_id:
            continue
        try:
            await ws.send_json(data)
        except Exception:
            gateway.ws_clients.pop(ws, None)


async def log_event(level: str, message: str, meta: dict, device_id: Optional[str] = None,
                    client_id: Optional[str] = None):
    if device_id and not client_id:
        client_id = DEVICES.get(device_id, {}).get("client_id")
    doc = {"level": level, "message": message, "meta": meta, "device_id": device_id, "client_id": client_id,
           "ts": now_iso()}
    await db.plc_events.insert_one(doc)
    doc.pop("_id", None)
    if client_id:
        await broadcast({"type": "event", "event": doc}, client_id)
    else:
        for ws, user in list(gateway.ws_clients.items()):
            if user["role"] == "superadmin":
                try:
                    await ws.send_json({"type": "event", "event": doc})
                except Exception:
                    gateway.ws_clients.pop(ws, None)


# ============================================================
# Registry, migration, background tasks
# ============================================================
async def load_registry():
    clients = {str(c["_id"]): c["name"] async for c in db.clients.find({})}
    DEVICES.clear()
    async for d in db.devices.find({}):
        DEVICES[d["device_id"]] = {"client_id": d["client_id"], "client_name": clients.get(d["client_id"], "?"),
                                   "name": d["name"], "chambers": d["chambers"], "simulated": d.get("simulated", False),
                                   "chamber_names": d.get("chamber_names", {})}
    THRESHOLDS.clear()
    async for t in db.device_thresholds.find({}):
        THRESHOLDS[(t["device_id"], t["chamber"])] = {"temp_max": t["temp_max"], "co2_max": t["co2_max"]}
    for d in list(gateway.states):
        if d not in DEVICES or len(gateway.states[d]["chambers"]) != DEVICES[d]["chambers"]:
            gateway.states.pop(d, None)


async def migrate_legacy():
    if await db.devices.count_documents({}) or await db.clients.count_documents({}):
        return
    res = await db.clients.insert_one({"name": "Marco Polo", "created_at": now_iso()})
    cid = str(res.inserted_id)
    await db.devices.insert_one({"client_id": cid, "name": "Sterownik 1", "device_id": LEGACY_DEVICE, "chambers": 3,
                                 "simulated": True, "mqtt_username": LEGACY_DEVICE, "mqtt_password_enc": "",
                                 "created_at": now_iso()})
    async for t in db.chamber_thresholds.find({}):
        await db.device_thresholds.update_one({"device_id": LEGACY_DEVICE, "chamber": t["chamber"]},
                                              {"$set": {"temp_max": t["temp_max"], "co2_max": t["co2_max"]}}, upsert=True)
    for coll in ("plc_history", "plc_plant_history", "plc_events"):
        await db[coll].update_many({"device_id": {"$exists": False}}, {"$set": {"device_id": LEGACY_DEVICE}})
    await db.plc_events.update_many({"client_id": {"$exists": False}}, {"$set": {"client_id": cid}})
    alarm = await db.alarm_settings.find_one({"_id": "main"})
    if alarm:
        await db.alarm_settings.insert_one({**alarm, "_id": cid})
    await db.users.update_many({"role": {"$ne": "superadmin"}, "client_id": {"$exists": False}}, {"$set": {"client_id": cid}})


def set_broker_globals(cfg: dict):
    global MQTT_HOST, MQTT_PORT, MQTT_USER, MQTT_PASS, MQTT_TLS, MQTT_PREFIX
    MQTT_HOST, MQTT_PORT = cfg["host"], int(cfg["port"])
    MQTT_USER, MQTT_PASS = cfg.get("username") or "", cfg.get("password") or ""
    MQTT_TLS, MQTT_PREFIX = bool(cfg.get("tls")), cfg["prefix"].strip("/")


async def load_broker():
    doc = await db.broker_config.find_one({"_id": "main"})
    if doc:
        doc["password"] = decrypt_secret(doc.get("password_enc", ""))
        set_broker_globals(doc)


MQTT_DYNSEC = os.environ.get("MQTT_DYNSEC") == "1"  # self-hosted Mosquitto with dynamic-security plugin


def dynsec(commands: list):
    """Provision per-device broker accounts (Mosquitto dynamic security). No-op on external brokers."""
    if MQTT_DYNSEC and gateway.mc:
        gateway.mc.publish("$CONTROL/dynamic-security/v1", json.dumps({"commands": commands}), qos=1)


def dynsec_add_device(device_id: str, password: str):
    role = f"dev-{device_id}"
    dynsec([
        {"command": "createRole", "rolename": role, "acls": [
            {"acltype": "publishClientSend", "topic": state_topic(device_id), "allow": True},
            {"acltype": "subscribePattern", "topic": command_topic(device_id), "allow": True},
            {"acltype": "publishClientReceive", "topic": command_topic(device_id), "allow": True}]},
        {"command": "deleteClient", "username": device_id},
        {"command": "createClient", "username": device_id, "password": password, "roles": [{"rolename": role}]},
    ])


def dynsec_remove_device(device_id: str):
    dynsec([{"command": "deleteClient", "username": device_id}, {"command": "deleteRole", "rolename": f"dev-{device_id}"}])


def is_public_host(host: str, port: int) -> bool:
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        return False
    return bool(infos) and all(ipaddress.ip_address(i[4][0]).is_global for i in infos)


async def history_sampler():
    while True:
        await asyncio.sleep(SAMPLE_S)
        ts = now_iso()
        for device_id, st in list(gateway.states.items()):
            if not gateway.is_online(device_id):
                continue
            docs = [{"device_id": device_id, "chamber": ch["id"], **{k: ch[k] for k in NUM_FIELDS if k != "setpoint"},
                     "ts": ts} for ch in st["chambers"]]
            try:
                await db.plc_history.insert_many(docs)
                if st.get("plant"):
                    await db.plc_plant_history.insert_one({"device_id": device_id, "power_kw": st["plant"].get("power_kw"),
                                                           "water_lpm": st["plant"].get("water_lpm"), "ts": ts})
            except Exception as e:
                logger.warning("history insert failed: %s", e)


alarm_active: dict = {}  # "device:chamber" -> last notification epoch


async def ws_revalidator():
    """Drop WS sessions whose user was deleted or changed role/client/password."""
    while True:
        await asyncio.sleep(30)
        for ws, u in list(gateway.ws_clients.items()):
            cur = await db.users.find_one({"_id": u["_id"]})
            if not cur or any(cur.get(k) != u.get(k) for k in ("role", "client_id", "tv")):
                gateway.ws_clients.pop(ws, None)
                try:
                    await ws.close(code=4401)
                except Exception:
                    pass


async def save_alarm_state():
    await db.alarm_state.update_one({"_id": "main"}, {"$set": {"active": alarm_active}}, upsert=True)


async def send_alarm(client_id: str, subject: str, body: str, kind: str):
    cfg = await db.alarm_settings.find_one({"_id": client_id}) or {}
    recipients = cfg.get("recipients", []) if cfg.get("enabled", True) else []
    if not recipients:
        return
    ts = now_iso()
    results = await asyncio.gather(*[asyncio.to_thread(notify.deliver, r["type"], r["value"], subject, body)
                                     for r in recipients])
    await db.alarm_notifications.insert_many([
        {"client_id": client_id, "ts": ts, "kind": kind, "channel": r["type"], "to": r["value"], "subject": subject,
         "body": body, "status": st, "error": err} for r, (st, err) in zip(recipients, results)])
    sent = sum(st == "sent" for st, _ in results)
    failed = [r["value"] for r, (st, _) in zip(recipients, results) if st == "failed"]
    logger.info("ALARM NOTIFY %s -> %s", subject, [(r["value"], st) for r, (st, _) in zip(recipients, results)])
    await log_event("warning" if failed else "info",
                    f"Powiadomienie: wysłano {sent}/{len(recipients)}" + (f", błąd: {', '.join(failed)}" if failed else "")
                    + f" – {subject}", {"kind": kind}, client_id=client_id)


async def alarm_notifier():
    doc = await db.alarm_state.find_one({"_id": "main"}) or {}
    alarm_active.update({k: v for k, v in doc.get("active", {}).items() if ":" in k})
    while True:
        await asyncio.sleep(5)
        now = time.time()
        try:
            for device_id, st in list(gateway.states.items()):
                if not gateway.is_online(device_id) or device_id not in DEVICES:
                    continue
                cid = DEVICES[device_id]["client_id"]
                for ch in st["chambers"]:
                    key, name = f"{device_id}:{ch['id']}", f"{dev_label(device_id)} – {ch_name(device_id, ch['id'])}"
                    last = alarm_active.get(key)
                    if ch.get("alarm"):
                        if last is None or now - last >= ALARM_REMIND_S:
                            alarm_active[key] = now
                            await save_alarm_state()
                            subj = f"ALARM: {name}" if last is None else f"PRZYPOMNIENIE – ALARM trwa: {name}"
                            await send_alarm(cid, subj, alarm_reason(ch), "alarm" if last is None else "reminder")
                    elif last is not None:
                        alarm_active.pop(key)
                        await save_alarm_state()
                        await send_alarm(cid, f"Koniec alarmu: {name}",
                                         f"Temp {ch['temp']}°C, CO₂ {int(ch['co2'])} ppm", "cleared")
        except Exception as e:
            logger.warning("alarm notifier failed: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    gateway.loop = asyncio.get_running_loop()
    auth.init(db)
    await auth.setup()
    await migrate_legacy()
    await migrate_slugs()
    await db.clients.create_index("slug", unique=True, partialFilterExpression={"slug": {"$type": "string"}})
    await load_broker()
    await load_registry()
    await db.plc_history.create_index([("device_id", 1), ("ts", 1)])
    await db.plc_plant_history.create_index([("device_id", 1), ("ts", 1)])
    await db.devices.create_index("device_id", unique=True)
    gateway.mqtt_start()
    sims.sync()
    tasks = [asyncio.create_task(history_sampler()), asyncio.create_task(alarm_notifier()),
             asyncio.create_task(ws_revalidator())]
    yield
    for t in tasks:
        t.cancel()
    sims.stop_all()
    gateway.mqtt_stop()
    client.close()


app = FastAPI(lifespan=lifespan)
api = APIRouter(prefix="/api")


# ============================================================
# Access helpers
# ============================================================
def visible(user: dict, device_id: str) -> bool:
    d = DEVICES.get(device_id)
    return bool(d) and (user["role"] == "superadmin" or d["client_id"] == user.get("client_id"))


def device_or_404(user: dict, device_id: str) -> dict:
    if not visible(user, device_id):
        raise HTTPException(404, "Device not found")
    return DEVICES[device_id]


def client_scope(user: dict, client_id: Optional[str]) -> str:
    if user["role"] == "superadmin":
        if not client_id or not ObjectId.is_valid(client_id):
            raise HTTPException(422, "client_id required")
        return client_id
    return user.get("client_id")


def device_view(device_id: str, user: dict) -> dict:
    d = DEVICES[device_id]
    out = {"device_id": device_id, "name": d["name"], "client_id": d["client_id"], "client_name": d["client_name"],
           "chambers": d["chambers"], "chamber_names": d["chamber_names"], "simulated": d["simulated"],
           "online": gateway.is_online(device_id),
           "state": gateway.states.get(device_id)}
    if user["role"] == "superadmin":
        out.update({"state_topic": state_topic(device_id), "command_topic": command_topic(device_id)})
    return out


# ============================================================
# Models
# ============================================================
class CommandIn(BaseModel):
    type: str = Field(pattern=r"^(set_setpoint|chamber_power|set_mode|set_vent)$")
    chamber: int = Field(ge=0, le=9)
    value: Any = None


class ThresholdIn(BaseModel):
    temp_max: float = Field(ge=-20, le=60)
    co2_max: float = Field(ge=300, le=20000)


class BrokerIn(BaseModel):
    host: str = Field(min_length=1, max_length=255, pattern=r"^[A-Za-z0-9.\-]+$")
    port: int = Field(ge=1, le=65535)
    username: str = Field(default="", max_length=128)
    password: Optional[str] = Field(default=None, max_length=256)
    tls: bool = False
    prefix: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_\-/]+$")


class ClientIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class ClientPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    display_name: Optional[str] = Field(default=None, max_length=40)
    slug: Optional[str] = Field(default=None, max_length=40, pattern=r"^([a-z0-9][a-z0-9-]{1,39})?$")
    theme: Optional[str] = Field(default=None, pattern=THEME_RX)


class DeviceIn(BaseModel):
    client_id: str
    name: str = Field(min_length=1, max_length=80)
    device_id: str = Field(min_length=3, max_length=48, pattern=r"^[a-z0-9][a-z0-9_\-]*$")
    chambers: int = Field(ge=1, le=10)
    simulated: bool = False


class DevicePatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    simulated: Optional[bool] = None


class Recipient(BaseModel):
    type: str = Field(pattern=r"^(email|sms)$")
    value: str = Field(min_length=3, max_length=254)


class AlarmSettingsIn(BaseModel):
    enabled: bool = True
    recipients: List[Recipient] = Field(default_factory=list, max_length=20)


EMAIL_RX = r"^[^@\s;,]+@[^@\s;,]+\.[^@\s;,]+$"
PHONE_RX = r"^\+?[0-9]{9,15}$"


# ============================================================
# Routes
# ============================================================
@api.get("/")
async def root():
    return {"message": "Fatek MQTT piggery gateway"}


@api.get("/health")
async def health(user: dict = Depends(require("viewer"))):
    return {"ok": True, "broker_connected": gateway.connected}


@api.get("/config")
async def get_config(user: dict = Depends(require("viewer"))):
    cfg = {"broker_host": MQTT_HOST, "broker_port": MQTT_PORT, "prefix": MQTT_PREFIX, "tls": MQTT_TLS}
    if user["role"] == "superadmin":
        cfg.update({"username": MQTT_USER, "has_password": bool(MQTT_PASS)})
    return cfg


@api.put("/broker")
async def set_broker(body: BrokerIn, user: dict = Depends(require("superadmin"))):
    cfg = body.model_dump()
    if not MQTT_DYNSEC and not await asyncio.to_thread(is_public_host, cfg["host"], cfg["port"]):
        raise HTTPException(422, "Broker host must resolve to a public address")
    if cfg["password"] is None:
        cfg["password"] = MQTT_PASS
    stored = {k: v for k, v in cfg.items() if k != "password"}
    stored["password_enc"] = encrypt_secret(cfg["password"])
    await db.broker_config.update_one({"_id": "main"}, {"$set": stored, "$unset": {"password": ""}}, upsert=True)
    await asyncio.to_thread(gateway.mqtt_stop)
    set_broker_globals(cfg)
    gateway.states.clear()
    gateway.last_seen.clear()
    gateway.mqtt_start()
    await asyncio.to_thread(sims.restart_mqtt)
    await log_event("info", f"Zmieniono broker: {MQTT_HOST}:{MQTT_PORT}", {"user": user["email"]})
    return await get_config(user)


@api.get("/clients")
async def list_clients(user: dict = Depends(require("superadmin"))):
    out = []
    async for c in db.clients.find({}).sort("name", 1):
        cid = str(c["_id"])
        out.append({"id": cid, "name": c["name"], "devices": sum(1 for d in DEVICES.values() if d["client_id"] == cid),
                    "display_name": c.get("display_name", ""), "theme": c.get("theme", "green"), "slug": c.get("slug", ""),
                    "logo_version": c.get("logo_version") if c.get("logo_path") else None})
    return {"clients": out}


PL_MAP = str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "acelnoszzACELNOSZZ")


async def unique_slug(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.translate(PL_MAP).lower()).strip("-")[:34].strip("-")
    base = base if len(base) >= 2 else "ferma"
    slug, n = base, 2
    while await db.clients.find_one({"slug": slug}):
        slug, n = f"{base}-{n}", n + 1
    return slug


async def migrate_slugs():
    async for c in db.clients.find({"$or": [{"slug": {"$exists": False}}, {"slug": ""}, {"slug": None}]}):
        await db.clients.update_one({"_id": c["_id"]}, {"$set": {"slug": await unique_slug(c.get("name", ""))}})


@api.post("/clients")
async def create_client(body: ClientIn, user: dict = Depends(require("superadmin"))):
    name = body.name.strip()
    slug = await unique_slug(name)
    res = await db.clients.insert_one({"name": name, "slug": slug, "created_at": now_iso()})
    await log_event("info", f"Dodano klienta: {name}", {"user": user["email"]}, client_id=str(res.inserted_id))
    return {"id": str(res.inserted_id), "name": name, "slug": slug, "devices": 0}


async def client_or_404(client_id: str) -> dict:
    c = await db.clients.find_one({"_id": ObjectId(client_id)}) if ObjectId.is_valid(client_id) else None
    if not c:
        raise HTTPException(404, "Client not found")
    return c


@api.patch("/clients/{client_id}")
async def patch_client(client_id: str, body: ClientPatch, user: dict = Depends(require("superadmin"))):
    c = await client_or_404(client_id)
    upd = {k: (v.strip() if isinstance(v, str) else v) for k, v in body.model_dump().items() if v is not None}
    if upd.get("slug") == "" and c.get("slug"):
        upd.pop("slug")
    if upd.get("slug") and await db.clients.find_one({"slug": upd["slug"], "_id": {"$ne": c["_id"]}}):
        raise HTTPException(409, "Link name already used")
    if upd:
        await db.clients.update_one({"_id": c["_id"]}, {"$set": upd})
        await load_registry()
    return {"ok": True}


async def store_logo(file: UploadFile, folder: str) -> tuple:
    data = await file.read(1_000_001)
    if len(data) > 1_000_000:
        raise HTTPException(413, "Logo too large (max 1 MB)")
    try:
        img = Image.open(io.BytesIO(data))
        if img.format not in ("PNG", "JPEG", "WEBP"):
            raise ValueError("format")
        img = img.convert("RGBA")
        img.thumbnail((256, 256))
        buf = io.BytesIO()
        img.save(buf, "PNG")
    except Exception:
        raise HTTPException(422, "Unsupported image (PNG, JPEG or WEBP)")
    res = await asyncio.to_thread(put_object, f"{STORAGE_APP}/logos/{folder}/{uuid.uuid4().hex}.png", buf.getvalue())
    return res["path"], uuid.uuid4().hex[:8]


@api.post("/clients/{client_id}/logo")
async def upload_logo(client_id: str, file: UploadFile = File(...), user: dict = Depends(require("superadmin"))):
    c = await client_or_404(client_id)
    path, version = await store_logo(file, client_id)
    await db.clients.update_one({"_id": c["_id"]}, {"$set": {"logo_path": path, "logo_version": version}})
    return {"ok": True, "logo_version": version}


@api.delete("/clients/{client_id}/logo")
async def delete_logo(client_id: str, user: dict = Depends(require("superadmin"))):
    c = await client_or_404(client_id)
    await db.clients.update_one({"_id": c["_id"]}, {"$unset": {"logo_path": "", "logo_version": ""}})
    return {"ok": True}


@api.get("/clients/{client_id}/logo")
async def get_logo(client_id: str, user: dict = Depends(require("viewer"))):
    if user["role"] != "superadmin" and user.get("client_id") != client_id:
        raise HTTPException(404, "Not found")
    c = await client_or_404(client_id)
    if not c.get("logo_path"):
        raise HTTPException(404, "No logo")
    data = await asyncio.to_thread(get_object, c["logo_path"])
    return Response(content=data, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})


def _square_icon(png: bytes, size: int, bg: str) -> bytes:
    src = Image.open(io.BytesIO(png)).convert("RGBA")
    canvas = Image.new("RGBA", (size, size), bg)
    inner = int(size * 0.8)
    src = src.resize((int(src.width * inner / max(src.size)), int(src.height * inner / max(src.size))), Image.LANCZOS)
    canvas.paste(src, ((size - src.width) // 2, (size - src.height) // 2), src)
    out = io.BytesIO()
    canvas.convert("RGB").save(out, "PNG")
    return out.getvalue()


THEME_BG = {"green": "#0A0A0A", "light": "#F3F5F3", "blue": "#080B12", "amber": "#0C0A07"}


async def client_by_slug(slug: str) -> dict:
    c = await db.clients.find_one({"slug": slug}) if re.match(r"^[a-z0-9][a-z0-9-]{1,39}$", slug or "") else None
    if not c:
        raise HTTPException(404, "Unknown client link")
    return c


@api.get("/public/branding/{slug}")
async def public_branding(slug: str):
    c = await client_by_slug(slug)
    return {"slug": slug, "app_name": c.get("display_name") or None, "theme": c.get("theme", "green"),
            "logo_version": c.get("logo_version") if c.get("logo_path") else None}


@api.get("/public/logo/{slug}")
async def public_logo(slug: str, size: int = 0):
    c = await client_by_slug(slug)
    if not c.get("logo_path"):
        raise HTTPException(404, "No logo")
    data = await asyncio.to_thread(get_object, c["logo_path"])
    if size in (180, 192, 512):
        data = await asyncio.to_thread(_square_icon, data, size, THEME_BG.get(c.get("theme", "green"), "#0A0A0A"))
    return Response(content=data, media_type="image/png", headers={"Cache-Control": "public, max-age=3600"})


@api.get("/public/manifest/{slug}")
async def public_manifest(slug: str):
    c = await client_by_slug(slug)
    name = c.get("display_name") or "Marco Polo Wentylacja"
    v = c.get("logo_version")
    icons = ([{"src": f"/api/public/logo/{slug}?size={s}&v={v}", "sizes": f"{s}x{s}", "type": "image/png", "purpose": "any"}
              for s in (192, 512)] if c.get("logo_path") else await site_icons())
    return manifest(name, f"/?klient={slug}", THEME_BG.get(c.get("theme", "green"), "#0A0A0A"), icons)


def manifest(name: str, start: str, bg: str, icons: list) -> JSONResponse:
    return JSONResponse({"id": start, "name": name, "short_name": name, "lang": "pl", "start_url": start, "scope": "/",
                         "display": "standalone", "orientation": "portrait", "background_color": bg, "theme_color": bg,
                         "icons": icons}, media_type="application/manifest+json")


async def site_icons() -> list:
    doc = await db.site_settings.find_one({"_id": "main"}) or {}
    if doc.get("logo_path"):
        return [{"src": f"/api/public/site/logo?size={s}&v={doc['logo_version']}", "sizes": f"{s}x{s}", "type": "image/png",
                 "purpose": "any"} for s in (192, 512)]
    return [{"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"},
            {"src": "/icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"}]


@api.get("/public/manifest")
async def public_site_manifest():
    return manifest("Marco Polo Wentylacja", "/", "#0A0A0A", await site_icons())


class SiteIn(BaseModel):
    phone: str = Field(default="", max_length=40, pattern=r"^[0-9+ ()-]*$")
    email: str = Field(default="", max_length=254, pattern=r"^([^@\s;,]+@[^@\s;,]+\.[^@\s;,]+)?$")


@api.get("/public/site")
async def public_site():
    doc = await db.site_settings.find_one({"_id": "main"}) or {}
    return {"phone": doc.get("phone", ""), "email": doc.get("email", ""),
            "logo_version": doc.get("logo_version") if doc.get("logo_path") else None}


@api.get("/public/site/logo")
async def public_site_logo(size: int = 0):
    doc = await db.site_settings.find_one({"_id": "main"}) or {}
    if not doc.get("logo_path"):
        raise HTTPException(404, "No logo")
    data = await asyncio.to_thread(get_object, doc["logo_path"])
    if size in (32, 180, 192, 512):
        data = await asyncio.to_thread(_square_icon, data, size, "#0A0A0A")
    return Response(content=data, media_type="image/png", headers={"Cache-Control": "public, max-age=3600"})


@api.post("/site/logo")
async def upload_site_logo(file: UploadFile = File(...), user: dict = Depends(require("superadmin"))):
    path, version = await store_logo(file, "site")
    await db.site_settings.update_one({"_id": "main"}, {"$set": {"logo_path": path, "logo_version": version}}, upsert=True)
    return {"ok": True, "logo_version": version}


@api.delete("/site/logo")
async def delete_site_logo(user: dict = Depends(require("superadmin"))):
    await db.site_settings.update_one({"_id": "main"}, {"$unset": {"logo_path": "", "logo_version": ""}})
    return {"ok": True}


@api.put("/site")
async def put_site(body: SiteIn, user: dict = Depends(require("superadmin"))):
    await db.site_settings.update_one({"_id": "main"}, {"$set": {"phone": body.phone.strip(), "email": body.email.strip()}}, upsert=True)
    return await public_site()


@api.get("/branding")
async def branding(client_id: Optional[str] = None, user: dict = Depends(require("viewer"))):
    cid = client_id if user["role"] == "superadmin" else user.get("client_id")
    c = await db.clients.find_one({"_id": ObjectId(cid)}) if cid and ObjectId.is_valid(cid) else None
    if not c:
        return {"client_id": None, "app_name": None, "theme": "green", "logo_version": None}
    return {"client_id": cid, "app_name": c.get("display_name") or None, "theme": c.get("theme", "green"),
            "logo_version": c.get("logo_version") if c.get("logo_path") else None}


@api.delete("/clients/{client_id}")
async def delete_client(client_id: str, user: dict = Depends(require("superadmin"))):
    if not ObjectId.is_valid(client_id):
        raise HTTPException(404, "Client not found")
    if any(d["client_id"] == client_id for d in DEVICES.values()):
        raise HTTPException(409, "Client still has devices")
    res = await db.clients.delete_one({"_id": ObjectId(client_id)})
    if not res.deleted_count:
        raise HTTPException(404, "Client not found")
    await db.users.delete_many({"client_id": client_id})
    await db.alarm_settings.delete_one({"_id": client_id})
    return {"ok": True}


@api.get("/devices")
async def list_devices(user: dict = Depends(require("viewer"))):
    ids = sorted((d for d in DEVICES if visible(user, d)), key=lambda d: (DEVICES[d]["client_name"], DEVICES[d]["name"]))
    return {"devices": [device_view(d, user) for d in ids]}


@api.post("/devices")
async def create_device(body: DeviceIn, user: dict = Depends(require("superadmin"))):
    if not ObjectId.is_valid(body.client_id) or not await db.clients.find_one({"_id": ObjectId(body.client_id)}):
        raise HTTPException(422, "Unknown client")
    if body.device_id in DEVICES:
        raise HTTPException(409, "Device ID already exists")
    password = secrets.token_urlsafe(18)
    await db.devices.insert_one({**body.model_dump(), "name": body.name.strip(), "mqtt_username": body.device_id,
                                 "mqtt_password_enc": encrypt_secret(password), "created_at": now_iso()})
    await load_registry()
    sims.sync()
    dynsec_add_device(body.device_id, password)
    await log_event("info", f"Dodano sterownik: {dev_label(body.device_id)} ({body.chambers} kom.)",
                    {"user": user["email"]}, body.device_id)
    return {**device_view(body.device_id, user), "mqtt_username": body.device_id, "mqtt_password": password}


@api.get("/devices/{device_id}/credentials")
async def device_credentials(device_id: str, user: dict = Depends(require("superadmin"))):
    d = await db.devices.find_one({"device_id": device_id})
    if not d:
        raise HTTPException(404, "Device not found")
    return {"mqtt_username": d.get("mqtt_username", device_id), "mqtt_password": decrypt_secret(d.get("mqtt_password_enc", "")),
            "state_topic": state_topic(device_id), "command_topic": command_topic(device_id),
            "broker_host": MQTT_HOST, "broker_port": MQTT_PORT, "tls": MQTT_TLS}


@api.patch("/devices/{device_id}")
async def patch_device(device_id: str, body: DevicePatch, user: dict = Depends(require("superadmin"))):
    upd = {k: v for k, v in body.model_dump().items() if v is not None}
    res = await db.devices.update_one({"device_id": device_id}, {"$set": upd})
    if not res.matched_count:
        raise HTTPException(404, "Device not found")
    await load_registry()
    sims.sync()
    return device_view(device_id, user)


@api.delete("/devices/{device_id}")
async def delete_device(device_id: str, user: dict = Depends(require("superadmin"))):
    if device_id not in DEVICES:
        raise HTTPException(404, "Device not found")
    label = dev_label(device_id)
    cid = DEVICES.pop(device_id)["client_id"]
    gateway.states.pop(device_id, None)
    gateway.last_seen.pop(device_id, None)
    sims.sync()
    await db.devices.delete_one({"device_id": device_id})
    dynsec_remove_device(device_id)
    for coll in ("device_thresholds", "plc_history", "plc_plant_history", "plc_events"):
        await db[coll].delete_many({"device_id": device_id})
    for k in [k for k in alarm_active if k.startswith(f"{device_id}:")]:
        alarm_active.pop(k)
    await save_alarm_state()
    await load_registry()
    sims.sync()
    gateway.states.pop(device_id, None)
    await log_event("info", f"Usunięto sterownik: {label}", {"user": user["email"]}, client_id=cid)
    return {"ok": True}


@api.post("/devices/{device_id}/command")
async def device_command(device_id: str, cmd: CommandIn, user: dict = Depends(require("operator"))):
    d = device_or_404(user, device_id)
    if cmd.chamber >= d["chambers"]:
        raise HTTPException(422, "Unknown chamber")
    if cmd.type == "set_setpoint" and (isinstance(cmd.value, bool) or not isinstance(cmd.value, (int, float))):
        raise HTTPException(422, "value must be a number")
    if cmd.type == "set_mode" and cmd.value not in ("auto", "manual"):
        raise HTTPException(422, "value must be auto|manual")
    if cmd.type == "set_vent":
        v = cmd.value
        if not isinstance(v, dict) or not v or any(
                k not in VENT_FIELDS or not _num(x) or not 0 <= x <= 100 for k, x in v.items()):
            raise HTTPException(422, "invalid vent values")
    body = {**cmd.model_dump(), "request_id": uuid.uuid4().hex}
    if not gateway.publish_command(device_id, body):
        raise HTTPException(503, "MQTT publish failed")
    name = f"{d['name']} – {ch_name(device_id, cmd.chamber)}"
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
    await log_event("command", msg, {**body, "user": user["email"]}, device_id)
    return {"queued": True, "request_id": body["request_id"]}


@api.get("/devices/{device_id}/thresholds")
async def get_thresholds(device_id: str, user: dict = Depends(require("viewer"))):
    d = device_or_404(user, device_id)
    return {"thresholds": [{"chamber": i, **th_for(device_id, i)} for i in range(d["chambers"])]}


@api.put("/devices/{device_id}/thresholds/{chamber}")
async def set_threshold(device_id: str, chamber: int, body: ThresholdIn, user: dict = Depends(require("operator"))):
    d = device_or_404(user, device_id)
    if not 0 <= chamber < d["chambers"]:
        raise HTTPException(404, "unknown chamber")
    th = {"temp_max": round(body.temp_max, 1), "co2_max": float(round(body.co2_max))}
    THRESHOLDS[(device_id, chamber)] = th
    await db.device_thresholds.update_one({"device_id": device_id, "chamber": chamber}, {"$set": th}, upsert=True)
    await log_event("info", f"{d['name']} – {ch_name(device_id, chamber)}: progi temp ≤ {th['temp_max']}°C, CO₂ ≤ {int(th['co2_max'])} ppm",
                    {"user": user["email"]}, device_id)
    st = gateway.states.get(device_id)
    if st:
        prev = copy.deepcopy(st)
        annotate(device_id, st)
        gateway.detect_alarms(device_id, prev, st)
    return {"ok": True, "thresholds": th}


class ChamberNameIn(BaseModel):
    name: str = Field(default="", max_length=30)


@api.put("/devices/{device_id}/chambers/{chamber}/name")
async def rename_chamber(device_id: str, chamber: int, body: ChamberNameIn, user: dict = Depends(require("admin"))):
    d = device_or_404(user, device_id)
    if not 0 <= chamber < d["chambers"]:
        raise HTTPException(404, "unknown chamber")
    name, old = " ".join(body.name.split()), ch_name(device_id, chamber)
    op = {"$set": {f"chamber_names.{chamber}": name}} if name else {"$unset": {f"chamber_names.{chamber}": ""}}
    await db.devices.update_one({"device_id": device_id}, op)
    await load_registry()
    st = gateway.states.get(device_id)
    if st:
        st["chambers"][chamber]["name"] = ch_name(device_id, chamber)
    await log_event("info", f"{d['name']}: zmieniono nazwę „{old}” → „{ch_name(device_id, chamber)}”", {"user": user["email"]}, device_id)
    return {"ok": True, "name": ch_name(device_id, chamber)}


@api.get("/devices/{device_id}/history")
async def history(device_id: str, hours: int = 3, user: dict = Depends(require("viewer"))):
    device_or_404(user, device_id)
    since = (datetime.now(timezone.utc) - timedelta(hours=max(1, min(24, hours)))).isoformat()
    q = {"device_id": device_id, "ts": {"$gte": since}}
    docs = await db.plc_history.find(q, {"_id": 0}).sort("ts", 1).to_list(20000)
    out: dict = {}
    for doc in docs:
        out.setdefault(str(doc["chamber"]), []).append(doc)
    plant = await db.plc_plant_history.find(q, {"_id": 0}).sort("ts", 1).to_list(3000)
    return {"history": out, "plant": plant}


@api.get("/devices/{device_id}/usage/daily")
async def usage_daily(device_id: str, days: int = 7, user: dict = Depends(require("viewer"))):
    device_or_404(user, device_id)
    days = max(1, min(60, days))
    start = (datetime.now(timezone.utc) - timedelta(days=days - 1)).date()
    rows = await db.plc_plant_history.aggregate([
        {"$match": {"device_id": device_id, "ts": {"$gte": start.isoformat()}}},
        {"$group": {"_id": {"$substr": ["$ts", 0, 10]}, "p": {"$sum": "$power_kw"}, "w": {"$sum": "$water_lpm"}}},
    ]).to_list(100)
    by = {r["_id"]: r for r in rows}
    out = []
    for i in range(days):
        day = (start + timedelta(days=i)).isoformat()
        r = by.get(day, {"p": 0, "w": 0})
        out.append({"date": day, "kwh": round(r["p"] * SAMPLE_S / 3600, 2),
                    "water_m3": round(r["w"] * SAMPLE_S / 60 / 1000, 3)})
    return {"days": out}


@api.get("/devices/{device_id}/history/csv")
async def history_csv(device_id: str, chamber: int, hours: int = 24, user: dict = Depends(require("viewer"))):
    d = device_or_404(user, device_id)
    if not 0 <= chamber < d["chambers"]:
        raise HTTPException(404, "unknown chamber")
    hours = max(1, min(24 * 31, hours))
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    cursor = db.plc_history.find({"device_id": device_id, "chamber": chamber, "ts": {"$gte": since}}, {"_id": 0}).sort("ts", 1)

    def fmt(v):
        if v is None:
            return ""
        if not _num(v):
            v = str(v)
            return ("'" + v if v[:1] in ("=", "+", "-", "@", "\t", "\r") else v).replace(";", " ")
        return str(v).replace(".", ",")

    async def gen():
        yield "\ufeffczas;temperatura_C;wilgotnosc_%;co2_ppm;kurtyna_L_zamkn_%;kurtyna_P_zamkn_%;komin_otw_%\n"
        async for doc in cursor:
            cl, cr = doc.get("curtain_left"), doc.get("curtain_right")
            ts = datetime.fromisoformat(doc["ts"]).astimezone(ZoneInfo("Europe/Warsaw")).strftime("%Y-%m-%d %H:%M:%S")
            yield ";".join([ts, fmt(doc.get("temp")), fmt(doc.get("humidity")), fmt(doc.get("co2")),
                            fmt(None if cl is None else round(100 - cl, 1)),
                            fmt(None if cr is None else round(100 - cr, 1)), fmt(doc.get("chimney"))]) + "\n"

    fname = f"{device_id}_komora{chamber + 1}_{hours}h_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    return StreamingResponse(gen(), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@api.get("/events")
async def events(device_id: Optional[str] = None, limit: int = 100, user: dict = Depends(require("viewer"))):
    q: dict = {} if user["role"] == "superadmin" else {"client_id": user.get("client_id")}
    if device_id:
        d = device_or_404(user, device_id)
        q = {"client_id": d["client_id"], "$or": [{"device_id": device_id}, {"device_id": None}]}
    docs = await db.plc_events.find(q, {"_id": 0}).sort("ts", -1).to_list(max(1, min(500, limit)))
    return {"events": docs}


@api.get("/alarm-settings")
async def get_alarm_settings(client_id: Optional[str] = None, user: dict = Depends(require("admin"))):
    cid = client_scope(user, client_id)
    cfg = await db.alarm_settings.find_one({"_id": cid}) or {}
    sent = await db.alarm_notifications.find({"client_id": cid}, {"_id": 0}).sort("ts", -1).to_list(10)
    return {"client_id": cid, "enabled": cfg.get("enabled", True), "recipients": cfg.get("recipients", []),
            "email_configured": notify.email_configured(), "sms_configured": notify.sms_configured(), "reminder_min": ALARM_REMIND_S // 60, "recent": sent}


@api.put("/alarm-settings")
async def put_alarm_settings(body: AlarmSettingsIn, client_id: Optional[str] = None, user: dict = Depends(require("admin"))):
    cid = client_scope(user, client_id)
    recs = []
    for r in body.recipients:
        v = r.value.strip().lower() if r.type == "email" else re.sub(r"[\s-]", "", r.value)
        if not re.match(EMAIL_RX if r.type == "email" else PHONE_RX, v):
            raise HTTPException(422, f"invalid {r.type}: {r.value}")
        if not any(x["type"] == r.type and x["value"] == v for x in recs):
            recs.append({"type": r.type, "value": v})
    await db.alarm_settings.update_one({"_id": cid}, {"$set": {"enabled": body.enabled, "recipients": recs}}, upsert=True)
    await log_event("info", f"Powiadomienia o alarmach {'WŁ.' if body.enabled else 'WYŁ.'}, odbiorcy: {len(recs)}",
                    {"user": user["email"]}, client_id=cid)
    return await get_alarm_settings(cid, user)


@api.post("/alarm-settings/test")
async def test_alarm(client_id: Optional[str] = None, user: dict = Depends(require("admin"))):
    cid = client_scope(user, client_id)
    cfg = await db.alarm_settings.find_one({"_id": cid}) or {}
    if not cfg.get("enabled", True) or not cfg.get("recipients"):
        raise HTTPException(409, "Notifications disabled or no recipients")
    await send_alarm(cid, "TEST: Marco Polo Wentylacja", f"Powiadomienie testowe wysłane przez {user['email']}", "test")
    return await get_alarm_settings(cid, user)


def origin_allowed(origin: Optional[str], host: Optional[str]) -> bool:
    if not origin:
        return True
    origin = origin.rstrip("/")
    return origin == FRONTEND_URL or (bool(host) and origin.split("://", 1)[-1] == host)


@app.websocket("/api/ws")
async def websocket_endpoint(ws: WebSocket):
    user = await auth.user_from_token(ws.cookies.get("access_token"))
    if not user or not origin_allowed(ws.headers.get("origin"), ws.headers.get("host")):
        await ws.close(code=4401)
        return
    await ws.accept()
    gateway.ws_clients[ws] = user
    for device_id, st in list(gateway.states.items()):
        if visible(user, device_id):
            await ws.send_json({"type": "state", "payload": st})
    try:
        while True:
            await ws.receive_text()
    except Exception:
        pass
    finally:
        gateway.ws_clients.pop(ws, None)


@app.middleware("http")
async def origin_guard(request: Request, call_next):
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        if not origin_allowed(request.headers.get("origin"), request.headers.get("host")):
            return JSONResponse({"detail": "Forbidden origin"}, status_code=403)
    return await call_next(request)


app.include_router(auth.router)
app.include_router(api)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=[FRONTEND_URL],
    allow_methods=["*"],
    allow_headers=["*"],
)

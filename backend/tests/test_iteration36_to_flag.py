# Iteration 36: to_flag normalisation of on/heating/mode (0/1, "0"/"1", "auto"/"manual", true/false) via real MQTT + set_mode command
import json
import os
import sys
import time
import uuid

import paho.mqtt.client as mqtt
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
SA = ("admin@chlewnia.pl", "Wentylacja!2026")
KOW = "6ad7dcc3261e5ba3c23315b7"
H = {"Origin": BASE_URL}
DEV = f"flag36{uuid.uuid4().hex[:4]}"


def payload(tag):
    base = dict(temp=20.5, setpoint=21.0, humidity=65, co2=1100, curtain_left=40, curtain_right=40, chimney=30)
    ch = [
        {"id": 0, "on": 0, "heating": 0, "mode": "0", **base},
        {"id": 1, "on": "1", "heating": 1, "mode": "1", **base},
        {"id": 2, "on": True, "heating": "0", "mode": "auto", **base},
    ]
    return json.dumps({"model": f"FBs-{tag}", "chambers": ch, "plant": {"power_kw": 3.2}})


@pytest.fixture(scope="module")
def sa():
    s = requests.Session()
    s.headers.update(H)
    r = s.post(f"{API}/auth/login", json={"email": SA[0], "password": SA[1]})
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def dev(sa):
    r = sa.post(f"{API}/devices", json={"client_id": KOW, "name": "TEST_Flag36", "device_id": DEV, "chambers": 3, "simulated": False})
    assert r.status_code == 200, r.text
    topic = sa.get(f"{API}/devices/{DEV}/mqtt-debug").json()["state_topic"]
    mc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"it36-{uuid.uuid4().hex[:6]}")
    mc.connect("broker.hivemq.com", 1883, 30)
    mc.loop_start()
    time.sleep(1)
    tag = uuid.uuid4().hex[:8]
    mc.publish(topic, payload(tag), qos=1).wait_for_publish(5)
    end = time.time() + 15
    while time.time() < end:
        m = sa.get(f"{API}/devices/{DEV}/mqtt-debug").json().get("last_message")
        if m and tag in m["payload"]:
            break
        time.sleep(0.5)
    yield m
    mc.loop_stop()
    mc.disconnect()
    assert sa.delete(f"{API}/devices/{DEV}").status_code == 200


def state(sa, d=DEV):
    return {x["device_id"]: x for x in sa.get(f"{API}/devices").json()["devices"]}[d]


class TestToFlag:
    def test_01_message_accepted(self, sa, dev):
        assert dev and dev["ok"] is True, dev

    def test_02_chamber0_off(self, sa, dev):
        c = state(sa)["state"]["chambers"][0]
        assert c["on"] is False and c["heating"] is False and c["mode"] == "auto", c

    def test_03_chamber1_string_one(self, sa, dev):
        c = state(sa)["state"]["chambers"][1]
        assert c["on"] is True and c["heating"] is True and c["mode"] == "manual", c

    def test_04_chamber2_heating_string_zero(self, sa, dev):
        c = state(sa)["state"]["chambers"][2]
        assert c["on"] is True and c["heating"] is False and c["mode"] == "auto", c

    def test_05_set_mode_command_queued(self, sa, dev):
        r = sa.post(f"{API}/devices/{DEV}/command", json={"type": "set_mode", "chamber": 2, "value": "manual"})
        assert r.status_code == 200, r.text
        assert r.json()["queued"] is True

    def test_06_set_mode_invalid(self, sa, dev):
        r = sa.post(f"{API}/devices/{DEV}/command", json={"type": "set_mode", "chamber": 2, "value": "x"})
        assert r.status_code == 422


class TestToFlagUnit:
    def test_07_to_flag_unit(self):
        sys.path.insert(0, "/app/backend")
        from server import to_flag
        for v in (True, 1, "1", "true", "TRUE", " on ", "manual", "Manual", 1.0):
            assert to_flag(v) is True, v
        for v in (False, 0, "0", "", "false", "off", "auto", None, 0.0, float("nan"), "2"):
            assert to_flag(v) is False, v

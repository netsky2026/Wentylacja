# Iteration 33: Fatek native MQTT format ({"d": {...}, "error": [], "ts": ...}) – rejection reasons, merge, scaling, regression
import json
import os
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
DEV = os.environ.get("FATEK_DEV", f"fatektest{uuid.uuid4().hex[:4]}")

FULL = {"temp_x10": [194, 214, 229], "setpoint_x10": [200, 220, 240], "humidity": [70, 71, 72], "co2": [1200, 1300, 1400],
        "curtain_left": [40, 40, 40], "curtain_right": [40, 40, 40], "chimney": [30, 30, 30], "mode": [0, 0, 1],
        "water_total_l": [100, 200, 300], "power_kwh_x10": [1672]}


@pytest.fixture(scope="module")
def sa():
    s = requests.Session()
    s.headers.update(H)
    r = s.post(f"{API}/auth/login", json={"email": SA[0], "password": SA[1]})
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def device(sa):
    r = sa.post(f"{API}/devices", json={"client_id": KOW, "name": "TEST_Fatek", "device_id": DEV, "chambers": 3, "simulated": False})
    assert r.status_code == 200, r.text
    yield r.json()
    d = sa.delete(f"{API}/devices/{DEV}")
    assert d.status_code == 200
    assert sa.get(f"{API}/devices/{DEV}/mqtt-debug").status_code == 404


@pytest.fixture(scope="module")
def pub(sa, device):
    topic = sa.get(f"{API}/devices/{DEV}/mqtt-debug").json()["state_topic"]
    mc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"it33-{uuid.uuid4().hex[:6]}")
    mc.connect("broker.hivemq.com", 1883, 30)
    mc.loop_start()
    time.sleep(1)

    def send(d):
        mc.publish(topic, json.dumps({"d": d, "error": [], "ts": "2026-01-09T09:50:06.858"}), qos=1).wait_for_publish(5)
    yield send
    mc.loop_stop()
    mc.disconnect()


def wait_msg(sa, pred, timeout=8):
    end = time.time() + timeout
    m = None
    while time.time() < end:
        m = sa.get(f"{API}/devices/{DEV}/mqtt-debug").json().get("last_message")
        if m and pred(m):
            return m
        time.sleep(0.4)
    return m


def marker(m, s):
    return m and s in m["payload"]


class TestFatekNative:
    def test_01_dataitem0_rejected(self, sa, pub):
        pub({"DataItem0": [4]})
        m = wait_msg(sa, lambda m: "DataItem0" in m["payload"])
        assert m and "DataItem0" in m["payload"], m
        assert m["ok"] is False
        assert m["error"].startswith("Fatek: brak tagów"), m["error"]
        assert "Nieznane tagi: DataItem0" in m["error"]
        dbg = sa.get(f"{API}/devices/{DEV}/mqtt-debug").json()
        assert dbg["online"] is False

    def test_02_split_first_rejected_missing(self, sa, pub):
        pub({"temp_x10": FULL["temp_x10"], "setpoint_x10": FULL["setpoint_x10"]})
        m = wait_msg(sa, lambda m: "setpoint_x10" in m["payload"] and "humidity" not in m["payload"])
        assert m["ok"] is False, m
        for t in ("humidity", "co2", "curtain_left", "curtain_right", "chimney"):
            assert t in m["error"], m["error"]
        assert "temp," not in m["error"] and "setpoint" not in m["error"]

    def test_03_split_second_accepted(self, sa, pub):
        rest = {k: v for k, v in FULL.items() if k not in ("temp_x10", "setpoint_x10")}
        pub(rest)
        m = wait_msg(sa, lambda m: "humidity" in m["payload"] and "temp_x10" not in m["payload"])
        assert m["ok"] is True and m["error"] is None, m
        devs = {d["device_id"]: d for d in sa.get(f"{API}/devices").json()["devices"]}
        st = devs[DEV]["state"]
        assert [c["temp"] for c in st["chambers"]] == [19.4, 21.4, 22.9]

    def test_04_full_repeated_online_and_values(self, sa, pub):
        for _ in range(3):
            pub(FULL)
            time.sleep(2)
        m = wait_msg(sa, lambda m: "temp_x10" in m["payload"] and "humidity" in m["payload"])
        assert m["ok"] is True, m
        dbg = sa.get(f"{API}/devices/{DEV}/mqtt-debug").json()
        assert dbg["online"] is True
        d = {d["device_id"]: d for d in sa.get(f"{API}/devices").json()["devices"]}[DEV]
        assert d["online"] is True
        st = d["state"]
        assert [c["temp"] for c in st["chambers"]] == [19.4, 21.4, 22.9]
        assert [c["setpoint"] for c in st["chambers"]] == [20.0, 22.0, 24.0]
        assert [c["mode"] for c in st["chambers"]] == ["auto", "auto", "manual"]
        assert [c["water_total_l"] for c in st["chambers"]] == [100, 200, 300]
        assert st["plant"]["power_kwh"] == pytest.approx(167.2)
        print("STATE", json.dumps(st)[:800])

    def test_05_short_array_rejected(self, sa, pub):
        pub({"temp": [20]})
        m = wait_msg(sa, lambda m: '"temp": [20]' in m["payload"])
        assert m["ok"] is False, m
        assert "mają mniej wartości niż komór (3)" in m["error"], m["error"]

    def test_06_string_values_rejected(self, sa, pub):
        pub({"temp": ["a", "b", "c"]})
        m = wait_msg(sa, lambda m: '"a"' in m["payload"])
        assert m["ok"] is False, m
        assert "muszą zawierać liczby" in m["error"], m["error"]

    def test_07_ui_hold(self, sa, pub):
        # restore a good state at the end
        pub({**FULL, "temp_x10": [194, 214, 229]})
        m = wait_msg(sa, lambda m: '"temp_x10": [194' in m["payload"])
        assert m["ok"] is True, m


class TestRegression:
    def test_kowalski_a_standard_online(self, sa):
        d = sa.get(f"{API}/devices/kowalski-a/mqtt-debug").json()
        assert d["online"] is True
        assert d["last_message"]["ok"] is True
        assert '"chambers"' in d["last_message"]["payload"]

    def test_kowalski_a_ping_ack(self, sa):
        r = sa.post(f"{API}/devices/kowalski-a/ping")
        assert r.status_code == 200
        rid = r.json()["request_id"]
        end = time.time() + 8
        while time.time() < end:
            p = sa.get(f"{API}/devices/kowalski-a/mqtt-debug").json().get("ping") or {}
            if p.get("request_id") == rid and p.get("ack_ts"):
                return
            time.sleep(0.5)
        pytest.fail("no ping ack")

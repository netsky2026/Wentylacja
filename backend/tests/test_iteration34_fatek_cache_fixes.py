# Iteration 34: Fatek native format – stale-cache fixes (unknown-only rejection, delete clears cache, short array no overwrite, TTL 60s) + regression
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
DEV = f"fatek34{uuid.uuid4().hex[:4]}"

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


def create(sa):
    r = sa.post(f"{API}/devices", json={"client_id": KOW, "name": "TEST_Fatek34", "device_id": DEV, "chambers": 3, "simulated": False})
    assert r.status_code == 200, r.text


@pytest.fixture(scope="module")
def device(sa):
    create(sa)
    yield
    sa.delete(f"{API}/devices/{DEV}")


@pytest.fixture(scope="module")
def pub(sa, device):
    topic = sa.get(f"{API}/devices/{DEV}/mqtt-debug").json()["state_topic"]
    mc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"it34-{uuid.uuid4().hex[:6]}")
    mc.connect("broker.hivemq.com", 1883, 30)
    mc.loop_start()
    time.sleep(1)

    def send(d, tag=None):
        body = {"d": d, "error": [], "ts": tag or uuid.uuid4().hex}
        mc.publish(topic, json.dumps(body), qos=1).wait_for_publish(5)
        return body["ts"]
    yield send
    mc.loop_stop()
    mc.disconnect()


def dbg(sa):
    return sa.get(f"{API}/devices/{DEV}/mqtt-debug").json()


def wait_ts(sa, ts, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        m = dbg(sa).get("last_message")
        if m and ts in m["payload"]:
            return m
        time.sleep(0.4)
    pytest.fail(f"message {ts} not received")


def state(sa):
    return {d["device_id"]: d for d in sa.get(f"{API}/devices").json()["devices"]}[DEV]


class TestFatekFixes:
    def test_01_full_accepted_online(self, sa, pub):
        m = wait_ts(sa, pub(FULL))
        assert m["ok"] is True, m
        d = state(sa)
        assert d["online"] is True
        st = d["state"]
        assert [c["temp"] for c in st["chambers"]] == [19.4, 21.4, 22.9]
        assert [c["mode"] for c in st["chambers"]] == ["auto", "auto", "manual"]
        assert st["plant"]["power_kwh"] == pytest.approx(167.2)

    def test_02_unknown_only_rejected_after_full_and_goes_offline(self, sa, pub):
        m = wait_ts(sa, pub({"DataItem0": [4]}))
        assert m["ok"] is False, m
        assert m["error"].startswith("Fatek: brak znanych tagów (otrzymane: DataItem0)"), m["error"]
        t0 = time.time()
        while time.time() - t0 < 14:
            pub({"DataItem0": [4]})
            time.sleep(1)
        assert dbg(sa)["online"] is False
        assert state(sa)["online"] is False

    def test_03_short_array_does_not_overwrite_cache(self, sa, pub):
        assert wait_ts(sa, pub(FULL))["ok"] is True
        m = wait_ts(sa, pub({"temp": [20]}))
        assert m["ok"] is False
        assert "mniej wartości niż komór (3)" in m["error"], m["error"]
        m = wait_ts(sa, pub({"co2": [900, 901, 902]}))
        assert m["ok"] is True, m
        st = state(sa)["state"]
        assert [c["temp"] for c in st["chambers"]] == [19.4, 21.4, 22.9]
        assert [c["co2"] for c in st["chambers"]] == [900, 901, 902]

    def test_04_strings_rejected(self, sa, pub):
        m = wait_ts(sa, pub({"temp": ["a", "b", "c"]}))
        assert m["ok"] is False and "muszą zawierać liczby" in m["error"], m

    def test_05_split_merge(self, sa, pub):
        sa.delete(f"{API}/devices/{DEV}")  # fresh cache
        create(sa)
        m = wait_ts(sa, pub({"temp_x10": FULL["temp_x10"], "setpoint_x10": FULL["setpoint_x10"]}))
        assert m["ok"] is False and "humidity" in m["error"] and "setpoint" not in m["error"], m
        rest = {k: v for k, v in FULL.items() if k not in ("temp_x10", "setpoint_x10")}
        m = wait_ts(sa, pub(rest))
        assert m["ok"] is True, m
        assert [c["temp"] for c in state(sa)["state"]["chambers"]] == [19.4, 21.4, 22.9]

    def test_06_delete_clears_cache_and_debug(self, sa, pub):
        assert sa.delete(f"{API}/devices/{DEV}").status_code == 200
        assert sa.get(f"{API}/devices/{DEV}/mqtt-debug").status_code == 404
        create(sa)
        d = dbg(sa)
        assert d["last_message"] is None, d["last_message"]
        assert d["online"] is False
        m = wait_ts(sa, pub({"co2": [1, 2, 3]}))
        assert m["ok"] is False, m
        assert "brak tagów: temp, setpoint" in m["error"], m["error"]

    def test_07_ttl_60s_expiry(self, sa, pub):
        assert wait_ts(sa, pub(FULL))["ok"] is True
        assert wait_ts(sa, pub({"co2": [5, 6, 7]}))["ok"] is True
        time.sleep(62)
        m = wait_ts(sa, pub({"co2": [5, 6, 7]}))
        assert m["ok"] is False, m
        for t in ("temp", "setpoint", "humidity", "curtain_left", "curtain_right", "chimney"):
            assert t in m["error"], m["error"]
        # full message restores
        assert wait_ts(sa, pub(FULL))["ok"] is True


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

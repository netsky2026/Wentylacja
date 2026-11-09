# Iteration 35: Gateway._on_message NUL/whitespace stripping + Polish JSON error messages (json_error_pl) + regression
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
DEV = f"nul35{uuid.uuid4().hex[:4]}"


def std(tag):
    ch = [{"id": i, "on": True, "heating": False, "mode": "auto", "temp": 20.5 + i, "setpoint": 21.0, "humidity": 65,
           "co2": 1100 + i, "curtain_left": 40, "curtain_right": 40, "chimney": 30, "water_lpm": 1.2, "water_total_l": 100}
          for i in range(3)]
    return json.dumps({"model": f"FBs-{tag}", "chambers": ch, "plant": {"power_kw": 3.2, "power_kwh": 167.2}})


@pytest.fixture(scope="module")
def sa():
    s = requests.Session()
    s.headers.update(H)
    r = s.post(f"{API}/auth/login", json={"email": SA[0], "password": SA[1]})
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def pub(sa):
    r = sa.post(f"{API}/devices", json={"client_id": KOW, "name": "TEST_Nul35", "device_id": DEV, "chambers": 3, "simulated": False})
    assert r.status_code == 200, r.text
    topic = sa.get(f"{API}/devices/{DEV}/mqtt-debug").json()["state_topic"]
    mc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"it35-{uuid.uuid4().hex[:6]}")
    mc.connect("broker.hivemq.com", 1883, 30)
    mc.loop_start()
    time.sleep(1)

    def send(raw: bytes):
        mc.publish(topic, raw, qos=1).wait_for_publish(5)
    yield send
    mc.loop_stop()
    mc.disconnect()
    assert sa.delete(f"{API}/devices/{DEV}").status_code == 200


def dbg(sa):
    return sa.get(f"{API}/devices/{DEV}/mqtt-debug").json()


def wait_tag(sa, tag, timeout=12):
    end = time.time() + timeout
    while time.time() < end:
        m = dbg(sa).get("last_message")
        if m and tag in m["payload"]:
            return m
        time.sleep(0.4)
    pytest.fail(f"message {tag} not received")


def dev_state(sa):
    return {d["device_id"]: d for d in sa.get(f"{API}/devices").json()["devices"]}[DEV]


def tag():
    return uuid.uuid4().hex[:10]


class TestNulStrip:
    def test_01_nul_padding_accepted(self, sa, pub):
        t = tag()
        raw = std(t).encode() + b"\x00" * 50
        pub(raw)
        m = wait_tag(sa, t)
        assert m["ok"] is True, m
        assert m["size"] == len(raw)
        d = dev_state(sa)
        assert d["online"] is True
        assert [c["temp"] for c in d["state"]["chambers"]] == [20.5, 21.5, 22.5]

    def test_02_crlf_spaces_accepted(self, sa, pub):
        t = tag()
        pub(b"  \r\n" + std(t).encode() + b"\r\n   \x00\x00\r\n")
        assert wait_tag(sa, t)["ok"] is True

    def test_03_nul_inside_accepted(self, sa, pub):
        t = tag()
        s = std(t).encode()
        raw = s.replace(b'"chambers"', b'\x00"chambers"\x00').replace(b",", b",\x00")
        pub(raw)
        m = wait_tag(sa, t)
        assert m["ok"] is True, m

    def test_03b_size_about_1058(self, sa, pub):
        # real PLC-sized message (~1KB) with NUL padding to fixed buffer
        t = tag()
        s = std(t).encode()
        raw = s + b"\x00" * max(0, 1058 - len(s))
        pub(raw)
        assert wait_tag(sa, t)["ok"] is True


class TestJsonErrors:
    def test_04_missing_final_brace(self, sa, pub):
        t = tag()
        pub(std(t)[:-1].encode() + b"\x00" * 20)
        m = wait_tag(sa, t)
        assert m["ok"] is False
        e = m["error"]
        print(e)
        assert "wiadomość urwana albo brak zamykającego nawiasu" in e, e
        assert "Koniec wiadomości: …" in e, e
        assert e.endswith('"power_kwh": 167.2}'), e  # last 40 chars of stripped body
        assert "\x00" not in e

    def test_05_concatenated(self, sa, pub):
        t = tag()
        pub((std(t) + std(t)).encode())
        m = wait_tag(sa, t)
        assert m["ok"] is False and "dodatkowe znaki po zamknięciu JSON" in m["error"], m

    def test_06_unquoted_keys(self, sa, pub):
        t = tag()
        pub(("{model: \"%s\", chambers: []}" % t).encode())
        m = wait_tag(sa, t)
        assert m["ok"] is False and "nazwy pól muszą być w cudzysłowach" in m["error"], m

    def test_07_non_utf8(self, sa, pub):
        t = tag()
        pub(b'\xff\xfe{"model":"' + t.encode() + b'"}')
        m = wait_tag(sa, t)
        assert m["ok"] is False and "znaki spoza UTF-8" in m["error"], m

    def test_08_missing_comma(self, sa, pub):
        t = tag()
        pub(('{"model": "%s" "chambers": []}' % t).encode())
        m = wait_tag(sa, t)
        assert m["ok"] is False and "brak przecinka" in m["error"], m

    def test_09_valid_after_errors_restores(self, sa, pub):
        t = tag()
        pub(std(t).encode() + b"\x00" * 10)
        assert wait_tag(sa, t)["ok"] is True
        assert dev_state(sa)["online"] is True


class TestRegression:
    def test_fatek_native_d_format(self, sa, pub):
        t = tag()
        full = {"temp_x10": [194, 214, 229], "setpoint_x10": [200, 220, 240], "humidity": [70, 71, 72], "co2": [1200, 1300, 1400],
                "curtain_left": [40, 40, 40], "curtain_right": [40, 40, 40], "chimney": [30, 30, 30], "mode": [0, 0, 1]}
        pub(json.dumps({"d": full, "error": [], "ts": t}).encode() + b"\x00" * 8)
        m = wait_tag(sa, t)
        assert m["ok"] is True, m
        assert [c["temp"] for c in dev_state(sa)["state"]["chambers"]] == [19.4, 21.4, 22.9]

    def test_kowalski_a_online(self, sa):
        d = sa.get(f"{API}/devices/kowalski-a/mqtt-debug").json()
        assert d["online"] is True and d["last_message"]["ok"] is True

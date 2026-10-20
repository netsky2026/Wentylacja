# Fatek PLC MQTT gateway regression tests (health, config, state, commands round-trip, events, simulator)
import os
import time
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')
API = f"{BASE_URL}/api"
DEV = "plc-01"


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    # wait until device online
    for _ in range(15):
        r = sess.get(f"{API}/health", timeout=10)
        if r.ok and r.json().get("device_online"):
            break
        time.sleep(1)
    return sess


def get_state(s):
    r = s.get(f"{API}/device/{DEV}/state", timeout=10)
    assert r.status_code == 200
    return r.json()["state"]


def cmd(s, body):
    r = s.post(f"{API}/device/{DEV}/command", json=body, timeout=10)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["queued"] is True and isinstance(d["request_id"], str)
    return d


def wait_for(s, pred, timeout=8):
    end = time.time() + timeout
    st = None
    while time.time() < end:
        st = get_state(s)
        if st and pred(st):
            return st
        time.sleep(0.5)
    return st


# Health
def test_health(s):
    d = s.get(f"{API}/health").json()
    assert d["ok"] is True
    assert d["broker_connected"] is True
    assert d["device_online"] is True
    assert "simulator_enabled" in d


# Config
def test_config(s):
    d = s.get(f"{API}/config").json()
    assert d["broker_host"] == "broker.hivemq.com"
    assert d["broker_port"] == 1883
    assert d["prefix"]
    assert d["state_topic"] == f"{d['prefix']}/{DEV}/state"
    assert d["command_topic"] == f"{d['prefix']}/{DEV}/command"
    assert d["layout"] == {"x": 8, "y": 8, "m": 8, "r": 6}


# State
def test_state_shape(s):
    r = s.get(f"{API}/device/{DEV}/state").json()
    assert r["online"] is True
    st = r["state"]
    assert len(st["x"]) == 8 and len(st["y"]) == 8 and len(st["m"]) == 8 and len(st["r"]) == 6
    assert isinstance(st["running"], bool)


# set_output Y round-trip
def test_set_output_y3(s):
    cmd(s, {"type": "set_output", "target": "Y", "index": 3, "value": True})
    st = wait_for(s, lambda st: st["y"][3] is True)
    assert st["y"][3] is True
    cmd(s, {"type": "set_output", "target": "Y", "index": 3, "value": False})
    st = wait_for(s, lambda st: st["y"][3] is False)
    assert st["y"][3] is False


# set_output M round-trip
def test_set_output_m2(s):
    cmd(s, {"type": "set_output", "target": "M", "index": 2, "value": True})
    st = wait_for(s, lambda st: st["m"][2] is True)
    assert st["m"][2] is True
    cmd(s, {"type": "set_output", "target": "M", "index": 2, "value": False})
    assert wait_for(s, lambda st: st["m"][2] is False)["m"][2] is False


# set_register
def test_set_register_r5(s):
    cmd(s, {"type": "set_register", "index": 5, "value": 999})
    st = wait_for(s, lambda st: st["r"][5] == 999)
    assert st["r"][5] == 999


# plc_run stop/start
def test_plc_run(s):
    cmd(s, {"type": "plc_run", "value": False})
    st = wait_for(s, lambda st: st["running"] is False)
    assert st["running"] is False
    time.sleep(1.2)  # allow one in-flight loop tick (known benign race, no lock in simulator)
    r2a = get_state(s)["r"][2]
    time.sleep(2.5)
    assert get_state(s)["r"][2] == r2a, "R2 counter should freeze while stopped"
    cmd(s, {"type": "plc_run", "value": True})
    st = wait_for(s, lambda st: st["running"] is True)
    assert st["running"] is True


# events
def test_events_contain_commands(s):
    time.sleep(1)
    d = s.get(f"{API}/events?limit=50").json()
    msgs = [e["message"] for e in d["events"]]
    assert all("_id" not in e for e in d["events"])
    assert any("R5 = 999" in m for m in msgs)
    assert any("Y3 = ON" in m for m in msgs)
    assert any("PLC STOP" in m for m in msgs)


# validation
def test_invalid_command_type(s):
    r = s.post(f"{API}/device/{DEV}/command", json={"type": "bogus"})
    assert r.status_code == 422


# simulator toggle
def test_simulator_toggle(s):
    r = s.post(f"{API}/simulator/toggle?enable=false")
    assert r.json()["simulator_enabled"] is False
    assert s.get(f"{API}/health").json()["simulator_enabled"] is False
    time.sleep(6)
    assert s.get(f"{API}/health").json()["device_online"] is False
    r = s.post(f"{API}/simulator/toggle?enable=true")
    assert r.json()["simulator_enabled"] is True
    time.sleep(3)
    h = s.get(f"{API}/health").json()
    assert h["simulator_enabled"] is True and h["device_online"] is True

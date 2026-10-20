# Piggery (chlewnia) MQTT gateway regression tests: health/config, state shape, commands round-trip,
# thresholds/alarm, history, events, simulator toggle
import os
import time
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')
API = f"{BASE_URL}/api"
DEV = "chlodnia-01"
DEFAULTS = {0: (26.0, 3000.0), 1: (28.0, 3000.0), 2: (30.0, 3000.0)}


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    for _ in range(15):
        r = sess.get(f"{API}/health", timeout=10)
        if r.ok and r.json().get("device_online"):
            break
        time.sleep(1)
    yield sess
    for k, (t, c) in DEFAULTS.items():
        sess.put(f"{API}/thresholds/{k}", json={"temp_max": t, "co2_max": c}, timeout=10)
    sess.post(f"{API}/simulator/toggle?enable=true", timeout=10)


def state(s):
    r = s.get(f"{API}/device/{DEV}/state", timeout=10)
    assert r.status_code == 200
    return r.json()["state"]


def cmd(s, body):
    r = s.post(f"{API}/device/{DEV}/command", json=body, timeout=10)
    assert r.status_code == 200, r.text
    assert r.json()["queued"] is True
    return r.json()


def wait_for(s, pred, timeout=20):  # public HiveMQ adds 1-4s latency each way
    end = time.time() + timeout
    st = None
    while time.time() < end:
        st = state(s)
        if st and pred(st):
            return st
        time.sleep(0.5)
    return st


# Health / config
def test_health(s):
    d = s.get(f"{API}/health").json()
    assert d["ok"] and d["broker_connected"] and d["device_online"] and d["simulator_enabled"]


def test_config(s):
    d = s.get(f"{API}/config").json()
    assert d["device_id"] == DEV and d["chambers"] == 3
    assert d["state_topic"].endswith(f"/{DEV}/state")
    assert d["command_topic"].endswith(f"/{DEV}/command")


# State shape
def test_state_shape(s):
    st = state(s)
    assert len(st["chambers"]) == 3
    for ch in st["chambers"]:
        for k in ["temp", "setpoint", "humidity", "co2", "on", "heating", "curtain_left",
                  "curtain_right", "chimney", "alarm", "temp_max", "co2_max", "temp_alarm", "co2_alarm"]:
            assert k in ch, k
        assert 0 <= ch["curtain_left"] <= 100 and 0 <= ch["chimney"] <= 100
    for k in ["power_kw", "power_kwh", "water_lpm", "water_total_l"]:
        assert k in st["plant"]


# Setpoint command round trip
def test_setpoint_roundtrip(s):
    orig = state(s)["chambers"][1]["setpoint"]
    cmd(s, {"type": "set_setpoint", "chamber": 1, "value": orig + 0.5})
    st = wait_for(s, lambda x: x["chambers"][1]["setpoint"] == orig + 0.5)
    assert st["chambers"][1]["setpoint"] == orig + 0.5
    cmd(s, {"type": "set_setpoint", "chamber": 1, "value": orig})
    st = wait_for(s, lambda x: x["chambers"][1]["setpoint"] == orig)
    assert st["chambers"][1]["setpoint"] == orig


def test_setpoint_clamped(s):
    orig = state(s)["chambers"][1]["setpoint"]
    cmd(s, {"type": "set_setpoint", "chamber": 1, "value": 99})
    st = wait_for(s, lambda x: x["chambers"][1]["setpoint"] == 35.0)
    assert st["chambers"][1]["setpoint"] == 35.0
    cmd(s, {"type": "set_setpoint", "chamber": 1, "value": orig})
    wait_for(s, lambda x: x["chambers"][1]["setpoint"] == orig)


# Power command round trip
def test_power_roundtrip(s):
    orig = state(s)["chambers"][2]["on"]
    cmd(s, {"type": "chamber_power", "chamber": 2, "value": not orig})
    st = wait_for(s, lambda x: x["chambers"][2]["on"] == (not orig))
    assert st["chambers"][2]["on"] == (not orig)
    cmd(s, {"type": "chamber_power", "chamber": 2, "value": orig})
    st = wait_for(s, lambda x: x["chambers"][2]["on"] == orig)
    assert st["chambers"][2]["on"] == orig


def test_invalid_command_type(s):
    r = s.post(f"{API}/device/{DEV}/command", json={"type": "rm_rf", "chamber": 0})
    assert r.status_code == 422


# Thresholds
def test_thresholds_get(s):
    d = s.get(f"{API}/thresholds").json()["thresholds"]
    assert [x["chamber"] for x in d] == [0, 1, 2]


def test_threshold_put_persist_and_alarm(s):
    cur = state(s)["chambers"][0]
    r = s.put(f"{API}/thresholds/0", json={"temp_max": round(cur["temp"] - 5, 1), "co2_max": 3000})
    assert r.status_code == 200 and r.json()["ok"]
    d = s.get(f"{API}/thresholds").json()["thresholds"][0]
    assert d["temp_max"] == round(cur["temp"] - 5, 1)
    st = wait_for(s, lambda x: x["chambers"][0]["alarm"] is True)
    assert st["chambers"][0]["temp_alarm"] is True and st["chambers"][0]["alarm"] is True
    s.put(f"{API}/thresholds/0", json={"temp_max": 26.0, "co2_max": 3000.0})
    st = wait_for(s, lambda x: x["chambers"][0]["temp_max"] == 26.0)
    assert st["chambers"][0]["temp_max"] == 26.0


def test_threshold_alarm_event_logged(s):
    """Lowering threshold should log an ALARM event (and notify)."""
    cur = state(s)["chambers"][1]
    s.put(f"{API}/thresholds/1", json={"temp_max": round(cur["temp"] - 5, 1), "co2_max": 3000})
    time.sleep(3)
    ev = s.get(f"{API}/events?limit=20").json()["events"]
    s.put(f"{API}/thresholds/1", json={"temp_max": 28.0, "co2_max": 3000.0})
    assert any("ALARM" in e["message"] and "Komora 2" in e["message"] for e in ev[:10]), [e["message"] for e in ev[:10]]


def test_threshold_unknown_chamber(s):
    r = s.put(f"{API}/thresholds/9", json={"temp_max": 20, "co2_max": 1000})
    assert r.status_code == 404


def test_threshold_invalid_body(s):
    r = s.put(f"{API}/thresholds/0", json={"temp_max": "abc"})
    assert r.status_code == 422


# History
def test_history(s):
    d = s.get(f"{API}/history?hours=3").json()
    assert "history" in d and "plant" in d
    assert set(d["history"].keys()) >= {"0", "1", "2"}
    last = d["history"]["0"][-1]
    for k in ["temp", "humidity", "co2", "curtain_left", "curtain_right", "chimney", "ts"]:
        assert k in last
    assert last["curtain_left"] is not None
    assert len(d["plant"]) > 0 and "power_kw" in d["plant"][-1]


# Events
def test_events(s):
    d = s.get(f"{API}/events?limit=50").json()["events"]
    assert any(e["level"] == "command" for e in d)
    assert all("_id" not in e for e in d)


# Simulator toggle
def test_simulator_toggle(s):
    r = s.post(f"{API}/simulator/toggle?enable=false")
    assert r.json()["simulator_enabled"] is False
    off = False
    for _ in range(20):
        time.sleep(1)
        if s.get(f"{API}/health").json()["device_online"] is False:
            off = True
            break
    s.post(f"{API}/simulator/toggle?enable=true")
    assert off
    on = False
    for _ in range(20):
        time.sleep(1)
        if s.get(f"{API}/health").json()["device_online"] is True:
            on = True
            break
    assert on


# Command validation (iteration 3)
@pytest.mark.parametrize("body", [
    {"type": "set_setpoint", "chamber": 9, "value": 20},
    {"type": "chamber_power", "chamber": -1, "value": True},
    {"type": "set_setpoint", "chamber": 0, "value": "abc"},
    {"type": "set_setpoint", "chamber": 0, "value": None},
])
def test_command_validation_422(s, body):
    r = s.post(f"{API}/device/{DEV}/command", json=body, timeout=10)
    assert r.status_code == 422, r.text


# ---------------- iteration 4: manual ventilation, daily usage, CSV export, broker settings ----------------
# Manual ventilation mode (set_mode / set_vent)
@pytest.mark.parametrize("body", [
    {"type": "set_mode", "chamber": 1, "value": "turbo"},
    {"type": "set_mode", "chamber": 1, "value": None},
    {"type": "set_vent", "chamber": 1, "value": {"curtain_left": 101}},
    {"type": "set_vent", "chamber": 1, "value": {"curtain_left": -1}},
    {"type": "set_vent", "chamber": 1, "value": {"curtain_left": True}},
    {"type": "set_vent", "chamber": 1, "value": {"curtain_left": "50"}},
    {"type": "set_vent", "chamber": 1, "value": {"door": 50}},
    {"type": "set_vent", "chamber": 1, "value": {}},
    {"type": "set_vent", "chamber": 1, "value": 50},
    {"type": "set_vent", "chamber": 1, "value": [50]},
])
def test_vent_validation_422(s, body):
    r = s.post(f"{API}/device/{DEV}/command", json=body, timeout=10)
    assert r.status_code == 422, r.text


def test_manual_mode_and_vent_gradual(s):
    cmd(s, {"type": "set_mode", "chamber": 1, "value": "manual"})
    st = wait_for(s, lambda x: x["chambers"][1]["mode"] == "manual")
    assert st["chambers"][1]["mode"] == "manual"
    cur = st["chambers"][1]
    tgt_l = 90 if cur["curtain_left"] < 50 else 10
    cmd(s, {"type": "set_vent", "chamber": 1, "value": {"curtain_left": tgt_l, "curtain_right": tgt_l, "chimney": 100 - tgt_l}})
    st = wait_for(s, lambda x: x["chambers"][1]["manual"]["curtain_left"] == tgt_l)
    m = st["chambers"][1]["manual"]
    assert m == {"curtain_left": tgt_l, "curtain_right": tgt_l, "chimney": 100 - tgt_l}
    from datetime import datetime
    a, ta = st["chambers"][1]["curtain_left"], datetime.fromisoformat(st["ts"])
    time.sleep(3)
    st2 = state(s)
    b, tb = st2["chambers"][1]["curtain_left"], datetime.fromisoformat(st2["ts"])
    dt = (tb - ta).total_seconds()
    step = abs(b - a)
    assert 0 < step <= 3 * (dt + 1) + 0.5, (a, b, dt)   # gradual, ~3%/s
    assert (b - a) * (tgt_l - a) > 0       # moving toward target
    st = wait_for(s, lambda x: abs(x["chambers"][1]["curtain_left"] - tgt_l) < 0.5, timeout=40)
    assert abs(st["chambers"][1]["curtain_left"] - tgt_l) < 0.5
    assert abs(st["chambers"][1]["chimney"] - (100 - tgt_l)) < 0.5
    # back to auto -> PLC overrides (moves away from manual target toward computed demand)
    cmd(s, {"type": "set_mode", "chamber": 1, "value": "auto"})
    st = wait_for(s, lambda x: x["chambers"][1]["mode"] == "auto", timeout=20)
    assert st["chambers"][1]["mode"] == "auto"


def test_vent_in_auto_ignored_by_plc(s):
    st = state(s)
    assert st["chambers"][1]["mode"] == "auto"
    before = st["chambers"][1]["curtain_left"]
    tgt = 100 if before < 50 else 0
    cmd(s, {"type": "set_vent", "chamber": 1, "value": {"curtain_left": tgt}})
    time.sleep(3)
    after = state(s)["chambers"][1]["curtain_left"]
    # In auto mode the PLC should not track the manual target to the extreme
    assert abs(after - tgt) > 5, (before, after)


# Daily usage
def test_usage_daily(s):
    d = s.get(f"{API}/usage/daily?days=7", timeout=10).json()["days"]
    assert len(d) == 7
    for e in d:
        assert set(e) >= {"date", "kwh", "water_m3"}
    assert d[-1]["kwh"] > 0 and d[-1]["water_m3"] > 0
    assert d == sorted(d, key=lambda e: e["date"])


# CSV export
def test_history_csv(s):
    r = s.get(f"{API}/history/csv?chamber=0&hours=24", timeout=20)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers.get("content-disposition", "")
    txt = r.content.decode("utf-8")
    assert txt.startswith("\ufeff")
    lines = txt.lstrip("\ufeff").strip().split("\n")
    hdr = lines[0].split(";")
    assert hdr[0] == "czas" and len(hdr) == 7 and "kurtyna_L_zamkn_%" in hdr
    assert len(lines) > 1
    row = lines[-1].split(";")
    assert len(row) == 7
    assert "." not in ";".join(row[1:])  # comma decimals


def test_history_csv_closed_pct(s):
    h = s.get(f"{API}/history?hours=1", timeout=10).json()["history"]["0"][-1]
    txt = s.get(f"{API}/history/csv?chamber=0&hours=1", timeout=20).content.decode("utf-8")
    row = txt.strip().split("\n")[-1].split(";")
    assert float(row[4].replace(",", ".")) == round(100 - h["curtain_left"], 1)


def test_history_csv_404(s):
    assert s.get(f"{API}/history/csv?chamber=9&hours=24", timeout=10).status_code == 404


# Broker settings
ORIG_BROKER = {"host": "broker.hivemq.com", "port": 1883, "username": "", "tls": False,
               "prefix": "emgt-fatek-7f3a9c", "device_id": "chlodnia-01"}


@pytest.mark.parametrize("patch", [{"host": "bad host"}, {"port": 0}, {"port": 70000},
                                   {"prefix": "a/#"}, {"prefix": ""}, {"device_id": "a/b"}])
def test_broker_validation_422(s, patch):
    r = s.put(f"{API}/broker", json={**ORIG_BROKER, **patch}, timeout=10)
    assert r.status_code == 422, r.text


def test_broker_reconnect_same(s):
    try:
        r = s.put(f"{API}/broker", json=ORIG_BROKER, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["broker_host"] == "broker.hivemq.com" and d["broker_port"] == 1883
        assert d["username"] == "" and d["has_password"] is False and d["tls"] is False
        ok = False
        for _ in range(40):
            time.sleep(1)
            if s.get(f"{API}/health", timeout=10).json().get("device_online"):
                ok = True
                break
        assert ok, "device did not come back online within 40s"
        c = s.get(f"{API}/config", timeout=10).json()
        assert c["prefix"] == "emgt-fatek-7f3a9c" and c["device_id"] == DEV
        assert {"username", "has_password", "tls"} <= set(c)
    finally:
        if s.get(f"{API}/config", timeout=10).json().get("prefix") != ORIG_BROKER["prefix"]:
            s.put(f"{API}/broker", json=ORIG_BROKER, timeout=20)

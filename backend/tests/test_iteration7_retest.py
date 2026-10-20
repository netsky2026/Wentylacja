# Iteration 7 retest: per-account lockout, strict MQTT chamber validation, token-version revocation,
# events/history clamping, quick role regression
import os
import json
import time
import uuid
import pytest
import requests
import paho.mqtt.client as mqtt
from pymongo import MongoClient

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')
API = f"{BASE_URL}/api"
DEV = "chlodnia-01"
ADMIN = {"email": "admin@chlewnia.pl", "password": "Wentylacja!2026"}
TOPIC = "emgt-fatek-7f3a9c/chlodnia-01/state"


def _mongo():
    env = dict(l.strip().split("=", 1) for l in open("/app/backend/.env") if "=" in l)
    return MongoClient(env["MONGO_URL"].strip('"'))[env["DB_NAME"].strip('"')]


def login(email, password, headers=None):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, headers=headers or {}, timeout=15)
    return s, r


@pytest.fixture()  # function scope: admin password test revokes earlier sessions by design
def admin():
    s, r = login(**ADMIN)
    assert r.status_code == 200, r.text
    return s


def mk_user(admin, role="viewer", prefix="test_it7"):
    email = f"{prefix}_{uuid.uuid4().hex[:6]}@example.com"
    r = admin.post(f"{API}/users", json={"email": email, "name": "TEST", "password": "TestPass123!", "role": role})
    assert r.status_code == 200, r.text
    return r.json()["id"], email


# ---- per-account lockout ----
def test_lockout_per_account_xff_and_correct_pw(admin):
    uid, email = mk_user(admin)
    try:
        codes = [login(email, "bad", {"X-Forwarded-For": f"9.9.9.{i}"})[1].status_code for i in range(5)]
        assert codes == [401] * 5, codes
        r = login(email, "bad", {"X-Forwarded-For": "1.2.3.4"})[1]
        assert r.status_code == 429, r.status_code
        r = login(email, "bad", {"X-Forwarded-For": "5.6.7.8, 10.0.0.1", "X-Real-IP": "8.8.8.8"})[1]
        assert r.status_code == 429
        r = login(email, "TestPass123!")[1]
        assert r.status_code == 429, "correct password must still be locked"
        r = login(email.upper(), "TestPass123!")[1]
        assert r.status_code == 429, "uppercase email variant must also be locked"
        # another account unaffected
        assert login(**ADMIN)[1].status_code == 200
    finally:
        admin.delete(f"{API}/users/{uid}")
        _mongo().login_attempts.delete_many({"identifier": email})


# ---- strict MQTT sanitize ----
@pytest.mark.parametrize("payload", [
    {"chambers": [{"id": 0, "temp": 99.0, "setpoint": 20, "humidity": 50, "co2": 900, "on": True,
                   "curtain_left": 1, "curtain_right": 1, "chimney": 1}]},
    {"chambers": []},
    {"chambers": [{"id": 0, "temp": 99.0, "setpoint": 20, "humidity": 50, "co2": 900, "on": True,
                   "curtain_left": 1, "curtain_right": 1, "chimney": 1}] * 3},
])
def test_mqtt_invalid_chamber_sets_rejected(admin, payload):
    seen, temps = set(), set()
    c = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id=f"test-{uuid.uuid4().hex[:6]}")
    c.connect("broker.hivemq.com", 1883)
    c.loop_start()
    for _ in range(12):
        c.publish(TOPIC, json.dumps(payload), qos=1)
        time.sleep(0.25)
        st = admin.get(f"{API}/device/{DEV}/state").json()["state"]
        seen.add(len(st["chambers"]))
        ids = tuple(ch["id"] for ch in st["chambers"])
        assert ids == (0, 1, 2), ids
        temps.add(st["chambers"][0]["temp"])
    c.loop_stop()
    c.disconnect()
    assert seen == {3}, seen
    assert 99.0 not in temps, "fake temp leaked"


# ---- token version revocation ----
def test_password_change_revokes_old_tokens(admin):
    uid, email = mk_user(admin)
    try:
        s, r = login(email, "TestPass123!")
        assert r.status_code == 200
        old_access = s.cookies.get("access_token")
        old_refresh = s.cookies.get("refresh_token")
        other, _ = login(email, "TestPass123!")  # second session
        assert other.get(f"{API}/auth/me").status_code == 200
        r = s.put(f"{API}/auth/password", json={"current_password": "TestPass123!", "new_password": "NewPass123!"})
        assert r.status_code == 200
        sc = r.headers.get("set-cookie", "")
        assert "access_token=" in sc and "refresh_token=" in sc
        assert s.cookies.get("access_token") != old_access
        # current session works
        assert s.get(f"{API}/auth/me").status_code == 200
        assert s.post(f"{API}/auth/refresh").status_code == 200
        # old tokens dead
        assert requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {old_access}"}).status_code == 401
        assert requests.post(f"{API}/auth/refresh", cookies={"refresh_token": old_refresh}).status_code == 401
        assert requests.get(f"{API}/auth/me", cookies={"access_token": old_access}).status_code == 401
        assert other.get(f"{API}/auth/me").status_code == 401
        assert other.post(f"{API}/auth/refresh").status_code == 401
    finally:
        admin.delete(f"{API}/users/{uid}")


def test_admin_password_change_and_restore():
    s, r = login(**ADMIN)
    old_access = s.cookies.get("access_token")
    try:
        r = s.put(f"{API}/auth/password", json={"current_password": ADMIN["password"], "new_password": "TmpAdmin!2026x"})
        assert r.status_code == 200
        assert requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {old_access}"}).status_code == 401
        assert s.get(f"{API}/auth/me").status_code == 200
    finally:
        r = s.put(f"{API}/auth/password", json={"current_password": "TmpAdmin!2026x", "new_password": ADMIN["password"]})
        assert r.status_code == 200
    assert login(**ADMIN)[1].status_code == 200


# ---- clamping ----
def test_events_limit_clamped(admin):
    r = admin.get(f"{API}/events", params={"limit": 10000000})
    assert r.status_code == 200
    d = r.json()
    items = d if isinstance(d, list) else d.get("events", d.get("items", []))
    assert len(items) <= 500
    assert admin.get(f"{API}/events", params={"limit": -5}).status_code == 200


def test_history_hours_clamped(admin):
    t = time.time()
    r = admin.get(f"{API}/history", params={"hours": 99999})
    assert r.status_code == 200
    assert time.time() - t < 15
    d = r.json()
    r24 = admin.get(f"{API}/history", params={"hours": 24}).json()
    n = lambda x: len(json.dumps(x))
    # same data size as 24h (allow small drift from new points)
    assert abs(n(d) - n(r24)) < max(5000, n(r24) * 0.05), (n(d), n(r24))


# ---- role regression ----
def test_roles_403(admin):
    vid, vemail = mk_user(admin, "viewer")
    oid, oemail = mk_user(admin, "operator")
    try:
        v, _ = login(vemail, "TestPass123!")
        o, _ = login(oemail, "TestPass123!")
        assert v.get(f"{API}/device/{DEV}/state").status_code == 200
        assert v.post(f"{API}/device/{DEV}/command", json={"chamber": 0, "action": "set_on", "value": True}).status_code == 403
        assert v.put(f"{API}/thresholds/0", json={}).status_code == 403
        assert o.get(f"{API}/users").status_code == 403
        assert o.post(f"{API}/users", json={"email": "x@y.zz", "password": "12345678", "role": "admin"}).status_code == 403
        assert v.get(f"{API}/users").status_code == 403
        assert o.post(f"{API}/auth/logout").status_code == 200
    finally:
        admin.delete(f"{API}/users/{vid}")
        admin.delete(f"{API}/users/{oid}")

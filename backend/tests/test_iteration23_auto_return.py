# Iteration 23: per-farm auto-return time (GET/PUT /api/auto-return), scheduler real run, RBAC
import os
import time
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
H = {"Origin": BASE_URL}
KOW = "kowalski-a"
MP = "chlodnia-01"
TAG = uuid.uuid4().hex[:6]
PW = "Haslo1234!x"


def login(email, pw):
    ss = requests.Session()
    ss.headers.update(H)
    r = ss.post(f"{API}/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return ss


def devs(s):
    return {d["device_id"]: d for d in s.get(f"{API}/devices").json()["devices"]}


def mode(s, dev, ch):
    return devs(s)[dev]["state"]["chambers"][ch].get("mode")


def wait_mode(s, dev, ch, m, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        if mode(s, dev, ch) == m:
            return True
        time.sleep(1)
    return False


@pytest.fixture(scope="module")
def sa():
    s = login("admin@chlewnia.pl", "Wentylacja!2026")
    cl = s.get(f"{API}/clients").json()["clients"]
    s.kow = next(c["id"] for c in cl if c["name"] == "Ferma Kowalski")
    s.mp = next(c["id"] for c in cl if c["name"] == "Marco Polo")
    s.users = {}
    for role in ("admin", "operator", "viewer"):
        email = f"test_{TAG}_{role}@kowalski.pl"
        r = s.post(f"{API}/users", json={"email": email, "password": PW, "role": role, "client_id": s.kow})
        assert r.status_code in (200, 201), r.text
        s.users[role] = (email, r.json().get("id") or r.json().get("user", {}).get("id"))
    yield s
    for cid in (s.kow, s.mp):
        s.put(f"{API}/auto-return?client_id={cid}", json={"time": "00:00"})
    for i in range(6):
        s.post(f"{API}/devices/{KOW}/command", json={"type": "set_mode", "chamber": i, "value": "auto"})
    for i in range(3):
        s.post(f"{API}/devices/{MP}/command", json={"type": "set_mode", "chamber": i, "value": "auto"})
    for email, uid in s.users.values():
        if uid:
            s.delete(f"{API}/users/{uid}")


def test_default_and_superadmin_requires_client(sa):
    assert sa.get(f"{API}/auto-return?client_id={sa.kow}").json()["time"] == "00:00"
    assert sa.get(f"{API}/auto-return?client_id={sa.mp}").json()["time"] == "00:00"
    assert sa.get(f"{API}/auto-return").status_code == 422


def test_put_and_devices_view(sa):
    r = sa.put(f"{API}/auto-return?client_id={sa.kow}", json={"time": "06:30"})
    assert r.status_code == 200 and r.json()["time"] == "06:30"
    assert sa.get(f"{API}/auto-return?client_id={sa.kow}").json()["time"] == "06:30"
    d = devs(sa)
    assert d[KOW]["auto_return"] == "06:30"
    assert d[MP]["auto_return"] == "00:00"


def test_disable(sa):
    r = sa.put(f"{API}/auto-return?client_id={sa.kow}", json={"time": ""})
    assert r.status_code == 200
    assert sa.get(f"{API}/auto-return?client_id={sa.kow}").json()["time"] == ""
    assert devs(sa)[KOW]["auto_return"] == ""


@pytest.mark.parametrize("bad", ["25:00", "6:30", "12:60", "abc", "06:30:00", " 06:30"])
def test_invalid(sa, bad):
    assert sa.put(f"{API}/auto-return?client_id={sa.kow}", json={"time": bad}).status_code == 422


def test_client_admin_scoped(sa):
    a = login(sa.users["admin"][0], PW)
    assert a.put(f"{API}/auto-return", json={"time": "07:15"}).status_code == 200
    assert sa.get(f"{API}/auto-return?client_id={sa.kow}").json()["time"] == "07:15"
    # other farm's client_id is ignored -> own client
    r = a.put(f"{API}/auto-return?client_id={sa.mp}", json={"time": "08:45"})
    assert r.status_code == 200
    assert sa.get(f"{API}/auto-return?client_id={sa.mp}").json()["time"] == "00:00"
    assert sa.get(f"{API}/auto-return?client_id={sa.kow}").json()["time"] == "08:45"
    assert a.get(f"{API}/auto-return?client_id={sa.mp}").json()["time"] == "08:45"


@pytest.mark.parametrize("role", ["operator", "viewer"])
def test_lower_roles_forbidden(sa, role):
    u = login(sa.users[role][0], PW)
    assert u.get(f"{API}/auto-return").status_code == 403
    assert u.put(f"{API}/auto-return", json={"time": "05:00"}).status_code == 403


def test_unauthenticated():
    assert requests.get(f"{API}/auto-return").status_code == 401


def test_scheduler_real_run(sa):
    now = datetime.now(ZoneInfo("Europe/Warsaw"))
    target = (now + timedelta(minutes=2 if now.second > 45 else 1)).strftime("%H:%M")
    assert sa.put(f"{API}/auto-return?client_id={sa.kow}", json={"time": target}).status_code == 200
    for dev in (KOW, MP):
        r = sa.post(f"{API}/devices/{dev}/command", json={"type": "set_mode", "chamber": 1, "value": "manual"})
        assert r.status_code == 200
        assert wait_mode(sa, dev, 1, "manual")
    assert wait_mode(sa, KOW, 1, "auto", timeout=150), "kowalski-a ch1 did not return to auto"
    time.sleep(3)
    assert mode(sa, MP, 1) == "manual", "Marco Polo chamber must stay manual"
    ev = sa.get(f"{API}/events?device_id={KOW}&limit=50").json()["events"]
    assert any(f"automatyczny powrót do AUTO ({target})" in e.get("message", e.get("msg", str(e))) for e in ev), ev[:5]
    sa.post(f"{API}/devices/{MP}/command", json={"type": "set_mode", "chamber": 1, "value": "auto"})
    assert wait_mode(sa, MP, 1, "auto")

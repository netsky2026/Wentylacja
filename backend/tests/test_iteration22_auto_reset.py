# Iteration 22: chamber_power removed, set_mode/set_setpoint/set_vent work, /api/admin/auto-reset (midnight AUTO return)
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
H = {"Origin": BASE_URL}
DEV = "kowalski-a"
TAG = uuid.uuid4().hex[:6]
PW = "Haslo1234!x"


def login(email, pw):
    ss = requests.Session()
    ss.headers.update(H)
    r = ss.post(f"{API}/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return ss


def chamber(s, cid=0):
    devs = {d["device_id"]: d for d in s.get(f"{API}/devices").json()["devices"]}
    return devs[DEV]["state"]["chambers"][cid]


def wait_mode(s, mode, cid=0, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        if chamber(s, cid).get("mode") == mode:
            return True
        time.sleep(1)
    return False


@pytest.fixture(scope="module")
def sa():
    s = login("admin@chlewnia.pl", "Wentylacja!2026")
    s.orig_sp = chamber(s, 0).get("setpoint")
    clients = s.get(f"{API}/clients").json()["clients"]
    kow = next(c for c in clients if c.get("slug") == "kowalski")
    s.users = {}
    for role in ("admin", "operator", "viewer"):
        email = f"test_{TAG}_{role}@kowalski.pl"
        r = s.post(f"{API}/users", json={"email": email, "password": PW, "role": role, "client_id": kow["id"]})
        assert r.status_code in (200, 201), r.text
        s.users[role] = (email, r.json().get("id") or r.json().get("user", {}).get("id"))
    yield s
    for i in range(6):
        s.post(f"{API}/devices/{DEV}/command", json={"type": "set_mode", "chamber": i, "value": "auto"})
    if s.orig_sp is not None:
        s.post(f"{API}/devices/{DEV}/command", json={"type": "set_setpoint", "chamber": 0, "value": s.orig_sp})
    for email, uid in s.users.values():
        if uid:
            s.delete(f"{API}/users/{uid}")


# chamber_power removed
def test_chamber_power_rejected(sa):
    for v in (True, False):
        r = sa.post(f"{API}/devices/{DEV}/command", json={"type": "chamber_power", "chamber": 0, "value": v})
        assert r.status_code == 422, r.text


def test_operator_chamber_power_rejected(sa):
    op = login(sa.users["operator"][0], PW)
    r = op.post(f"{API}/devices/{DEV}/command", json={"type": "chamber_power", "chamber": 0, "value": False})
    assert r.status_code == 422


# other commands still work for operator+
def test_operator_set_setpoint(sa):
    op = login(sa.users["operator"][0], PW)
    r = op.post(f"{API}/devices/{DEV}/command", json={"type": "set_setpoint", "chamber": 0, "value": 21.5})
    assert r.status_code == 200 and r.json()["queued"] is True


def test_operator_set_mode_and_vent(sa):
    op = login(sa.users["operator"][0], PW)
    r = op.post(f"{API}/devices/{DEV}/command", json={"type": "set_mode", "chamber": 1, "value": "manual"})
    assert r.status_code == 200
    assert wait_mode(sa, "manual", 1)
    r = op.post(f"{API}/devices/{DEV}/command", json={"type": "set_vent", "chamber": 1, "value": {"chimney": 40}})
    assert r.status_code == 200
    r = op.post(f"{API}/devices/{DEV}/command", json={"type": "set_mode", "chamber": 1, "value": "auto"})
    assert r.status_code == 200
    assert wait_mode(sa, "auto", 1)


def test_viewer_cannot_command(sa):
    v = login(sa.users["viewer"][0], PW)
    r = v.post(f"{API}/devices/{DEV}/command", json={"type": "set_mode", "chamber": 0, "value": "manual"})
    assert r.status_code == 403


# auto-reset endpoint RBAC
@pytest.mark.parametrize("role", ["admin", "operator", "viewer"])
def test_auto_reset_forbidden(sa, role):
    s = login(sa.users[role][0], PW)
    assert s.post(f"{API}/admin/auto-reset").status_code == 403


def test_auto_reset_unauth():
    assert requests.post(f"{API}/admin/auto-reset", headers=H).status_code == 401


# full flow: manual -> auto-reset -> auto + event log
def test_auto_reset_flow(sa):
    r = sa.post(f"{API}/devices/{DEV}/command", json={"type": "set_mode", "chamber": 0, "value": "manual"})
    assert r.status_code == 200
    assert wait_mode(sa, "manual", 0), "chamber 0 never switched to manual"
    r = sa.post(f"{API}/admin/auto-reset")
    assert r.status_code == 200 and r.json()["ok"] is True
    assert wait_mode(sa, "auto", 0, timeout=10), "chamber 0 did not return to auto"
    ev = sa.get(f"{API}/events?device_id={DEV}&limit=50").json()["events"]
    msgs = [e.get("message") or e.get("msg") or str(e) for e in ev]
    assert any("automatyczny powrót do AUTO (00:00)" in m for m in msgs), msgs[:5]


def test_auto_reset_noop_when_all_auto(sa):
    before = len([e for e in sa.get(f"{API}/events?device_id={DEV}&limit=200").json()["events"]
                  if "automatyczny powrót" in str(e)])
    assert sa.post(f"{API}/admin/auto-reset").status_code == 200
    time.sleep(1)
    after = len([e for e in sa.get(f"{API}/events?device_id={DEV}&limit=200").json()["events"]
                 if "automatyczny powrót" in str(e)])
    assert after == before

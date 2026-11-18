# Iteration 37: multi-farm user access (client_ids), PUT /users/{id}/access, client delete cascade, plc-scale, mqtt-send, device move
import os
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
SA = ("admin@chlewnia.pl", "Wentylacja!2026")
KOW = "6ad7dcc3261e5ba3c23315b7"
MP = "6ad7dcb08b38a7c48f3db7d2"
H = {"Origin": BASE_URL}
PW = "TestPass!2026"
TAG = uuid.uuid4().hex[:6]


def login(email, pw=PW):
    s = requests.Session()
    s.headers.update(H)
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def sa():
    return login(*SA)


@pytest.fixture(scope="module")
def created(sa):
    ids = []
    yield ids
    for uid in ids:
        sa.delete(f"{API}/users/{uid}")


def mk(sa, created, name, role, client_ids):
    r = sa.post(f"{API}/users", json={"email": f"test_{name}_{TAG}@example.com", "password": PW, "role": role, "client_ids": client_ids})
    assert r.status_code == 200, r.text
    u = r.json()
    created.append(u["id"])
    return u


# --- user creation / no farm ---
def test_create_no_farm_sees_nothing(sa, created):
    u = mk(sa, created, "nofarm", "operator", [])
    assert u["client_ids"] == [] and u["client_id"] is None
    s = login(u["email"])
    assert s.get(f"{API}/devices").json()["devices"] == []
    assert s.get(f"{API}/auth/me").json()["client_ids"] == []
    ev = s.get(f"{API}/events")
    assert ev.status_code == 200, ev.text
    assert s.post(f"{API}/devices/kowalski-a/command", json={"type": "set_mode", "chamber": 0, "value": "auto"}).status_code == 404
    b = s.get(f"{API}/branding")
    assert b.status_code == 200


def test_create_invalid_farm_422(sa):
    r = sa.post(f"{API}/users", json={"email": f"test_bad_{TAG}@example.com", "password": PW, "role": "viewer", "client_ids": ["000000000000000000000000"]})
    assert r.status_code == 422


# --- two farms operator ---
def test_two_farms_operator(sa, created):
    u = mk(sa, created, "op2", "operator", [KOW, MP])
    assert u["client_ids"] == [KOW, MP] and u["client_id"] == KOW
    s = login(u["email"])
    devs = {d["device_id"] for d in s.get(f"{API}/devices").json()["devices"]}
    assert {"kowalski-a", "chlodnia-01"} <= devs
    for dev in ("kowalski-a", "chlodnia-01"):
        r = s.post(f"{API}/devices/{dev}/command", json={"type": "set_mode", "chamber": 0, "value": "auto"})
        assert r.status_code == 200, r.text


def test_viewer_403(sa, created):
    u = mk(sa, created, "view", "viewer", [KOW, MP])
    s = login(u["email"])
    assert len(s.get(f"{API}/devices").json()["devices"]) >= 2
    r = s.post(f"{API}/devices/chlodnia-01/command", json={"type": "set_mode", "chamber": 0, "value": "auto"})
    assert r.status_code == 403


# --- PUT access ---
def test_set_access_flow(sa, created):
    u = mk(sa, created, "acc", "viewer", [KOW])
    r = sa.put(f"{API}/users/{u['id']}/access", json={"role": "operator", "client_ids": [MP, KOW]})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["role"] == "operator" and d["client_ids"] == [MP, KOW] and d["client_id"] == MP
    lst = sa.get(f"{API}/users", params={"client_id": MP}).json()["users"]
    assert any(x["id"] == u["id"] for x in lst)
    assert all(MP in x["client_ids"] for x in lst)
    # remove all farms
    r = sa.put(f"{API}/users/{u['id']}/access", json={"role": "operator", "client_ids": []})
    assert r.status_code == 200 and r.json()["client_ids"] == [] and r.json()["client_id"] is None
    s = login(u["email"])
    assert s.get(f"{API}/devices").json()["devices"] == []
    lst = sa.get(f"{API}/users", params={"client_id": MP}).json()["users"]
    assert not any(x["id"] == u["id"] for x in lst)


def test_set_access_validation(sa, created):
    u = mk(sa, created, "val", "viewer", [KOW])
    assert sa.put(f"{API}/users/{u['id']}/access", json={"role": "viewer", "client_ids": ["000000000000000000000000"]}).status_code == 422
    assert sa.put(f"{API}/users/{u['id']}/access", json={"role": "viewer", "client_ids": ["nope"]}).status_code == 422
    assert sa.put(f"{API}/users/{u['id']}/access", json={"role": "viewer", "client_ids": [KOW, KOW]}).status_code == 422
    assert sa.put(f"{API}/users/{u['id']}/access", json={"role": "superadmin", "client_ids": [KOW]}).status_code == 422
    me = sa.get(f"{API}/auth/me").json()
    assert sa.put(f"{API}/users/{me['id']}/access", json={"role": "admin", "client_ids": [KOW]}).status_code == 404
    assert sa.put(f"{API}/users/000000000000000000000000/access", json={"role": "admin", "client_ids": []}).status_code == 404


def test_set_access_non_superadmin_403(sa, created):
    adm = mk(sa, created, "adm", "admin", [KOW, MP])
    tgt = mk(sa, created, "tgt", "viewer", [KOW])
    s = login(adm["email"])
    assert s.put(f"{API}/users/{tgt['id']}/access", json={"role": "admin", "client_ids": [KOW]}).status_code == 403


# --- farm admin with 2 farms: farm-level settings use client_id ---
def test_farm_admin_two_farms_scope(sa, created):
    adm = mk(sa, created, "fadm", "admin", [KOW, MP])
    s = login(adm["email"])
    for cid in (KOW, MP):
        for ep in ("auto-return", "rates", "client-contact", "alarm-settings"):
            r = s.get(f"{API}/{ep}", params={"client_id": cid})
            assert r.status_code == 200, f"{ep} {cid}: {r.status_code} {r.text}"
        us = s.get(f"{API}/users", params={"client_id": cid}).json()["users"]
        assert all(cid in x["client_ids"] for x in us)
    ar = s.get(f"{API}/auto-return", params={"client_id": MP}).json()
    r = s.put(f"{API}/auto-return", params={"client_id": MP}, json={"time": ar["time"]})
    assert r.status_code == 200
    # user created by farm admin goes to selected farm
    r = s.post(f"{API}/users", json={"email": f"test_byadm_{TAG}@example.com", "password": PW, "role": "viewer", "client_id": MP})
    assert r.status_code == 200, r.text
    created.append(r.json()["id"])
    assert r.json()["client_ids"] == [MP]
    # farm admin cannot delete multi-farm user? (only within own farms) -> allowed since subset
    other = mk(sa, created, "onlykow", "viewer", [KOW])
    s1 = login(mk(sa, created, "kowadm", "admin", [KOW])["email"])
    multi = mk(sa, created, "multi", "viewer", [KOW, MP])
    assert s1.delete(f"{API}/users/{multi['id']}").status_code == 403
    assert s1.delete(f"{API}/users/{other['id']}").status_code == 200
    created.remove(other["id"])


# --- client delete cascade ---
def test_delete_client_cascade(sa, created):
    r = sa.post(f"{API}/clients", json={"name": f"TEST_Farm_{TAG}"})
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    only = mk(sa, created, "only", "viewer", [cid])
    both = mk(sa, created, "both", "viewer", [cid, KOW])
    assert sa.delete(f"{API}/clients/{cid}").status_code == 200
    users = {x["id"]: x for x in sa.get(f"{API}/users").json()["users"]}
    assert only["id"] not in users
    created.remove(only["id"])
    assert users[both["id"]]["client_ids"] == [KOW] and users[both["id"]]["client_id"] == KOW


# --- regression: plc-scale ---
def test_plc_scale(sa):
    cur = sa.get(f"{API}/plc-scale").json()
    assert cur["temp"] == 10 and cur["setpoint"] == 10
    assert sa.put(f"{API}/plc-scale", json={"co2": 7}).status_code == 422
    assert sa.put(f"{API}/plc-scale", json={"bogus": 10}).status_code == 422
    r = sa.put(f"{API}/plc-scale", json={"humidity": 10})
    assert r.status_code == 200 and r.json()["humidity"] == 10
    assert sa.get(f"{API}/plc-scale").json()["humidity"] == 10
    r = sa.put(f"{API}/plc-scale", json={"humidity": 1})
    assert r.json()["humidity"] == 1


# --- regression: mqtt-send ---
def test_mqtt_send(sa):
    topic = sa.get(f"{API}/devices/kowalski-a/mqtt-debug").json()["command_topic"]
    assert sa.post(f"{API}/devices/kowalski-a/mqtt-send", json={"topic": topic, "payload": "{bad"}).status_code in (400, 422)
    r = sa.post(f"{API}/devices/kowalski-a/mqtt-send", json={"topic": topic, "payload": f'{{"test":"{TAG}"}}'})
    assert r.status_code == 200, r.text
    h = sa.get(f"{API}/devices/kowalski-a/mqtt-sent").json()
    assert TAG in h[0]["payload"]


# --- regression: device move ---
def test_device_move_roundtrip(sa):
    r = sa.patch(f"{API}/devices/chlodnia-01", json={"client_id": KOW})
    try:
        assert r.status_code == 200 and r.json()["client_id"] == KOW
        assert sa.patch(f"{API}/devices/chlodnia-01", json={"client_id": "000000000000000000000000"}).status_code == 422
    finally:
        r2 = sa.patch(f"{API}/devices/chlodnia-01", json={"client_id": MP})
    assert r2.status_code == 200 and r2.json()["client_id"] == MP

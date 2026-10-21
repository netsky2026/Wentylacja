# Iteration 18: chamber rename PUT /api/devices/{id}/chambers/{n}/name + RBAC
import os
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
ADMIN = {"email": "admin@chlewnia.pl", "password": "Wentylacja!2026"}
PW = "TestPass!2026x"
CREATED_USERS = []


def sess():
    s = requests.Session()
    s.headers.update({"Origin": BASE_URL})
    return s


def url(dev, ch):
    return f"{BASE_URL}/api/devices/{dev}/chambers/{ch}/name"


def names(s, dev):
    r = s.get(f"{BASE_URL}/api/devices")
    assert r.status_code == 200
    d = [x for x in r.json()["devices"] if x["device_id"] == dev]
    return d[0]["chamber_names"] if d else None


@pytest.fixture(scope="module")
def sa():
    s = sess()
    r = s.post(f"{BASE_URL}/api/auth/login", json=ADMIN)
    if r.status_code != 200:
        pytest.skip("login failed")
    yield s
    for dev, n in (("kowalski-a", 6), ("chlodnia-01", 3)):
        for i in range(n):
            s.put(url(dev, i), json={"name": ""})
    for uid in CREATED_USERS:
        s.delete(f"{BASE_URL}/api/users/{uid}")


@pytest.fixture(scope="module")
def kow_client_id(sa):
    r = sa.get(f"{BASE_URL}/api/devices")
    return [d for d in r.json()["devices"] if d["device_id"] == "kowalski-a"][0]["client_id"]


def mkuser(sa, cid, role):
    email = f"test_{role}_{uuid.uuid4().hex[:6]}@example.com"
    r = sa.post(f"{BASE_URL}/api/users", json={"email": email, "password": PW, "role": role, "client_id": cid})
    assert r.status_code in (200, 201), r.text
    CREATED_USERS.append(r.json().get("id"))
    s = sess()
    assert s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": PW}).status_code == 200
    return s


# Superadmin rename / reset / validation
def test_sa_rename_and_reset(sa):
    r = sa.put(url("kowalski-a", 0), json={"name": "  Porodówka  "})
    assert r.status_code == 200 and r.json()["name"] == "Porodówka"
    assert names(sa, "kowalski-a").get("0") == "Porodówka"
    r = sa.put(url("kowalski-a", 0), json={"name": "Odchów   nr   2"})
    assert r.json()["name"] == "Odchów nr 2"
    r = sa.put(url("kowalski-a", 0), json={"name": ""})
    assert r.status_code == 200 and r.json()["name"] == "Komora 1"
    assert "0" not in names(sa, "kowalski-a")


def test_whitespace_only_resets(sa):
    sa.put(url("kowalski-a", 1), json={"name": "X"})
    r = sa.put(url("kowalski-a", 1), json={"name": "    "})
    assert r.status_code == 200 and r.json()["name"] == "Komora 2"
    assert "1" not in names(sa, "kowalski-a")


def test_out_of_range(sa):
    assert sa.put(url("kowalski-a", 6), json={"name": "x"}).status_code == 404
    assert sa.put(url("kowalski-a", -1), json={"name": "x"}).status_code == 404
    assert sa.put(url("chlodnia-01", 3), json={"name": "x"}).status_code == 404
    assert sa.put(url("nope-dev", 0), json={"name": "x"}).status_code == 404


def test_too_long(sa):
    assert sa.put(url("kowalski-a", 0), json={"name": "a" * 31}).status_code == 422
    r = sa.put(url("kowalski-a", 0), json={"name": "a" * 30})
    assert r.status_code == 200
    sa.put(url("kowalski-a", 0), json={"name": ""})


def test_event_logged(sa):
    sa.put(url("kowalski-a", 0), json={"name": "Porodówka"})
    r = sa.get(f"{BASE_URL}/api/events", params={"device_id": "kowalski-a"})
    assert r.status_code == 200
    txt = str(r.json())
    assert "zmieniono nazwę „Komora 1” → „Porodówka”" in txt
    sa.put(url("kowalski-a", 0), json={"name": ""})


def test_unauth():
    assert sess().put(url("kowalski-a", 0), json={"name": "x"}).status_code == 401


# RBAC with client users
def test_rbac(sa, kow_client_id):
    adm = mkuser(sa, kow_client_id, "admin")
    r = adm.put(url("kowalski-a", 2), json={"name": "Warchlakarnia"})
    assert r.status_code == 200 and r.json()["name"] == "Warchlakarnia"
    assert names(adm, "kowalski-a").get("2") == "Warchlakarnia"
    assert adm.put(url("chlodnia-01", 0), json={"name": "hack"}).status_code == 404
    op = mkuser(sa, kow_client_id, "operator")
    assert op.put(url("kowalski-a", 2), json={"name": "op"}).status_code == 403
    vw = mkuser(sa, kow_client_id, "viewer")
    assert vw.put(url("kowalski-a", 2), json={"name": "vw"}).status_code == 403
    assert names(vw, "kowalski-a").get("2") == "Warchlakarnia"
    assert adm.put(url("kowalski-a", 2), json={"name": ""}).status_code == 200

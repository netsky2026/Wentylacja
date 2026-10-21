# Iteration 19: GET /api/clients migrates missing slugs; no-op chamber rename skips event log
import os
import time

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
ADMIN = {"email": "admin@chlewnia.pl", "password": "Wentylacja!2026"}
mongo = MongoClient("mongodb://localhost:27017")["test_database"]


@pytest.fixture(scope="module")
def sa():
    s = requests.Session()
    s.headers.update({"Origin": BASE_URL})
    r = s.post(f"{BASE_URL}/api/auth/login", json=ADMIN)
    if r.status_code != 200:
        pytest.skip("login failed")
    return s


# Slug migration
def test_list_clients_migrates_missing_slug(sa):
    mongo.clients.delete_many({"name": "Stara Ferma Test"})
    ins = mongo.clients.insert_one({"name": "Stara Ferma Test"})
    cid = str(ins.inserted_id)
    try:
        r = sa.get(f"{BASE_URL}/api/clients")
        assert r.status_code == 200
        c = [x for x in r.json()["clients"] if x["id"] == cid]
        assert c and c[0]["slug"] == "stara-ferma-test"
        assert mongo.clients.find_one({"_id": ins.inserted_id})["slug"] == "stara-ferma-test"
        # all clients have slugs
        assert all(x["slug"] for x in r.json()["clients"])
        # resolvable publicly? (site endpoint) - informational
    finally:
        d = sa.delete(f"{BASE_URL}/api/clients/{cid}")
        assert d.status_code in (200, 204), d.text
        assert not mongo.clients.find_one({"_id": ins.inserted_id})


def test_empty_slug_string_migrated(sa):
    ins = mongo.clients.insert_one({"name": "Stara Ferma Test", "slug": ""})
    cid = str(ins.inserted_id)
    try:
        r = sa.get(f"{BASE_URL}/api/clients")
        c = [x for x in r.json()["clients"] if x["id"] == cid][0]
        assert c["slug"] == "stara-ferma-test"
    finally:
        sa.delete(f"{BASE_URL}/api/clients/{cid}")
        mongo.clients.delete_one({"_id": ins.inserted_id})


# No-op chamber rename
def test_noop_rename_no_event(sa):
    url = f"{BASE_URL}/api/devices/kowalski-a/chambers/1/name"
    try:
        assert sa.put(url, json={"name": "TEST_Noop"}).status_code == 200
        time.sleep(0.5)
        before = sa.get(f"{BASE_URL}/api/events?device_id=kowalski-a&limit=500").json()["events"]
        r = sa.put(url, json={"name": "  TEST_Noop "})
        assert r.status_code == 200 and r.json()["name"] == "TEST_Noop"
        after = sa.get(f"{BASE_URL}/api/events?device_id=kowalski-a&limit=500").json()["events"]
        renames_b = [e for e in before if "zmieniono nazwę" in e.get("message", "")]
        renames_a = [e for e in after if "zmieniono nazwę" in e.get("message", "")]
        assert len(renames_a) == len(renames_b)
        assert (renames_a[0]["ts"] if renames_a else None) == (renames_b[0]["ts"] if renames_b else None)
    finally:
        sa.put(url, json={"name": ""})


def test_noop_rename_default_name(sa):
    url = f"{BASE_URL}/api/devices/kowalski-a/chambers/2/name"
    sa.put(url, json={"name": ""})
    before = sa.get(f"{BASE_URL}/api/events?device_id=kowalski-a&limit=500").json()["events"]
    for body in ({"name": ""}, {"name": "Komora 3"}):
        r = sa.put(url, json=body)
        assert r.status_code == 200
    after = sa.get(f"{BASE_URL}/api/events?device_id=kowalski-a&limit=500").json()["events"]
    cnt = lambda ev: len([e for e in ev if "zmieniono nazwę" in e.get("message", "")])
    assert cnt(after) == cnt(before)

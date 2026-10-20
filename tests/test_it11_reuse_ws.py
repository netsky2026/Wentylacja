# Iteration 11 retest: device_id re-use tenant leak + WS revalidation after user deletion
import os
import json
import time
import uuid
import asyncio
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
ORIGIN = {"Origin": BASE_URL}


def env(key):
    for line in open("/app/backend/.env"):
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip().strip('"')


mdb = MongoClient(env("MONGO_URL"))[env("DB_NAME")]


def login(email, pw):
    s = requests.Session()
    s.headers.update(ORIGIN)
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def sa():
    return login("admin@chlewnia.pl", "Wentylacja!2026")


@pytest.fixture(scope="module")
def setup(sa):
    tag = uuid.uuid4().hex[:5]
    a = sa.post(f"{API}/clients", json={"name": f"TEST_A_{tag}"}).json()["id"]
    b = sa.post(f"{API}/clients", json={"name": f"TEST_B_{tag}"}).json()["id"]
    did = f"test-reuse-{tag}"
    ctx = {"a": a, "b": b, "did": did, "tag": tag, "users": []}
    yield ctx
    sa.delete(f"{API}/devices/{did}")
    for uid in ctx["users"]:
        sa.delete(f"{API}/users/{uid}")
    sa.delete(f"{API}/clients/{a}")
    sa.delete(f"{API}/clients/{b}")


def mkuser(sa, ctx, client, role="viewer"):
    em = f"test_{ctx['tag']}_{uuid.uuid4().hex[:4]}@b.pl"
    r = sa.post(f"{API}/users", json={"email": em, "password": "Haslo1234!", "role": role, "client_id": client})
    assert r.status_code in (200, 201), r.text
    ctx["users"].append(r.json()["id"])
    return em, r.json()["id"]


class TestReuseLeak:
    def test_reuse_no_leak(self, sa, setup):
        did, a, b = setup["did"], setup["a"], setup["b"]
        r = sa.post(f"{API}/devices", json={"client_id": a, "name": "devA", "device_id": did, "chambers": 2, "simulated": True})
        assert r.status_code in (200, 201), r.text
        assert sa.put(f"{API}/devices/{did}/thresholds/0", json={"temp_max": 11, "co2_max": 1111}).status_code == 200
        # wait for history samples
        end = time.time() + 60
        while time.time() < end:
            h = sa.get(f"{API}/devices/{did}/history?hours=1").json()
            if h["history"] and h["plant"]:
                break
            time.sleep(4)
        assert h["history"], "no history generated for simulated device A"
        assert mdb.plc_history.count_documents({"device_id": did}) > 0
        assert mdb.plc_events.count_documents({"device_id": did}) > 0
        # delete
        assert sa.delete(f"{API}/devices/{did}").status_code == 200
        time.sleep(3)
        counts = {c: mdb[c].count_documents({"device_id": did}) for c in
                  ("plc_events", "plc_history", "plc_plant_history", "device_thresholds")}
        print("post-delete counts", counts)
        assert all(v == 0 for v in counts.values()), counts
        st = mdb.alarm_state.find_one({"_id": "main"}) or {}
        assert not any(k.startswith(f"{did}:") for k in st.get("active", {}))
        # re-create under B, non-simulated so no new data appears
        r = sa.post(f"{API}/devices", json={"client_id": b, "name": "devB", "device_id": did, "chambers": 2, "simulated": False})
        assert r.status_code in (200, 201), r.text
        em, _ = mkuser(sa, setup, b)
        u = login(em, "Haslo1234!")
        ev = u.get(f"{API}/events?device_id={did}").json()["events"]
        assert not [e for e in ev if e.get("client_id") == a], ev
        assert not [e for e in ev if "devA" in e["message"] or "TEST_A_" in e["message"]], ev
        h = u.get(f"{API}/devices/{did}/history?hours=24").json()
        assert h["history"] == {} and h["plant"] == [], h
        days = u.get(f"{API}/devices/{did}/usage/daily").json()["days"]
        assert all(d["kwh"] == 0 and d["water_m3"] == 0 for d in days), days
        csv = u.get(f"{API}/devices/{did}/history/csv?chamber=0&hours=24").text
        assert len(csv.strip().splitlines()) == 1, csv[:300]
        th = u.get(f"{API}/devices/{did}/thresholds").json()["thresholds"]
        assert th[0]["temp_max"] != 11, th

    def test_events_scoped_by_client(self, sa, setup):
        # event inserted in DB for device_id with foreign client_id must not be returned
        did, a, b = setup["did"], setup["a"], setup["b"]
        mdb.plc_events.insert_one({"level": "info", "message": "TEST_FOREIGN_LEAK", "meta": {}, "device_id": did,
                                   "client_id": a, "ts": "2099-01-01T00:00:00+00:00"})
        try:
            em, _ = mkuser(sa, setup, b)
            u = login(em, "Haslo1234!")
            ev = u.get(f"{API}/events?device_id={did}").json()["events"]
            assert not [e for e in ev if e["message"] == "TEST_FOREIGN_LEAK"]
            ev_sa = sa.get(f"{API}/events?device_id={did}").json()["events"]
            assert not [e for e in ev_sa if e["message"] == "TEST_FOREIGN_LEAK"]
            # client A user cannot query B device
            ema, _ = mkuser(sa, setup, a)
            ua = login(ema, "Haslo1234!")
            assert ua.get(f"{API}/events?device_id={did}").status_code in (403, 404)
        finally:
            mdb.plc_events.delete_many({"message": "TEST_FOREIGN_LEAK"})


class TestWsRevalidate:
    def test_ws_closed_after_user_delete(self, sa, setup):
        import websockets
        em, uid = mkuser(sa, setup, setup["b"])
        u = login(em, "Haslo1234!")
        cookie = u.cookies.get("access_token")
        url = BASE_URL.replace("https", "wss") + "/api/ws"

        async def run():
            async with websockets.connect(url, additional_headers={"Cookie": f"access_token={cookie}", "Origin": BASE_URL}) as ws:
                await asyncio.sleep(1)
                t0 = time.time()
                assert sa.delete(f"{API}/users/{uid}").status_code == 200
                try:
                    while time.time() - t0 < 50:
                        await asyncio.wait_for(ws.recv(), 50)
                except websockets.ConnectionClosed as e:
                    return time.time() - t0, e.code if hasattr(e, "code") else e.rcvd.code
                except asyncio.TimeoutError:
                    return None, None
            return None, None

        dt, code = asyncio.run(run())
        print("ws closed after", dt, "code", code)
        assert dt is not None and dt <= 45, dt

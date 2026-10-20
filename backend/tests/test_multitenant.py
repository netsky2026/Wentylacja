# Multi-tenant regression tests: devices registry, fleet CRUD, tenant isolation, MQTT validation, per-client alarms
import os
import json
import time
import uuid
import asyncio
import pytest
import requests
import paho.mqtt.client as mqtt

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
SA_EMAIL, SA_PW = "admin@chlewnia.pl", "Wentylacja!2026"
PREFIX = "emgt-fatek-7f3a9c"
TAG = uuid.uuid4().hex[:6]


def login(email, pw):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=20)
    assert r.status_code == 200, r.text
    return s


def wait_for(fn, timeout=40, step=2):
    end = time.time() + timeout
    while time.time() < end:
        v = fn()
        if v:
            return v
        time.sleep(step)
    return None


def mqtt_publish(topic, payload, n=3):
    c = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id=f"t1-{uuid.uuid4().hex[:8]}")
    c.connect("broker.hivemq.com", 1883, 30)
    c.loop_start()
    for _ in range(n):
        c.publish(topic, json.dumps(payload), qos=1).wait_for_publish(10)
        time.sleep(0.5)
    c.loop_stop()
    c.disconnect()


def fake_state(n):
    return {"model": "T1-INJECT", "chambers": [
        {"id": i, "temp": 21.0, "setpoint": 21.0, "humidity": 60.0, "co2": 1000.0, "on": True, "heating": False,
         "mode": "auto", "curtain_left": 10.0, "curtain_right": 10.0, "chimney": 10.0} for i in range(n)],
        "plant": {"power_kw": 1.0}}


@pytest.fixture(scope="module")
def sa():
    return login(SA_EMAIL, SA_PW)


@pytest.fixture(scope="module")
def ids(sa):
    cl = {c["name"]: c["id"] for c in sa.get(f"{API}/clients").json()["clients"]}
    assert "Marco Polo" in cl and "Ferma Kowalski" in cl
    return {"mp": cl["Marco Polo"], "fk": cl["Ferma Kowalski"]}


@pytest.fixture(scope="module")
def kusers(sa, ids):
    out, created = {}, []
    for role in ("admin", "operator", "viewer"):
        email = f"test_{TAG}_{role}@kowalski.pl"
        r = sa.post(f"{API}/users", json={"email": email, "name": role, "password": "Haslo1234!", "role": role,
                                          "client_id": ids["fk"]})
        assert r.status_code == 200, r.text
        assert r.json()["client_id"] == ids["fk"]
        created.append(r.json()["id"])
        out[role] = login(email, "Haslo1234!")
    mp = sa.post(f"{API}/users", json={"email": f"test_{TAG}_mpop@marcopolo.pl", "password": "Haslo1234!",
                                        "role": "operator", "client_id": ids["mp"]})
    assert mp.status_code == 200
    out["mp_user_id"] = mp.json()["id"]
    created.append(mp.json()["id"])
    yield out
    for uid in created:
        sa.delete(f"{API}/users/{uid}")
    for u in sa.get(f"{API}/users").json()["users"]:
        if u["email"].startswith(f"test_{TAG}"):
            sa.delete(f"{API}/users/{u['id']}")


# ---------- superadmin device registry ----------
class TestRegistry:
    def test_devices_superadmin(self, sa):
        devs = {d["device_id"]: d for d in sa.get(f"{API}/devices").json()["devices"]}
        assert devs["kowalski-a"]["chambers"] == 6 and devs["kowalski-a"]["client_name"] == "Ferma Kowalski"
        assert devs["chlodnia-01"]["chambers"] == 3 and devs["chlodnia-01"]["client_name"] == "Marco Polo"
        assert "state_topic" in devs["kowalski-a"]

    def test_devices_online_with_state(self, sa):
        def ok():
            d = {x["device_id"]: x for x in sa.get(f"{API}/devices").json()["devices"]}
            return all(d[k]["online"] and d[k]["state"] for k in ("kowalski-a", "chlodnia-01")) and d
        d = wait_for(ok, 60)
        assert d, "devices not online"
        assert len(d["kowalski-a"]["state"]["chambers"]) == 6
        assert len(d["chlodnia-01"]["state"]["chambers"]) == 3

    def test_chamber_bounds(self, sa):
        assert sa.post(f"{API}/devices/kowalski-a/command", json={"type": "set_mode", "chamber": 6, "value": "auto"}).status_code == 422
        assert sa.post(f"{API}/devices/chlodnia-01/command", json={"type": "set_mode", "chamber": 3, "value": "auto"}).status_code == 422
        assert sa.put(f"{API}/devices/kowalski-a/thresholds/6", json={"temp_max": 28, "co2_max": 3000}).status_code == 404
        assert sa.get(f"{API}/devices/kowalski-a/history/csv?chamber=6").status_code == 404
        assert sa.get(f"{API}/devices/nope-xyz/thresholds").status_code == 404

    def test_device_endpoints(self, sa):
        assert len(sa.get(f"{API}/devices/kowalski-a/thresholds").json()["thresholds"]) == 6
        h = sa.get(f"{API}/devices/kowalski-a/history?hours=3").json()
        assert "history" in h and "plant" in h
        assert len(sa.get(f"{API}/devices/kowalski-a/usage/daily?days=7").json()["days"]) == 7
        r = sa.get(f"{API}/devices/kowalski-a/history/csv?chamber=5&hours=24")
        assert r.status_code == 200 and "czas;temperatura_C" in r.text
        ev = sa.get(f"{API}/events?device_id=kowalski-a").json()["events"]
        assert all(e.get("device_id") in ("kowalski-a", None) for e in ev)


# ---------- fleet CRUD ----------
class TestFleet:
    def test_fleet_lifecycle(self, sa):
        r = sa.post(f"{API}/clients", json={"name": f"TEST_client_{TAG}"})
        assert r.status_code == 200
        cid = r.json()["id"]
        did = f"test-{TAG}"
        try:
            r = sa.post(f"{API}/devices", json={"client_id": cid, "name": "TEST sim", "device_id": did, "chambers": 4, "simulated": True})
            assert r.status_code == 200, r.text
            assert r.json()["mqtt_username"] == did and len(r.json()["mqtt_password"]) > 10
            cr = sa.get(f"{API}/devices/{did}/credentials").json()
            assert cr["mqtt_password"] == r.json()["mqtt_password"]
            assert cr["state_topic"] == f"{PREFIX}/{did}/state" and cr["broker_host"]
            # duplicate / invalid
            assert sa.post(f"{API}/devices", json={"client_id": cid, "name": "x", "device_id": did, "chambers": 2}).status_code == 409
            assert sa.post(f"{API}/devices", json={"client_id": cid, "name": "x", "device_id": "Bad ID!", "chambers": 2}).status_code == 422
            assert sa.post(f"{API}/devices", json={"client_id": cid, "name": "x", "device_id": f"ok-{TAG}", "chambers": 11}).status_code == 422
            assert sa.post(f"{API}/devices", json={"client_id": "000000000000000000000000", "name": "x", "device_id": f"ok-{TAG}", "chambers": 2}).status_code == 422
            # online with 4 chambers
            def online():
                d = next((x for x in sa.get(f"{API}/devices").json()["devices"] if x["device_id"] == did), None)
                return d and d["online"] and d["state"] and len(d["state"]["chambers"]) == 4
            assert wait_for(online, 40), "simulated device did not come online"
            # client delete blocked
            assert sa.delete(f"{API}/clients/{cid}").status_code == 409
            # toggle simulator off -> offline
            r = sa.patch(f"{API}/devices/{did}", json={"simulated": False})
            assert r.status_code == 200 and r.json()["simulated"] is False
            def offline():
                d = next(x for x in sa.get(f"{API}/devices").json()["devices"] if x["device_id"] == did)
                return not d["online"]
            assert wait_for(offline, 25), "device stayed online after simulator off"
        finally:
            assert sa.delete(f"{API}/devices/{did}").status_code == 200
            assert all(d["device_id"] != did for d in sa.get(f"{API}/devices").json()["devices"])
            assert sa.get(f"{API}/devices/{did}/credentials").status_code == 404
            assert sa.delete(f"{API}/clients/{cid}").status_code == 200
            assert all(c["id"] != cid for c in sa.get(f"{API}/clients").json()["clients"])

    def test_mqtt_wrong_chamber_count_and_unknown_device(self, sa):
        cid = sa.post(f"{API}/clients", json={"name": f"TEST_mq_{TAG}"}).json()["id"]
        did = f"test-mq-{TAG}"
        try:
            assert sa.post(f"{API}/devices", json={"client_id": cid, "name": "real", "device_id": did, "chambers": 2}).status_code == 200
            mqtt_publish(f"{PREFIX}/{did}/state", fake_state(3))
            mqtt_publish(f"{PREFIX}/test-ghost-{TAG}/state", fake_state(2))
            time.sleep(3)
            devs = {x["device_id"]: x for x in sa.get(f"{API}/devices").json()["devices"]}
            assert devs[did]["state"] is None and not devs[did]["online"], "wrong chamber count accepted"
            assert f"test-ghost-{TAG}" not in devs
            # positive control
            mqtt_publish(f"{PREFIX}/{did}/state", fake_state(2))
            def ok():
                d = next(x for x in sa.get(f"{API}/devices").json()["devices"] if x["device_id"] == did)
                return d["state"] and len(d["state"]["chambers"]) == 2
            assert wait_for(ok, 20), "valid payload for real device not accepted"
        finally:
            sa.delete(f"{API}/devices/{did}")
            sa.delete(f"{API}/clients/{cid}")


# ---------- tenant isolation ----------
class TestIsolation:
    def test_admin_sees_only_own(self, kusers, ids):
        a = kusers["admin"]
        devs = [d["device_id"] for d in a.get(f"{API}/devices").json()["devices"]]
        assert devs == ["kowalski-a"]
        assert "state_topic" not in a.get(f"{API}/devices").json()["devices"][0]
        for p in ("thresholds", "history", "usage/daily", "history/csv?chamber=0"):
            assert a.get(f"{API}/devices/chlodnia-01/{p}").status_code == 404, p
        assert a.get(f"{API}/events?device_id=chlodnia-01").status_code == 404
        ev = a.get(f"{API}/events?limit=500").json()["events"]
        assert all(e.get("client_id") == ids["fk"] for e in ev)
        assert all(e.get("device_id") != "chlodnia-01" for e in a.get(f"{API}/events?device_id=kowalski-a&limit=500").json()["events"])
        assert a.post(f"{API}/devices/chlodnia-01/command", json={"type": "set_mode", "chamber": 0, "value": "auto"}).status_code == 404
        assert a.get(f"{API}/config").json().get("username") is None

    def test_admin_users_scope(self, kusers, ids):
        a = kusers["admin"]
        users = a.get(f"{API}/users").json()["users"]
        assert users and all(u["client_id"] == ids["fk"] for u in users)
        assert a.get(f"{API}/users?client_id={ids['mp']}").json()["users"] == users
        assert a.post(f"{API}/users", json={"email": f"test_{TAG}_sa@x.pl", "password": "Haslo1234!", "role": "superadmin"}).status_code == 403
        r = a.post(f"{API}/users", json={"email": f"test_{TAG}_emp@kowalski.pl", "password": "Haslo1234!", "role": "viewer", "client_id": ids["mp"]})
        assert r.status_code == 200 and r.json()["client_id"] == ids["fk"]
        assert a.delete(f"{API}/users/{r.json()['id']}").status_code == 200
        assert a.delete(f"{API}/users/{kusers['mp_user_id']}").status_code == 404

    def test_admin_alarm_settings_scope(self, kusers, ids):
        a = kusers["admin"]
        g = a.get(f"{API}/alarm-settings?client_id={ids['mp']}").json()
        assert g["client_id"] == ids["fk"]
        r = a.put(f"{API}/alarm-settings?client_id={ids['mp']}", json={"enabled": True, "recipients": [{"type": "email", "value": "TEST_k@kowalski.pl"}]})
        assert r.status_code == 200 and r.json()["client_id"] == ids["fk"]
        a.put(f"{API}/alarm-settings", json={"enabled": True, "recipients": []})

    def test_admin_forbidden_superadmin_routes(self, kusers, ids):
        a = kusers["admin"]
        assert a.get(f"{API}/clients").status_code == 403
        assert a.post(f"{API}/clients", json={"name": "x"}).status_code == 403
        assert a.post(f"{API}/devices", json={"client_id": ids["fk"], "name": "x", "device_id": "xx-1", "chambers": 1}).status_code == 403
        assert a.get(f"{API}/devices/kowalski-a/credentials").status_code == 403
        assert a.patch(f"{API}/devices/kowalski-a", json={"simulated": False}).status_code == 403
        assert a.delete(f"{API}/devices/kowalski-a").status_code == 403
        assert a.put(f"{API}/broker", json={"host": "broker.hivemq.com", "port": 1883, "prefix": "x"}).status_code == 403

    def test_operator(self, kusers):
        o = kusers["operator"]
        assert o.get(f"{API}/users").status_code == 403
        assert o.get(f"{API}/alarm-settings").status_code == 403
        assert o.get(f"{API}/clients").status_code == 403
        assert o.post(f"{API}/devices", json={}).status_code in (403, 422)
        assert o.put(f"{API}/broker", json={"host": "a.b", "port": 1, "prefix": "x"}).status_code == 403
        assert o.post(f"{API}/devices/kowalski-a/command", json={"type": "set_mode", "chamber": 5, "value": "auto"}).status_code == 200
        assert o.put(f"{API}/devices/kowalski-a/thresholds/5", json={"temp_max": 28, "co2_max": 3000}).status_code == 200
        assert o.post(f"{API}/devices/chlodnia-01/command", json={"type": "set_mode", "chamber": 0, "value": "auto"}).status_code == 404

    def test_viewer(self, kusers):
        v = kusers["viewer"]
        assert [d["device_id"] for d in v.get(f"{API}/devices").json()["devices"]] == ["kowalski-a"]
        assert v.get(f"{API}/devices/kowalski-a/thresholds").status_code == 200
        assert v.post(f"{API}/devices/kowalski-a/command", json={"type": "set_mode", "chamber": 0, "value": "auto"}).status_code == 403
        assert v.put(f"{API}/devices/kowalski-a/thresholds/0", json={"temp_max": 28, "co2_max": 3000}).status_code == 403
        assert v.get(f"{API}/users").status_code == 403

    def test_ws_isolation(self, kusers, sa):
        import websockets
        cookie = kusers["viewer"].cookies.get("access_token")
        url = BASE_URL.replace("https", "wss") + "/api/ws"

        async def run():
            seen = set()
            async with websockets.connect(url, additional_headers={"Cookie": f"access_token={cookie}"}) as ws:
                # trigger an event on chlodnia-01 via superadmin
                sa.post(f"{API}/devices/chlodnia-01/command", json={"type": "set_mode", "chamber": 0, "value": "auto"})
                end = time.time() + 8
                while time.time() < end:
                    try:
                        m = json.loads(await asyncio.wait_for(ws.recv(), 2))
                    except asyncio.TimeoutError:
                        continue
                    if m["type"] == "state":
                        seen.add(m["payload"]["device_id"])
                    elif m["type"] == "event":
                        seen.add(m["event"].get("device_id") or "none")
            return seen
        seen = asyncio.run(run())
        assert "kowalski-a" in seen
        assert "chlodnia-01" not in seen


# ---------- per-client alarm notifications (mocked) ----------
class TestAlarms:
    def test_alarm_only_for_owner_client(self, sa, ids):
        fk_mail, mp_mail = f"test_{TAG}_fk@kowalski.pl", f"test_{TAG}_mp@marcopolo.pl"
        assert sa.put(f"{API}/alarm-settings?client_id={ids['fk']}", json={"recipients": [{"type": "email", "value": fk_mail}]}).status_code == 200
        assert sa.put(f"{API}/alarm-settings?client_id={ids['mp']}", json={"recipients": [{"type": "email", "value": mp_mail}]}).status_code == 200
        assert sa.get(f"{API}/alarm-settings").status_code == 422
        try:
            assert sa.put(f"{API}/devices/kowalski-a/thresholds/2", json={"temp_max": 5, "co2_max": 3000}).status_code == 200
            def got():
                rec = sa.get(f"{API}/alarm-settings?client_id={ids['fk']}").json()["recent"]
                return [n for n in rec if n["to"] == fk_mail and n["kind"] == "alarm" and "Komora 3" in n["subject"]]
            n = wait_for(got, 40)
            assert n, "no notification for Ferma Kowalski"
            assert "Ferma Kowalski" in n[0]["subject"]
            mp_rec = sa.get(f"{API}/alarm-settings?client_id={ids['mp']}").json()["recent"]
            assert not any("Kowalski" in x["subject"] or x["to"] == fk_mail for x in mp_rec)
        finally:
            sa.put(f"{API}/devices/kowalski-a/thresholds/2", json={"temp_max": 28, "co2_max": 3000})
            time.sleep(8)
            sa.put(f"{API}/alarm-settings?client_id={ids['fk']}", json={"recipients": []})
            sa.put(f"{API}/alarm-settings?client_id={ids['mp']}", json={"recipients": []})

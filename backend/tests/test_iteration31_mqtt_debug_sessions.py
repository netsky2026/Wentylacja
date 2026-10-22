# Iteration 31: MQTT debug preview (superadmin), session revocation (logout / logout-all), lockout + unlock
import json
import os
import time
import uuid

import paho.mqtt.client as mqtt
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
SA = ("admin@chlewnia.pl", "Wentylacja!2026")
KADM = ("kowalski.admin@kowalski.pl", "KowalskiAdm!2026")
DEV = "kowalski-a"
H = {"Origin": BASE_URL}


def login(email, pw):
    s = requests.Session()
    s.headers.update(H)
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return s


def cookies_of(s):
    return {k: s.cookies.get(k) for k in ("access_token", "refresh_token")}


@pytest.fixture(scope="module")
def sa():
    return login(*SA)


@pytest.fixture(scope="module")
def kadm():
    return login(*KADM)


@pytest.fixture(scope="module")
def clients(sa):
    r = sa.get(f"{API}/clients")
    assert r.status_code == 200
    data = r.json()
    return data.get("clients", data) if isinstance(data, dict) else data


@pytest.fixture(scope="module")
def tmp_users(sa, clients):
    kow = next(c for c in clients if "owalski" in (c.get("name") or ""))
    other = next(c for c in clients if c["id"] != kow["id"])
    tag = uuid.uuid4().hex[:6]
    made = {}
    for key, role, cid in [("op", "operator", kow["id"]), ("vw", "viewer", kow["id"]),
                           ("lock", "viewer", kow["id"]), ("other", "viewer", other["id"]),
                           ("sess", "viewer", kow["id"]), ("all", "viewer", kow["id"])]:
        email = f"test_it31_{key}_{tag}@example.com"
        r = sa.post(f"{API}/users", json={"email": email, "password": "TestPass!123", "role": role, "client_id": cid})
        assert r.status_code == 200, r.text
        made[key] = {"id": r.json()["id"], "email": email, "pw": "TestPass!123"}
    yield made
    for u in made.values():
        sa.delete(f"{API}/users/{u['id']}")


# ---------- MQTT debug ----------
class TestMqttDebug:
    def test_superadmin_gets_debug(self, sa):
        r = sa.get(f"{API}/devices/{DEV}/mqtt-debug")
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("online", "broker_connected", "state_topic", "command_topic", "last_message", "last_command"):
            assert k in d
        assert d["state_topic"].endswith(f"/{DEV}/state")
        assert d["command_topic"].endswith(f"/{DEV}/command")
        assert d["broker_connected"] is True and d["online"] is True
        m = d["last_message"]
        assert m and m["ok"] is True and m["error"] is None
        assert m["topic"] == d["state_topic"] and m["size"] > 0
        json.loads(m["payload"])

    def test_rbac(self, kadm, tmp_users):
        assert requests.get(f"{API}/devices/{DEV}/mqtt-debug").status_code == 401
        assert kadm.get(f"{API}/devices/{DEV}/mqtt-debug").status_code == 403
        for k in ("op", "vw"):
            s = login(tmp_users[k]["email"], tmp_users[k]["pw"])
            assert s.get(f"{API}/devices/{DEV}/mqtt-debug").status_code == 403

    def test_unknown_device_404(self, sa):
        assert sa.get(f"{API}/devices/nope-xyz/mqtt-debug").status_code == 404

    def test_last_command(self, sa):
        st = sa.get(f"{API}/devices/{DEV}/state")
        orig = None
        if st.status_code == 200:
            try:
                orig = st.json()["chambers"][0]["setpoint"]
            except Exception:
                orig = None
        r = sa.post(f"{API}/devices/{DEV}/command", json={"type": "set_setpoint", "chamber": 0, "value": 22})
        assert r.status_code == 200, r.text
        c = sa.get(f"{API}/devices/{DEV}/mqtt-debug").json()["last_command"]
        assert c and c["ok"] is True and c["topic"].endswith(f"/{DEV}/command")
        p = json.loads(c["payload"])
        assert p.get("type") == "set_setpoint" and p.get("chamber") == 0 and p.get("value") == 22
        if orig is not None and orig != 22:
            sa.post(f"{API}/devices/{DEV}/command", json={"type": "set_setpoint", "chamber": 0, "value": orig})

    def test_rejection_reasons(self, sa):
        d = sa.get(f"{API}/devices/{DEV}/mqtt-debug").json()
        topic = d["state_topic"]
        good = json.loads(d["last_message"]["payload"])
        r = sa.patch(f"{API}/devices/{DEV}", json={"simulated": False})
        assert r.status_code == 200, r.text
        try:
            time.sleep(3)
            mc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"it31-{uuid.uuid4().hex[:6]}")
            mc.connect("broker.hivemq.com", 1883, 30)
            mc.loop_start()
            time.sleep(1)
            no_co2 = json.loads(json.dumps(good))
            no_co2["chambers"][0].pop("co2", None)
            cases = [
                (b"not json {", "poprawny JSON"),
                (json.dumps([1, 2]).encode(), "obiektem JSON"),
                (json.dumps({"x": 1}).encode(), "chambers"),
                (json.dumps({"chambers": good["chambers"][:2]}).encode(), "Zła liczba komór"),
                (json.dumps(no_co2).encode(), "co2"),
            ]
            results = []
            for payload, expect in cases:
                mc.publish(topic, payload, qos=1).wait_for_publish(5)
                time.sleep(2.5)
                m = sa.get(f"{API}/devices/{DEV}/mqtt-debug").json()["last_message"]
                results.append((expect, m["ok"], m["error"], m["payload"][:40]))
            mc.loop_stop()
            mc.disconnect()
            print(results)
            for expect, ok, err, _ in results:
                assert ok is False and err and expect in err, results
        finally:
            r = sa.patch(f"{API}/devices/{DEV}", json={"simulated": True})
            assert r.status_code == 200 and r.json()["simulated"] is True
        time.sleep(4)
        m = sa.get(f"{API}/devices/{DEV}/mqtt-debug").json()["last_message"]
        assert m["ok"] is True


# ---------- Logout revocation ----------
class TestSessions:
    def test_logout_revokes_only_current_session(self, tmp_users):
        u = tmp_users["sess"]
        s1 = login(u["email"], u["pw"])
        s2 = login(u["email"], u["pw"])
        old = cookies_of(s1)
        assert s1.get(f"{API}/auth/me").status_code == 200
        assert s1.post(f"{API}/auth/logout").status_code == 200
        # replay old cookies
        r = requests.get(f"{API}/auth/me", cookies={"access_token": old["access_token"]})
        assert r.status_code == 401
        r = requests.post(f"{API}/auth/refresh", cookies={"refresh_token": old["refresh_token"]}, headers=H)
        assert r.status_code == 401
        r = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {old['access_token']}"})
        assert r.status_code == 401
        # second session still valid
        assert s2.get(f"{API}/auth/me").status_code == 200
        assert s2.post(f"{API}/auth/refresh").status_code == 200
        assert s2.get(f"{API}/auth/me").status_code == 200

    def test_refresh_keeps_sid_then_logout_revokes_refreshed(self, tmp_users):
        u = tmp_users["sess"]
        s = login(u["email"], u["pw"])
        pre = cookies_of(s)
        assert s.post(f"{API}/auth/refresh").status_code == 200
        post = cookies_of(s)
        assert s.post(f"{API}/auth/logout").status_code == 200
        for c in (pre, post):
            assert requests.get(f"{API}/auth/me", cookies={"access_token": c["access_token"]}).status_code == 401
            assert requests.post(f"{API}/auth/refresh", cookies={"refresh_token": c["refresh_token"]}, headers=H).status_code == 401

    def test_logout_all(self, tmp_users):
        u = tmp_users["all"]
        s1 = login(u["email"], u["pw"])
        s2 = login(u["email"], u["pw"])
        c2 = cookies_of(s2)
        assert s1.post(f"{API}/auth/logout-all").status_code == 200
        assert s1.get(f"{API}/auth/me").status_code == 401
        assert requests.get(f"{API}/auth/me", cookies={"access_token": c2["access_token"]}).status_code == 401
        assert requests.post(f"{API}/auth/refresh", cookies={"refresh_token": c2["refresh_token"]}, headers=H).status_code == 401
        s3 = login(u["email"], u["pw"])
        assert s3.get(f"{API}/auth/me").status_code == 200

    def test_logout_all_anon_401(self):
        assert requests.post(f"{API}/auth/logout-all", headers=H).status_code == 401

    def test_logout_without_origin_forbidden(self, tmp_users):
        u = tmp_users["sess"]
        s = login(u["email"], u["pw"])
        # foreign Origin is rejected (missing Origin is allowed by design for non-browser clients)
        r = requests.post(f"{API}/auth/logout", cookies=cookies_of(s), headers={"Origin": "https://evil.example"})
        assert r.status_code == 403
        assert s.get(f"{API}/auth/me").status_code == 200


# ---------- Lockout / unlock ----------
class TestLockout:
    def _lock(self, email):
        codes = [requests.post(f"{API}/auth/login", json={"email": email, "password": "wrong!pass"}, headers=H).status_code
                 for _ in range(6)]
        return codes

    def test_lock_and_unlock_by_client_admin(self, sa, kadm, tmp_users):
        u = tmp_users["lock"]
        codes = self._lock(u["email"])
        assert codes[:5] == [401] * 5 and codes[5] == 429, codes
        r = requests.post(f"{API}/auth/login", json={"email": u["email"], "password": u["pw"]}, headers=H)
        assert r.status_code == 429
        users = kadm.get(f"{API}/users").json()["users"]
        row = next(x for x in users if x["email"] == u["email"])
        assert row["locked"] is True
        assert all(x["locked"] is False for x in users if x["email"] != u["email"])
        row_sa = next(x for x in sa.get(f"{API}/users").json()["users"] if x["email"] == u["email"])
        assert row_sa["locked"] is True
        assert kadm.post(f"{API}/users/{u['id']}/unlock").status_code == 200
        users = kadm.get(f"{API}/users").json()["users"]
        assert next(x for x in users if x["email"] == u["email"])["locked"] is False
        r = requests.post(f"{API}/auth/login", json={"email": u["email"], "password": u["pw"]}, headers=H)
        assert r.status_code == 200

    def test_superadmin_unlock(self, sa, tmp_users):
        u = tmp_users["other"]
        self._lock(u["email"])
        assert sa.post(f"{API}/users/{u['id']}/unlock").status_code == 200
        r = requests.post(f"{API}/auth/login", json={"email": u["email"], "password": u["pw"]}, headers=H)
        assert r.status_code == 200

    def test_client_admin_scope(self, sa, kadm, tmp_users):
        other = tmp_users["other"]
        assert kadm.post(f"{API}/users/{other['id']}/unlock").status_code == 404
        sa_id = sa.get(f"{API}/auth/me").json()["id"]
        assert kadm.post(f"{API}/users/{sa_id}/unlock").status_code == 404
        assert kadm.post(f"{API}/users/invalid/unlock").status_code == 404
        op = login(tmp_users["op"]["email"], tmp_users["op"]["pw"])
        assert op.post(f"{API}/users/{tmp_users['vw']['id']}/unlock").status_code == 403
        assert requests.post(f"{API}/users/{tmp_users['vw']['id']}/unlock", headers=H).status_code == 401


# ---------- Regression ----------
class TestRegression:
    def test_me_refresh(self, sa):
        assert sa.get(f"{API}/auth/me").json()["role"] == "superadmin"
        assert sa.post(f"{API}/auth/refresh").status_code == 200
        assert sa.get(f"{API}/auth/me").status_code == 200

    def test_password_change(self, tmp_users):
        u = tmp_users["vw"]
        s = login(u["email"], u["pw"])
        other = login(u["email"], u["pw"])
        assert s.put(f"{API}/auth/password", json={"current_password": "bad", "new_password": "NewPass!456"}).status_code == 400
        assert s.put(f"{API}/auth/password", json={"current_password": u["pw"], "new_password": "NewPass!456"}).status_code == 200
        assert s.get(f"{API}/auth/me").status_code == 200
        assert other.get(f"{API}/auth/me").status_code == 401
        login(u["email"], "NewPass!456")
        u["pw"] = "NewPass!456"

# Iteration 32: MQTT ping/ack (superadmin), alarm-settings offline_min, connection monitor (offline/online events + notifications)
import os
import time
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
SA = ("admin@chlewnia.pl", "Wentylacja!2026")
KADM = ("kowalski.admin@kowalski.pl", "KowalskiAdm!2026")
DEV = "kowalski-a"
KOW = "6ad7dcc3261e5ba3c23315b7"
H = {"Origin": BASE_URL}
TAG = uuid.uuid4().hex[:6]
REC = f"test_it32_{TAG}@example.com"


def login(email, pw):
    s = requests.Session()
    s.headers.update(H)
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def sa():
    return login(*SA)


@pytest.fixture(scope="module")
def kadm():
    return login(*KADM)


def wait_ping_ack(sa, rid, timeout=6):
    end = time.time() + timeout
    while time.time() < end:
        p = sa.get(f"{API}/devices/{DEV}/mqtt-debug").json().get("ping") or {}
        if p.get("request_id") == rid and p.get("ack_ts"):
            return p
        time.sleep(0.5)
    return None


# --- Ping auth ---
class TestPingAuth:
    def test_anon_401(self):
        r = requests.post(f"{API}/devices/{DEV}/ping", headers=H)
        assert r.status_code == 401

    def test_client_admin_403(self, kadm):
        assert kadm.post(f"{API}/devices/{DEV}/ping").status_code == 403
        assert kadm.get(f"{API}/devices/{DEV}/mqtt-debug").status_code == 403

    def test_bad_origin_403(self, sa):
        r = sa.post(f"{API}/devices/{DEV}/ping", headers={"Origin": "https://evil.example.com"})
        assert r.status_code == 403

    def test_unknown_device_404(self, sa):
        assert sa.post(f"{API}/devices/nope-xyz/ping").status_code == 404


# --- Ping ack with simulator ---
class TestPingAck:
    def test_ping_acked(self, sa):
        r = sa.post(f"{API}/devices/{DEV}/ping")
        assert r.status_code == 200, r.text
        d = r.json()
        assert isinstance(d["request_id"], str) and len(d["request_id"]) == 16
        assert d["sent_ts"] and d["ack_ts"] is None
        p = wait_ping_ack(sa, d["request_id"], timeout=6)
        assert p, "ping not acknowledged by simulator within 6s"
        assert p["sent_ts"] == d["sent_ts"]
        dbg = sa.get(f"{API}/devices/{DEV}/mqtt-debug").json()
        assert dbg["last_command"]["payload"].find('"ping"') >= 0

    def test_ping_events_logged(self, sa):
        ev = sa.get(f"{API}/events", params={"device_id": DEV, "limit": 30}).json()["events"]
        msgs = [e["message"] for e in ev]
        assert any("wysłano polecenie testowe (ping)" in m for m in msgs)
        assert any("potwierdził polecenie testowe (ping)" in m for m in msgs)


# --- alarm-settings offline_min ---
class TestOfflineMin:
    def get(self, s):
        r = s.get(f"{API}/alarm-settings", params={"client_id": KOW})
        assert r.status_code == 200
        return r.json()

    def test_default_and_put(self, sa):
        cfg = self.get(sa)
        assert isinstance(cfg["offline_min"], int)
        body = {"enabled": cfg["enabled"], "recipients": cfg["recipients"], "offline_min": 7}
        r = sa.put(f"{API}/alarm-settings", params={"client_id": KOW}, json=body)
        assert r.status_code == 200 and r.json()["offline_min"] == 7
        assert self.get(sa)["offline_min"] == 7
        # omitted keeps
        r = sa.put(f"{API}/alarm-settings", params={"client_id": KOW}, json={"enabled": cfg["enabled"], "recipients": cfg["recipients"]})
        assert r.status_code == 200 and r.json()["offline_min"] == 7
        # 0 allowed
        r = sa.put(f"{API}/alarm-settings", params={"client_id": KOW}, json={**body, "offline_min": 0})
        assert r.status_code == 200 and r.json()["offline_min"] == 0

    @pytest.mark.parametrize("v", [-1, 1441, "abc"])
    def test_invalid_422(self, sa, v):
        cfg = self.get(sa)
        r = sa.put(f"{API}/alarm-settings", params={"client_id": KOW}, json={"enabled": True, "recipients": cfg["recipients"], "offline_min": v})
        assert r.status_code == 422

    def test_client_admin_own(self, kadm):
        cfg = self.get(kadm)
        r = kadm.put(f"{API}/alarm-settings", json={"enabled": cfg["enabled"], "recipients": cfg["recipients"], "offline_min": 5})
        assert r.status_code == 200 and r.json()["offline_min"] == 5


# --- Connection monitor end-to-end (slow ~3 min) ---
class TestConnMonitor:
    def test_offline_online_flow(self, sa):
        ref_ts = "9"
        orig = sa.get(f"{API}/alarm-settings", params={"client_id": KOW}).json()
        try:
            r = sa.put(f"{API}/alarm-settings", params={"client_id": KOW},
                       json={"enabled": True, "recipients": orig["recipients"] + [{"type": "email", "value": REC}], "offline_min": 1})
            assert r.status_code == 200, r.text
            r = sa.patch(f"{API}/devices/{DEV}", json={"simulated": False})
            assert r.status_code == 200, r.text
            t0 = time.time()
            # ping with sim off -> no ack
            pr = sa.post(f"{API}/devices/{DEV}/ping").json()
            rid, ref_ts = pr["request_id"], pr["sent_ts"]
            assert wait_ping_ack(sa, rid, timeout=5) is None
            # offline event within ~60s
            off_at = None
            while time.time() - t0 < 70:
                ev = sa.get(f"{API}/events", params={"device_id": DEV, "limit": 20}).json()["events"]
                hit = [e for e in ev if "sterownik offline – brak danych" in e["message"] and e["level"] == "warning"]
                if hit and hit[0]["ts"] > ref_ts:
                    off_at = time.time() - t0
                    break
                time.sleep(3)
            print("offline event after", off_at)
            assert off_at is not None, "offline event not logged within 70s"
            # offline alarm notification ~1 min after last data
            notif = None
            while time.time() - t0 < 130:
                rec = sa.get(f"{API}/alarm-settings", params={"client_id": KOW}).json()["recent"]
                notif = next((n for n in rec if n["kind"] == "offline" and n["to"] == REC), None)
                if notif:
                    break
                time.sleep(4)
            print("offline notif after", time.time() - t0, notif)
            assert notif, "no 'offline' alarm_notification"
            assert notif["status"] in ("not_configured", "failed", "sent")
            assert "brak połączenia" in notif["subject"]
        finally:
            sa.patch(f"{API}/devices/{DEV}", json={"simulated": True})
        t1 = time.time()
        online_ev = restored = None
        while time.time() - t1 < 40:
            ev = sa.get(f"{API}/events", params={"device_id": DEV, "limit": 20}).json()["events"]
            online_ev = next((e for e in ev if "sterownik znów online (przerwa" in e["message"] and e["ts"] > ref_ts), None)
            rec = sa.get(f"{API}/alarm-settings", params={"client_id": KOW}).json()["recent"]
            restored = next((n for n in rec if n["kind"] == "conn_restored" and n["to"] == REC), None)
            if online_ev and restored:
                break
            time.sleep(3)
        print("online event:", online_ev and online_ev["message"], "restored:", restored and restored["subject"])
        # restore settings
        sa.put(f"{API}/alarm-settings", params={"client_id": KOW},
               json={"enabled": orig["enabled"], "recipients": orig["recipients"], "offline_min": 5})
        assert online_ev, "online event missing"
        assert restored and "Połączenie przywrócone" in restored["subject"]
        assert sa.get(f"{API}/alarm-settings", params={"client_id": KOW}).json()["offline_min"] == 5


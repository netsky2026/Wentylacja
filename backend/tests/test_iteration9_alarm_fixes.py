# Iteration 9: retest of minor alarm fixes (phone validation, dedupe, event message, test 409,
# threshold rounding, alarm_active persisted across backend restart)
import os
import re
import subprocess
import time
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')
API = f"{BASE_URL}/api"
DEV = "chlodnia-01"
ADMIN = {"email": "admin@chlewnia.pl", "password": "Wentylacja!2026"}


def _mongo():
    env = dict(l.strip().split("=", 1) for l in open("/app/backend/.env") if "=" in l)
    return MongoClient(env["MONGO_URL"].strip('"'))[env["DB_NAME"].strip('"')]


DB = _mongo()


def login():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=ADMIN, timeout=15)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def admin():
    s = login()
    yield s
    s = login()
    s.put(f"{API}/alarm-settings", json={"enabled": True, "recipients": []})
    for ch, t in ((0, 26), (1, 28), (2, 30)):
        s.put(f"{API}/thresholds/{ch}", json={"temp_max": t, "co2_max": 3000})
    time.sleep(6)
    DB.alarm_notifications.delete_many({})
    DB.alarm_state.delete_many({})
    DB.login_attempts.delete_many({})


def put(s, recs, enabled=True):
    return s.put(f"{API}/alarm-settings", json={"enabled": enabled, "recipients": recs})


# --- phone validation / dedupe
class TestValidation:
    @pytest.mark.parametrize("v", ["1 2 3 4", "+  1 2 3 4", "12345678", "1234567890123456", "+48 600 abc 200"])
    def test_phone_invalid(self, admin, v):
        r = put(admin, [{"type": "sms", "value": v}])
        assert r.status_code == 422, (v, r.text)

    def test_phone_normalised(self, admin):
        r = put(admin, [{"type": "sms", "value": "+48 600-100-200"}])
        assert r.status_code == 200, r.text
        assert r.json()["recipients"] == [{"type": "sms", "value": "+48600100200"}]

    def test_phone_bounds_ok(self, admin):
        r = put(admin, [{"type": "sms", "value": "123456789"}, {"type": "sms", "value": "+123456789012345"}])
        assert r.status_code == 200, r.text
        assert len(r.json()["recipients"]) == 2

    def test_dedupe(self, admin):
        r = put(admin, [{"type": "email", "value": "a@b.pl"}, {"type": "email", "value": " A@B.pl "},
                        {"type": "sms", "value": "+48 600 100 200"}, {"type": "sms", "value": "+48600-100-200"}])
        assert r.status_code == 200
        assert r.json()["recipients"] == [{"type": "email", "value": "a@b.pl"}, {"type": "sms", "value": "+48600100200"}]
        assert admin.get(f"{API}/alarm-settings").json()["recipients"] == r.json()["recipients"]

    def test_event_message(self, admin):
        put(admin, [{"type": "email", "value": "a@b.pl"}], enabled=False)
        put(admin, [{"type": "email", "value": "a@b.pl"}, {"type": "email", "value": "c@d.pl"}], enabled=True)
        time.sleep(1)
        ev = admin.get(f"{API}/events?limit=20").json()["events"]
        msgs = [(e["message"], e.get("meta", {}).get("user")) for e in ev]
        assert ("Powiadomienia o alarmach WYŁ., odbiorcy: 1", ADMIN["email"]) in msgs, msgs
        assert ("Powiadomienia o alarmach WŁ., odbiorcy: 2", ADMIN["email"]) in msgs, msgs


# --- test send 409
class TestTestSend:
    def test_409_disabled(self, admin):
        put(admin, [{"type": "email", "value": "a@b.pl"}], enabled=False)
        DB.alarm_notifications.delete_many({})
        r = admin.post(f"{API}/alarm-settings/test")
        assert r.status_code == 409
        assert DB.alarm_notifications.count_documents({}) == 0

    def test_409_no_recipients(self, admin):
        put(admin, [], enabled=True)
        assert admin.post(f"{API}/alarm-settings/test").status_code == 409

    def test_200_ok(self, admin):
        DB.alarm_notifications.delete_many({})
        put(admin, [{"type": "email", "value": "a@b.pl"}])
        r = admin.post(f"{API}/alarm-settings/test")
        assert r.status_code == 200
        assert DB.alarm_notifications.count_documents({"kind": "test"}) == 1
        put(admin, [])


# --- threshold rounding
class TestRounding:
    def test_round(self, admin):
        r = admin.put(f"{API}/thresholds/0", json={"temp_max": 14.399999, "co2_max": 2999.6})
        assert r.status_code == 200
        assert r.json()["thresholds"] == {"temp_max": 14.4, "co2_max": 3000.0}
        t = [x for x in admin.get(f"{API}/thresholds").json()["thresholds"] if x["chamber"] == 0][0]
        assert t["temp_max"] == 14.4
        assert DB.chamber_thresholds.find_one({"chamber": 0})["temp_max"] == 14.4
        admin.put(f"{API}/thresholds/0", json={"temp_max": 26, "co2_max": 3000})


def wait_for(fn, timeout=20):
    for _ in range(timeout):
        v = fn()
        if v:
            return v
        time.sleep(1)
    return None


# --- alarm_active persisted across restart
class TestRestartPersistence:
    def test_no_duplicate_after_restart(self, admin):
        assert wait_for(lambda: admin.get(f"{API}/health").json().get("device_online"), 120), "device offline"
        put(admin, [{"type": "email", "value": "test_r@x.pl"}])
        DB.alarm_notifications.delete_many({})
        st = admin.get(f"{API}/device/{DEV}/state").json()["state"]
        assert st["chambers"][0]["on"]
        admin.put(f"{API}/thresholds/0", json={"temp_max": 5.049999, "co2_max": 3000})
        a = wait_for(lambda: DB.alarm_notifications.find_one({"kind": "alarm", "subject": "ALARM: Komora 1"}))
        assert a, "no initial alarm"
        assert re.search(r"> 5\.0°C", a["body"]), a["body"]
        assert "0" in (DB.alarm_state.find_one({"_id": "main"}) or {}).get("active", {})
        subprocess.run(["sudo", "supervisorctl", "restart", "backend"], check=True)
        # wait for backend + SIM online
        time.sleep(5)

        def online():
            try:
                return login().get(f"{API}/health", timeout=5).json().get("device_online")
            except Exception:
                return False
        assert wait_for(online, 120), "backend/device not online after restart"
        time.sleep(15)
        assert DB.alarm_notifications.count_documents({"kind": "alarm", "subject": "ALARM: Komora 1"}) == 1
        s = login()
        st = s.get(f"{API}/device/{DEV}/state").json()["state"]
        assert st["chambers"][0]["alarm"] is True
        s.put(f"{API}/thresholds/0", json={"temp_max": 26, "co2_max": 3000})
        cl = wait_for(lambda: DB.alarm_notifications.find_one({"kind": "cleared", "subject": "Koniec alarmu: Komora 1"}))
        assert cl, "no cleared notification after restart"
        assert "0" not in (DB.alarm_state.find_one({"_id": "main"}) or {}).get("active", {})

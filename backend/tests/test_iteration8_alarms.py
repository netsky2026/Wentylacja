# Iteration 8: alarm-settings CRUD/validation/roles, mocked test notification, alarm notifier
# (start once / no repeat / cleared), action attribution (meta.user) on commands/thresholds/sim/alarm-settings
import os
import time
import uuid
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


def login(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    return s, r


@pytest.fixture(scope="module")
def admin():
    s, r = login(**ADMIN)
    assert r.status_code == 200, r.text
    yield s
    # cleanup
    s.put(f"{API}/alarm-settings", json={"enabled": True, "recipients": []})
    for ch, t in ((0, 26), (1, 28), (2, 30)):
        s.put(f"{API}/thresholds/{ch}", json={"temp_max": t, "co2_max": 3000})
    DB.alarm_notifications.delete_many({})
    for u in DB.users.find({"email": {"$regex": "^test_it8_"}}):
        s.delete(f"{API}/users/{u['_id']}")
    DB.login_attempts.delete_many({})


def mk_user(admin, role):
    email = f"test_it8_{role}_{uuid.uuid4().hex[:6]}@example.com"
    r = admin.post(f"{API}/users", json={"email": email, "name": "TEST", "password": "TestPass123!", "role": role})
    assert r.status_code == 200, r.text
    s, r = login(email, "TestPass123!")
    assert r.status_code == 200
    return s, email


def events(s, n=60):
    return s.get(f"{API}/events?limit={n}").json()["events"]


# --- alarm-settings CRUD + validation
class TestAlarmSettings:
    def test_get_shape(self, admin):
        r = admin.get(f"{API}/alarm-settings")
        assert r.status_code == 200
        d = r.json()
        assert d["channel_configured"] is False
        assert d["reminder_min"] == 30
        assert isinstance(d["recipients"], list) and isinstance(d["recent"], list)

    def test_put_normalise(self, admin):
        r = admin.put(f"{API}/alarm-settings", json={"enabled": True, "recipients": [
            {"type": "email", "value": "  TEST_Jan@Firma.PL "}, {"type": "sms", "value": "+48 600 100 200"}]})
        assert r.status_code == 200, r.text
        recs = r.json()["recipients"]
        assert recs == [{"type": "email", "value": "test_jan@firma.pl"}, {"type": "sms", "value": "+48600100200"}]
        g = admin.get(f"{API}/alarm-settings").json()
        assert g["recipients"] == recs and g["enabled"] is True
        ev = events(admin, 10)
        assert any(e["message"] == "Odbiorcy alarmów: 2" and e.get("meta", {}).get("user") == ADMIN["email"] for e in ev)

    @pytest.mark.parametrize("rec", [
        {"type": "email", "value": "not-an-email"}, {"type": "email", "value": "a@b"},
        {"type": "email", "value": "a@b.pl;c@d.pl"}, {"type": "sms", "value": "abc12345"},
        {"type": "sms", "value": "12345"}, {"type": "fax", "value": "+48600100200"}])
    def test_put_invalid(self, admin, rec):
        r = admin.put(f"{API}/alarm-settings", json={"enabled": True, "recipients": [rec]})
        assert r.status_code == 422, (rec, r.status_code, r.text)

    def test_roles_forbidden(self, admin):
        for role in ("viewer", "operator"):
            s, _ = mk_user(admin, role)
            assert s.get(f"{API}/alarm-settings").status_code == 403
            assert s.put(f"{API}/alarm-settings", json={"enabled": True, "recipients": []}).status_code == 403
            assert s.post(f"{API}/alarm-settings/test").status_code == 403

    def test_unauth(self):
        assert requests.get(f"{API}/alarm-settings").status_code == 401

    def test_send_test(self, admin):
        DB.alarm_notifications.delete_many({})
        admin.put(f"{API}/alarm-settings", json={"enabled": True, "recipients": [
            {"type": "email", "value": "test_a@x.pl"}, {"type": "sms", "value": "+48600100200"}]})
        r = admin.post(f"{API}/alarm-settings/test")
        assert r.status_code == 200
        docs = list(DB.alarm_notifications.find({"kind": "test"}))
        assert len(docs) == 2
        assert all(d["status"] == "mocked" for d in docs)
        assert {d["to"] for d in docs} == {"test_a@x.pl", "+48600100200"}
        assert len(r.json()["recent"]) == 2
        time.sleep(1)
        ev = events(admin, 10)
        assert any(e["message"].startswith("Powiadomienie (2 odb., tryb testowy)") for e in ev)

    def test_disabled_sends_nothing(self, admin):
        DB.alarm_notifications.delete_many({})
        admin.put(f"{API}/alarm-settings", json={"enabled": False, "recipients": [{"type": "email", "value": "test_a@x.pl"}]})
        admin.post(f"{API}/alarm-settings/test")
        assert DB.alarm_notifications.count_documents({}) == 0
        admin.put(f"{API}/alarm-settings", json={"enabled": True, "recipients": [{"type": "email", "value": "test_a@x.pl"}]})


# --- alarm notifier lifecycle on chamber 1
class TestNotifier:
    def test_alarm_once_then_cleared(self, admin):
        admin.put(f"{API}/alarm-settings", json={"enabled": True, "recipients": [{"type": "email", "value": "test_n@x.pl"}]})
        DB.alarm_notifications.delete_many({})
        st = admin.get(f"{API}/device/{DEV}/state").json()["state"]
        ch0 = st["chambers"][0]
        assert ch0["on"]
        admin.put(f"{API}/thresholds/0", json={"temp_max": ch0["temp"] - 5, "co2_max": 3000})
        found = None
        for _ in range(15):
            time.sleep(1)
            found = DB.alarm_notifications.find_one({"kind": "alarm", "subject": "ALARM: Komora 1"})
            if found:
                break
        assert found, "no alarm notification within 15s"
        assert found["status"] == "mocked" and found["to"] == "test_n@x.pl"
        time.sleep(12)
        assert DB.alarm_notifications.count_documents({"kind": "alarm", "subject": "ALARM: Komora 1"}) == 1
        assert DB.alarm_notifications.count_documents({"kind": "reminder"}) == 0
        admin.put(f"{API}/thresholds/0", json={"temp_max": 26, "co2_max": 3000})
        cl = None
        for _ in range(15):
            time.sleep(1)
            cl = DB.alarm_notifications.find_one({"kind": "cleared"})
            if cl:
                break
        assert cl and cl["subject"] == "Koniec alarmu: Komora 1"


# --- action attribution
class TestAttribution:
    def test_command_attribution(self, admin):
        s, email = mk_user(admin, "operator")
        cmds = [{"type": "set_setpoint", "chamber": 0, "value": 20},
                {"type": "set_mode", "chamber": 0, "value": "auto"},
                {"type": "chamber_power", "chamber": 2, "value": False},
                {"type": "set_vent", "chamber": 0, "value": {"chimney": 40}}]
        for c in cmds:
            assert s.post(f"{API}/device/{DEV}/command", json=c).status_code == 200
        assert s.put(f"{API}/thresholds/1", json={"temp_max": 28, "co2_max": 3000}).status_code == 200
        time.sleep(1.5)
        mine = [e for e in events(admin, 40) if e.get("meta", {}).get("user") == email]
        assert len(mine) >= 5, [e["message"] for e in mine]
        assert sum(1 for e in mine if e["level"] == "command") >= 4

    def test_simulator_toggle_attribution(self, admin):
        assert admin.post(f"{API}/simulator/toggle?enable=true").status_code == 200
        time.sleep(1)
        ev = events(admin, 10)
        assert any(e["message"] == "Symulator włączony" and e["meta"].get("user") == ADMIN["email"] for e in ev)

# Auth & security tests: JWT cookie login/logout/refresh, unauth 401, roles 403, brute force 429,
# password change, origin guard, broker SSRF block + encrypted password, MQTT state sanitization, CSV
import os
import json
import time
import uuid
import asyncio
import pytest
import requests
import paho.mqtt.client as mqtt
import websockets

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')
API = f"{BASE_URL}/api"
DEV = "chlodnia-01"
ADMIN = {"email": "admin@chlewnia.pl", "password": "Wentylacja!2026"}
ORIG_BROKER = {"host": "broker.hivemq.com", "port": 1883, "username": "", "tls": False,
               "prefix": "emgt-fatek-7f3a9c", "device_id": DEV}


def login(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    return s, r


@pytest.fixture(scope="module")
def admin():
    s, r = login(**ADMIN)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def users(admin):
    created = {}
    for role in ("viewer", "operator"):
        email = f"test_{role}_{uuid.uuid4().hex[:6]}@example.com"
        r = admin.post(f"{API}/users", json={"email": email, "name": f"TEST {role}", "password": "TestPass123!", "role": role})
        assert r.status_code == 200, r.text
        assert r.json()["role"] == role and r.json()["email"] == email
        created[role] = (r.json()["id"], email)
    yield created
    for uid, _ in created.values():
        admin.delete(f"{API}/users/{uid}")


# ---- login / cookies ----
def test_login_sets_httponly_cookies():
    s, r = login(**ADMIN)
    assert r.status_code == 200
    assert r.json()["role"] == "admin" and r.json()["email"] == ADMIN["email"]
    sc = r.headers.get("set-cookie", "")
    assert "access_token=" in sc and "refresh_token=" in sc
    assert sc.lower().count("httponly") >= 2 and "secure" in sc.lower()  # ingress rewrites SameSite to None
    me = s.get(f"{API}/auth/me")
    assert me.status_code == 200 and me.json()["email"] == ADMIN["email"]
    assert "password_hash" not in me.json()


def test_login_wrong_password_401():
    _, r = login(ADMIN["email"], "wrong-password-x")
    assert r.status_code == 401
    # cleanup the attempt from admin counter by successful login
    login(**ADMIN)


def test_cors_explicit_origin():
    r = requests.options(f"{API}/auth/login", headers={"Origin": BASE_URL, "Access-Control-Request-Method": "POST"})
    assert r.headers.get("access-control-allow-origin") == BASE_URL
    assert r.headers.get("access-control-allow-credentials") == "true"
    r2 = requests.options(f"{API}/auth/login", headers={"Origin": "https://evil.com", "Access-Control-Request-Method": "POST"})
    assert r2.headers.get("access-control-allow-origin") != "https://evil.com"


# ---- unauthenticated access ----
@pytest.mark.parametrize("method,path", [
    ("get", "/health"), ("get", "/config"), ("get", f"/device/{DEV}/state"),
    ("post", f"/device/{DEV}/command"), ("get", "/events"), ("get", "/thresholds"),
    ("put", "/thresholds/0"), ("get", "/history"), ("get", "/history/csv?chamber=0"),
    ("get", "/usage/daily"), ("put", "/broker"), ("post", "/simulator/toggle?enable=false"),
    ("get", "/users"), ("post", "/users"), ("delete", "/users/abc"), ("get", "/auth/me"), ("put", "/auth/password"),
])
def test_unauth_401(method, path):
    body = {"type": "chamber_power", "chamber": 0, "value": False} if "command" in path else {}
    r = getattr(requests, method)(f"{API}{path}", json=body, timeout=10)
    assert r.status_code == 401, (path, r.status_code, r.text)


def test_public_root_ok():
    assert requests.get(f"{API}/").status_code == 200


def test_ws_without_cookie_rejected():
    async def go():
        url = BASE_URL.replace("https", "wss") + "/api/ws"
        try:
            async with websockets.connect(url, open_timeout=10) as ws:
                await asyncio.wait_for(ws.recv(), 5)
                return "accepted"
        except Exception as e:
            return f"rejected:{type(e).__name__}"
    res = asyncio.run(go())
    assert res.startswith("rejected"), res


def test_ws_with_cookie_receives_state(admin):
    async def go():
        url = BASE_URL.replace("https", "wss") + "/api/ws"
        cookie = f"access_token={admin.cookies.get('access_token')}"
        async with websockets.connect(url, additional_headers={"Cookie": cookie, "Origin": BASE_URL}, open_timeout=10) as ws:
            for _ in range(10):
                m = json.loads(await asyncio.wait_for(ws.recv(), 10))
                if m["type"] == "state":
                    return m
    m = asyncio.run(go())
    assert m and len(m["payload"]["chambers"]) == 3


# ---- roles ----
def test_viewer_permissions(users):
    s, r = login(users["viewer"][1], "TestPass123!")
    assert r.status_code == 200 and r.json()["role"] == "viewer"
    for p in ("/health", "/config", f"/device/{DEV}/state", "/events", "/thresholds", "/history", "/usage/daily", "/history/csv?chamber=0&hours=1"):
        assert s.get(f"{API}{p}").status_code == 200, p
    assert s.post(f"{API}/device/{DEV}/command", json={"type": "chamber_power", "chamber": 2, "value": True}).status_code == 403
    assert s.put(f"{API}/thresholds/0", json={"temp_max": 26, "co2_max": 3000}).status_code == 403
    assert s.put(f"{API}/broker", json=ORIG_BROKER).status_code == 403
    assert s.post(f"{API}/simulator/toggle?enable=true").status_code == 403
    assert s.get(f"{API}/users").status_code == 403
    assert s.post(f"{API}/users", json={"email": "x@y.pl", "password": "12345678", "role": "admin"}).status_code == 403


def test_operator_permissions(users):
    s, r = login(users["operator"][1], "TestPass123!")
    assert r.status_code == 200 and r.json()["role"] == "operator"
    assert s.post(f"{API}/device/{DEV}/command", json={"type": "set_mode", "chamber": 0, "value": "auto"}).status_code == 200
    assert s.put(f"{API}/thresholds/0", json={"temp_max": 26.0, "co2_max": 3000.0}).status_code == 200
    assert s.put(f"{API}/broker", json=ORIG_BROKER).status_code == 403
    assert s.post(f"{API}/simulator/toggle?enable=true").status_code == 403
    assert s.get(f"{API}/users").status_code == 403


def test_users_list_and_duplicate(admin, users):
    lst = admin.get(f"{API}/users").json()["users"]
    emails = [u["email"] for u in lst]
    assert users["viewer"][1] in emails and all("password_hash" not in u for u in lst)
    r = admin.post(f"{API}/users", json={"email": users["viewer"][1], "password": "TestPass123!", "role": "viewer"})
    assert r.status_code == 409
    me = admin.get(f"{API}/auth/me").json()
    assert admin.delete(f"{API}/users/{me['id']}").status_code == 400


def test_deleted_user_token_invalid(admin):
    email = f"test_del_{uuid.uuid4().hex[:6]}@example.com"
    uid = admin.post(f"{API}/users", json={"email": email, "password": "TestPass123!", "role": "viewer"}).json()["id"]
    s, _ = login(email, "TestPass123!")
    assert s.get(f"{API}/health").status_code == 200
    assert admin.delete(f"{API}/users/{uid}").status_code == 200
    assert s.get(f"{API}/health").status_code == 401
    assert admin.delete(f"{API}/users/{uid}").status_code == 404


# ---- brute force ----
def test_brute_force_lockout(admin):
    email = f"test_bf_{uuid.uuid4().hex[:6]}@example.com"
    uid = admin.post(f"{API}/users", json={"email": email, "password": "TestPass123!", "role": "viewer"}).json()["id"]
    try:
        codes = [login(email, "bad-pass-1")[1].status_code for _ in range(5)]
        assert codes == [401] * 5
        assert login(email, "bad-pass-1")[1].status_code == 429
        assert login(email, "TestPass123!")[1].status_code == 429  # locked even with correct pw
    finally:
        admin.delete(f"{API}/users/{uid}")


def test_brute_force_xff_bypass(admin):
    """Lockout key uses first X-Forwarded-For entry - check if client-supplied XFF bypasses it."""
    email = f"test_xff_{uuid.uuid4().hex[:6]}@example.com"
    uid = admin.post(f"{API}/users", json={"email": email, "password": "TestPass123!", "role": "viewer"}).json()["id"]
    try:
        for _ in range(5):
            login(email, "bad")
        r = requests.post(f"{API}/auth/login", json={"email": email, "password": "bad"},
                          headers={"X-Forwarded-For": "1.2.3.4"}, timeout=10)
        assert r.status_code == 429, f"lockout bypassed via X-Forwarded-For spoof: {r.status_code}"
    finally:
        admin.delete(f"{API}/users/{uid}")


# ---- password change / logout / refresh ----
def test_password_change_flow(admin):
    email = f"test_pw_{uuid.uuid4().hex[:6]}@example.com"
    uid = admin.post(f"{API}/users", json={"email": email, "password": "TestPass123!", "role": "viewer"}).json()["id"]
    try:
        s, _ = login(email, "TestPass123!")
        assert s.put(f"{API}/auth/password", json={"current_password": "nope", "new_password": "NewPass123!"}).status_code == 400
        assert s.put(f"{API}/auth/password", json={"current_password": "TestPass123!", "new_password": "short"}).status_code == 422
        assert s.put(f"{API}/auth/password", json={"current_password": "TestPass123!", "new_password": "NewPass123!"}).status_code == 200
        assert login(email, "TestPass123!")[1].status_code == 401
        assert login(email, "NewPass123!")[1].status_code == 200
    finally:
        admin.delete(f"{API}/users/{uid}")


def test_logout_then_401():
    s, _ = login(**ADMIN)
    r = s.post(f"{API}/auth/logout")
    assert r.status_code == 200
    assert "access_token" not in s.cookies
    assert s.get(f"{API}/health").status_code == 401


def test_refresh_with_only_refresh_cookie():
    s, _ = login(**ADMIN)
    rt = s.cookies.get("refresh_token")
    s2 = requests.Session()
    s2.cookies.set("refresh_token", rt)
    assert s2.get(f"{API}/health").status_code == 401
    r = s2.post(f"{API}/auth/refresh")
    assert r.status_code == 200 and r.json()["role"] == "admin"
    assert s2.get(f"{API}/health").status_code == 200
    # access token must not work as refresh and vice versa
    s3 = requests.Session()
    s3.cookies.set("access_token", rt)
    assert s3.get(f"{API}/health").status_code == 401


def test_bearer_header_accepted(admin):
    tok = admin.cookies.get("access_token")
    assert requests.get(f"{API}/health", headers={"Authorization": f"Bearer {tok}"}).status_code == 200


# ---- origin guard ----
def test_origin_guard(admin):
    r = admin.post(f"{API}/device/{DEV}/command", json={"type": "set_mode", "chamber": 0, "value": "auto"},
                   headers={"Origin": "https://evil.com"})
    assert r.status_code == 403
    r = requests.post(f"{API}/auth/login", json=ADMIN, headers={"Origin": "https://evil.com"})
    assert r.status_code == 403
    r = admin.post(f"{API}/device/{DEV}/command", json={"type": "set_mode", "chamber": 0, "value": "auto"},
                   headers={"Origin": BASE_URL})
    assert r.status_code == 200


# ---- broker SSRF + encrypted password ----
@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "10.0.0.1", "mongodb", "169.254.169.254", "192.168.1.1", "0.0.0.0"])
def test_broker_private_host_422(admin, host):
    r = admin.put(f"{API}/broker", json={**ORIG_BROKER, "host": host}, timeout=20)
    assert r.status_code == 422, (host, r.text)


def test_broker_ok_and_reconnect(admin):
    r = admin.put(f"{API}/broker", json={**ORIG_BROKER, "password": ""}, timeout=30)
    assert r.status_code == 200, r.text
    assert r.json()["broker_host"] == "broker.hivemq.com" and r.json()["has_password"] is False
    ok = False
    for _ in range(40):
        time.sleep(1)
        if admin.get(f"{API}/health").json().get("device_online"):
            ok = True
            break
    assert ok


# ---- MQTT sanitization ----
def test_mqtt_malicious_payload_ignored(admin):
    topic = "emgt-fatek-7f3a9c/chlodnia-01/state"
    bad = {"device_id": DEV, "chambers": [{"id": 0, "name": "=HYPERLINK(\"http://evil\")", "temp": "=HYPERLINK(\"http://evil\",\"x\")",
                                           "setpoint": 20, "humidity": 50, "co2": 900, "on": True,
                                           "curtain_left": 1, "curtain_right": 1, "chimney": 1}] * 3, "plant": {}}
    c = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id=f"test-{uuid.uuid4().hex[:6]}")
    c.connect("broker.hivemq.com", 1883)
    c.loop_start()
    for _ in range(5):
        c.publish(topic, json.dumps(bad), qos=1)
        c.publish(topic, "not json", qos=1)
        time.sleep(0.4)
    c.loop_stop()
    c.disconnect()
    for _ in range(6):
        st = admin.get(f"{API}/device/{DEV}/state").json()["state"]
        for ch in st["chambers"]:
            assert isinstance(ch["temp"], float) and ch["name"].startswith("Komora")
        time.sleep(0.5)
    r = admin.get(f"{API}/history/csv?chamber=0&hours=1")
    assert r.status_code == 200 and "HYPERLINK" not in r.text


def test_mqtt_partial_payload(admin):
    """Report-only: a numeric but partial payload (1 chamber) from broker is accepted?"""
    topic = "emgt-fatek-7f3a9c/chlodnia-01/state"
    part = {"chambers": [{"id": 0, "temp": 99.0, "setpoint": 20, "humidity": 50, "co2": 900, "on": True,
                          "curtain_left": 1, "curtain_right": 1, "chimney": 1}]}
    seen = set()
    c = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id=f"test-{uuid.uuid4().hex[:6]}")
    c.connect("broker.hivemq.com", 1883)
    c.loop_start()
    for _ in range(15):
        c.publish(topic, json.dumps(part), qos=1)
        time.sleep(0.2)
        seen.add(len(admin.get(f"{API}/device/{DEV}/state").json()["state"]["chambers"]))
    c.loop_stop()
    c.disconnect()
    print("chamber counts seen:", seen)
    assert seen == {3}, f"partial payload accepted, chamber counts seen {seen}"

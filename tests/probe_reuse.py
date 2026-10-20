# Probe: data leakage when a device_id is deleted and re-created under another client
import os, requests, uuid
API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
s = requests.Session()
r = s.post(f"{API}/auth/login", json={"email": "admin@chlewnia.pl", "password": "Wentylacja!2026"})
print("login", r.status_code, "set-cookie:", r.headers.get("set-cookie", "")[:200])
tag = uuid.uuid4().hex[:5]
a = s.post(f"{API}/clients", json={"name": f"TEST_A_{tag}"}).json()["id"]
b = s.post(f"{API}/clients", json={"name": f"TEST_B_{tag}"}).json()["id"]
did = f"test-reuse-{tag}"
s.post(f"{API}/devices", json={"client_id": a, "name": "devA", "device_id": did, "chambers": 2})
s.put(f"{API}/devices/{did}/thresholds/0", json={"temp_max": 11, "co2_max": 1111})
s.delete(f"{API}/devices/{did}")
s.post(f"{API}/devices", json={"client_id": b, "name": "devB", "device_id": did, "chambers": 2})
em = f"test_{tag}_b@b.pl"
uid = s.post(f"{API}/users", json={"email": em, "password": "Haslo1234!", "role": "viewer", "client_id": b}).json()["id"]
u = requests.Session(); u.post(f"{API}/auth/login", json={"email": em, "password": "Haslo1234!"})
ev = u.get(f"{API}/events?device_id={did}").json()["events"]
leak = [e["message"] for e in ev if e.get("client_id") == a]
print("B user sees client A events:", leak)
print("thresholds B:", u.get(f"{API}/devices/{did}/thresholds").json())
s.delete(f"{API}/devices/{did}"); s.delete(f"{API}/users/{uid}")
print("del A", s.delete(f"{API}/clients/{a}").status_code, "del B", s.delete(f"{API}/clients/{b}").status_code)
# lockout
for i in range(6):
    r = requests.post(f"{API}/auth/login", json={"email": f"test_lock_{tag}@x.pl", "password": "bad"})
print("6th bad login:", r.status_code)

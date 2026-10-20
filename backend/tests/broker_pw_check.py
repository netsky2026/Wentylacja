# one-off: verify broker password is stored encrypted (not plaintext), then restore
import os, time, requests, subprocess
API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
s = requests.Session()
s.post(f"{API}/auth/login", json={"email": "admin@chlewnia.pl", "password": "Wentylacja!2026"})
B = {"host": "broker.hivemq.com", "port": 1883, "username": "tester", "tls": False, "prefix": "emgt-fatek-7f3a9c", "device_id": "chlodnia-01"}
r = s.put(f"{API}/broker", json={**B, "password": "PlainSecret123"}, timeout=30)
print("put", r.status_code, r.json().get("has_password"), "PlainSecret123" in r.text)
print(subprocess.run(["mongosh", "--quiet", os.environ["MURL"], "--eval",
                      "printjson(db.getSiblingDB('%s').broker_config.findOne())" % os.environ["DBN"]], capture_output=True, text=True).stdout)
r = s.put(f"{API}/broker", json={**B, "username": "", "password": ""}, timeout=30)
print("restore", r.status_code, r.json().get("has_password"), r.json().get("username"))
for _ in range(30):
    time.sleep(1)
    if s.get(f"{API}/health").json().get("device_online"):
        print("online again"); break

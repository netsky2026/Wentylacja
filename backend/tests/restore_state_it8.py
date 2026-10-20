# Restore baseline state after iteration 8 tests
import os, time, requests
from pymongo import MongoClient
API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
env = dict(l.strip().split("=", 1) for l in open("/app/backend/.env") if "=" in l)
db = MongoClient(env["MONGO_URL"].strip('"'))[env["DB_NAME"].strip('"')]
s = requests.Session()
assert s.post(f"{API}/auth/login", json={"email": "admin@chlewnia.pl", "password": "Wentylacja!2026"}).status_code == 200
s.put(f"{API}/alarm-settings", json={"enabled": True, "recipients": []})
for ch, t in ((0, 26), (1, 28), (2, 30)):
    s.put(f"{API}/thresholds/{ch}", json={"temp_max": t, "co2_max": 3000})
s.post(f"{API}/simulator/toggle?enable=true")
D = "chlodnia-01"
for ch, sp in ((0, 20), (1, 22), (2, 24)):
    s.post(f"{API}/device/{D}/command", json={"type": "chamber_power", "chamber": ch, "value": True})
    time.sleep(0.5)
    s.post(f"{API}/device/{D}/command", json={"type": "set_mode", "chamber": ch, "value": "auto"})
    s.post(f"{API}/device/{D}/command", json={"type": "set_setpoint", "chamber": ch, "value": sp})
time.sleep(1)
s.post(f"{API}/device/{D}/command", json={"type": "chamber_power", "chamber": 2, "value": False})
for u in db.users.find({"email": {"$regex": "^test_"}}):
    s.delete(f"{API}/users/{u['_id']}")
time.sleep(6)
db.alarm_notifications.delete_many({})
db.login_attempts.delete_many({})
st = s.get(f"{API}/device/{D}/state").json()["state"]
print([(c["id"], c["on"], c["mode"], c["setpoint"]) for c in st["chambers"]])
print(s.get(f"{API}/thresholds").json(), s.get(f"{API}/alarm-settings").json())
print([u["email"] for u in db.users.find()], db.alarm_notifications.count_documents({}), s.get(f"{API}/health").json())

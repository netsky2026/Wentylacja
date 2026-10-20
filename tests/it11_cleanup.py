# Inspect + clean leftover test data (keeps Marco Polo / Ferma Kowalski)
from pymongo import MongoClient
env = dict(l.strip().split("=", 1) for l in open("/app/backend/.env") if "=" in l)
db = MongoClient(env["MONGO_URL"].strip('"'))[env["DB_NAME"].strip('"')]
print("clients", [c["name"] for c in db.clients.find()])
print("devices", [(d["device_id"], d["chambers"], d.get("simulated")) for d in db.devices.find()])
print("users", [(u["email"], u["role"]) for u in db.users.find()])
print("alarm_settings", list(db.alarm_settings.find({}, {"recipients": 1})))
keep = [d["device_id"] for d in db.devices.find()]
for c in ("plc_events", "plc_history", "plc_plant_history", "device_thresholds"):
    r = db[c].delete_many({"device_id": {"$regex": "^test-"}})
    print("orphan", c, r.deleted_count)
db.alarm_settings.update_many({}, {"$set": {"recipients": []}})
print("login_attempts", db.login_attempts.delete_many({}).deleted_count)
print("alarm_notifications", db.alarm_notifications.delete_many({}).deleted_count)
print("thresholds", list(db.device_thresholds.find({}, {"_id": 0})))

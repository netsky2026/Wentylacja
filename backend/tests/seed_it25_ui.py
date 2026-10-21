# Seed/cleanup for iteration 25 UI test: kowalski-a chamber 0 ended cycles + active cycle + synthetic meter days. Usage: python seed_it25_ui.py seed|clean
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pymongo import MongoClient

db = MongoClient("mongodb://localhost:27017")["test_database"]
KOW = "kowalski-a"
NOW = datetime.now(ZoneInfo("Europe/Warsaw")).date()
FIRST = NOW.replace(day=1)
PF = (FIRST - timedelta(days=1)).replace(day=1)
TAG = "it25ui"

if sys.argv[1] == "seed":
    for i in range(20):
        d = (PF + timedelta(days=i)).isoformat()
        if not db.meter_daily.find_one({"_id": f"{KOW}|{d}"}):
            db.meter_daily.insert_one({"_id": f"{KOW}|{d}", "device_id": KOW, "day": d, "kwh": 10.0, "test_tag": TAG,
                                       "water": {str(c): 1000.0 for c in range(6)}})
    for i in range(5):
        d = (FIRST + timedelta(days=i)).isoformat()
        if d < NOW.isoformat() and not db.meter_daily.find_one({"_id": f"{KOW}|{d}"}):
            db.meter_daily.insert_one({"_id": f"{KOW}|{d}", "device_id": KOW, "day": d, "kwh": 10.0, "test_tag": TAG,
                                       "water": {str(c): 1000.0 for c in range(6)}})
    db.cycles.delete_many({"device_id": KOW, "chamber": 0})
    db.cycles.insert_many([
        {"device_id": KOW, "chamber": 0, "start": PF.isoformat(), "end": (PF + timedelta(days=9)).isoformat(), "animals": 100, "started_by": f"{TAG}@x"},
        {"device_id": KOW, "chamber": 0, "start": (PF + timedelta(days=10)).isoformat(), "end": (PF + timedelta(days=19)).isoformat(), "animals": 50, "started_by": f"{TAG}@x"},
        {"device_id": KOW, "chamber": 0, "start": FIRST.isoformat(), "end": None, "active": True, "animals": 40, "started_by": f"{TAG}@x"},
    ])
    print("seeded")
else:
    print(db.meter_daily.delete_many({"test_tag": TAG}).deleted_count, db.cycles.delete_many({"device_id": KOW, "started_by": f"{TAG}@x"}).deleted_count)

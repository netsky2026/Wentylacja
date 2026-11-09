# Helper (iteration 36 UI test): creates TEST device, publishes flag-variant state every 2 s for DURATION s, then deletes device
import json, os, sys, time, uuid
import paho.mqtt.client as mqtt
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"
DEV = sys.argv[1]
DURATION = int(sys.argv[2]) if len(sys.argv) > 2 else 240
s = requests.Session()
s.headers.update({"Origin": BASE})
s.post(f"{API}/auth/login", json={"email": "admin@chlewnia.pl", "password": "Wentylacja!2026"}).raise_for_status()
r = s.post(f"{API}/devices", json={"client_id": "6ad7dcc3261e5ba3c23315b7", "name": "TEST_FlagUI", "device_id": DEV, "chambers": 3, "simulated": False})
print("create", r.status_code, flush=True)
topic = s.get(f"{API}/devices/{DEV}/mqtt-debug").json()["state_topic"]
base = dict(temp=20.5, setpoint=21.0, humidity=65, co2=1100, curtain_left=40, curtain_right=40, chimney=30)
msg = json.dumps({"model": "FBs-UI", "chambers": [
    {"id": 0, "on": 0, "heating": 0, "mode": "0", **base},
    {"id": 1, "on": "1", "heating": 1, "mode": "1", **base},
    {"id": 2, "on": True, "heating": "0", "mode": "auto", **base}], "plant": {"power_kw": 3.2}})
mc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"it36ui-{uuid.uuid4().hex[:6]}")
mc.connect("broker.hivemq.com", 1883, 30)
mc.loop_start()
try:
    end = time.time() + DURATION
    while time.time() < end and not os.path.exists(f"/tmp/stop_{DEV}"):
        mc.publish(topic, msg, qos=1)
        time.sleep(2)
finally:
    mc.loop_stop()
    print("delete", s.delete(f"{API}/devices/{DEV}").status_code, flush=True)

# Helper (iteration 33 UI): publish native Fatek msgs to fatektest: phase1 DataItem0 for N1 s, then full message every 2s for N2 s
import json, sys, time, uuid
import paho.mqtt.client as mqtt
topic = sys.argv[1]
n1, n2 = int(sys.argv[2]), int(sys.argv[3])
FULL = {"temp_x10": [194, 214, 229], "setpoint_x10": [200, 220, 240], "humidity": [70, 71, 72], "co2": [1200, 1300, 1400],
        "curtain_left": [40, 40, 40], "curtain_right": [40, 40, 40], "chimney": [30, 30, 30], "mode": [0, 0, 1],
        "water_total_l": [100, 200, 300], "power_kwh_x10": [1672]}
mc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"it33u-{uuid.uuid4().hex[:6]}")
mc.connect("broker.hivemq.com", 1883, 30)
mc.loop_start()
end = time.time() + n1
while time.time() < end:
    mc.publish(topic, json.dumps({"d": {"DataItem0": [4]}, "error": [], "ts": "2026-01-09T09:50:06.858"}), qos=1)
    time.sleep(1)
end = time.time() + n2
while time.time() < end:
    mc.publish(topic, json.dumps({"d": FULL, "error": [], "ts": "2026-01-09T09:50:06.858"}), qos=1)
    time.sleep(2)
mc.loop_stop()

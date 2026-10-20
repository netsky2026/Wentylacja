# helper: sniff state & command topic for N seconds to detect foreign publishers
import json, time, sys, uuid
import paho.mqtt.client as mqtt
msgs = []
def on_msg(c, u, m):
    try:
        p = json.loads(m.payload)
    except Exception:
        p = None
    msgs.append((time.time(), m.topic, p))
c = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id=f"sniff-{uuid.uuid4().hex[:6]}")
c.on_message = on_msg
c.on_connect = lambda c, u, f, rc, pr: c.subscribe("emgt-fatek-7f3a9c/#")
c.connect("broker.hivemq.com", 1883)
c.loop_start()
time.sleep(int(sys.argv[1]) if len(sys.argv) > 1 else 8)
c.loop_stop()
for t, top, p in msgs:
    if p and "chambers" in p:
        print(round(t % 100, 2), top, p.get("ts"), [(ch["curtain_left"], ch["mode"], ch["setpoint"]) for ch in p["chambers"]], p["plant"].get("power_kwh"))
    else:
        print(round(t % 100, 2), top, str(p)[:120])

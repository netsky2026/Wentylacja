# Helper: publish an invalid (non-JSON) state message to kowalski-a every 1s for N seconds (UI rejection test)
import sys, time, uuid
import paho.mqtt.client as mqtt
topic = "emgt-fatek-7f3a9c/kowalski-a/state"
mc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"it31p-{uuid.uuid4().hex[:6]}")
mc.connect("broker.hivemq.com", 1883, 30)
mc.loop_start()
end = time.time() + int(sys.argv[1] if len(sys.argv) > 1 else 60)
while time.time() < end:
    mc.publish(topic, b'{"chambers": "bad"', qos=1)
    time.sleep(1)
mc.loop_stop()

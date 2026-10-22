import { useEffect, useState } from "react";
import axios from "axios";
import { X, CheckCircle2, XCircle } from "lucide-react";
import { API } from "@/api";

const ago = (ts) => (ts ? Math.max(0, Math.round((Date.now() - new Date(ts).getTime()) / 1000)) : null);
const pretty = (s) => { try { return JSON.stringify(JSON.parse(s), null, 2); } catch (e) { return s; } };
const Box = ({ children, testid }) => (
  <pre data-testid={testid} style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, padding: 8,
    fontSize: 10, maxHeight: 220, overflow: "auto", whiteSpace: "pre-wrap", wordBreak: "break-all", margin: "4px 0 0" }}>{children}</pre>
);

export const MqttDebugPanel = ({ t, deviceId, onClose }) => {
  const [d, setD] = useState(null);
  useEffect(() => {
    const load = () => axios.get(`${API}/devices/${deviceId}/mqtt-debug`).then(({ data }) => setD(data)).catch(() => {});
    load();
    const i = setInterval(load, 2000);
    return () => clearInterval(i);
  }, [deviceId]);
  const m = d?.last_message, c = d?.last_command;
  return (
    <div className="reg-cell fade-in" style={{ padding: 10, fontSize: 11, marginTop: 6 }} data-testid={`mqtt-debug-${deviceId}`}>
      <div className="flex items-center justify-between" style={{ marginBottom: 6 }}>
        <b style={{ fontSize: 12 }}>{t.mqttTitle} · {deviceId}</b>
        <button className="sp-btn" onClick={onClose} data-testid="mqtt-debug-close" aria-label="close"><X size={13} /></button>
      </div>
      {!d ? <div style={{ color: "var(--muted)" }}>…</div> : (<>
        <div data-testid="mqtt-debug-status">{t.mqttBroker}: <b style={{ color: d.broker_connected ? "var(--green)" : "var(--accent)" }}>{d.broker_connected ? t.mqttYes : t.mqttNo}</b>
          {" · "}{t.mqttDevice}: <b style={{ color: d.online ? "var(--green)" : "var(--accent)" }}>{d.online ? "online" : "offline"}</b></div>
        <div style={{ color: "var(--muted)", marginTop: 2, wordBreak: "break-all" }}>state: {d.state_topic}<br />command: {d.command_topic}</div>
        <div style={{ marginTop: 8, fontWeight: 700 }}>{t.mqttLastMsg}</div>
        {!m ? <div style={{ color: "var(--muted)" }} data-testid="mqtt-debug-none">{t.mqttNone}</div> : (<>
          <div className="flex items-center gap-1" data-testid="mqtt-debug-result" style={{ color: m.ok ? "var(--green)" : "var(--accent)" }}>
            {m.ok ? <CheckCircle2 size={12} /> : <XCircle size={12} />} {m.ok ? t.mqttAccepted : `${t.mqttRejected}: ${m.error}`}
          </div>
          <div style={{ color: "var(--muted)" }}>{ago(m.ts)} s {t.mqttAgo} · {m.size} B</div>
          <Box testid="mqtt-debug-payload">{pretty(m.payload)}</Box>
        </>)}
        <div style={{ marginTop: 8, fontWeight: 700 }}>{t.mqttLastCmd}</div>
        {!c ? <div style={{ color: "var(--muted)" }}>{t.mqttNoCmd}</div> : (<>
          <div style={{ color: "var(--muted)" }}>{ago(c.ts)} s {t.mqttAgo} · {c.ok ? t.mqttSent : t.mqttSendFail}</div>
          <Box testid="mqtt-debug-command">{pretty(c.payload)}</Box>
        </>)}
      </>)}
    </div>
  );
};

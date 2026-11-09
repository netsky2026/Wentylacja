import { useEffect, useState } from "react";
import axios from "axios";
import { Send, RotateCcw } from "lucide-react";
import { toast } from "sonner";
import { API } from "@/api";

const inp = { width: "100%", background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, padding: 6,
  fontSize: 11, fontFamily: "monospace", color: "inherit" };

const jsonError = (s) => { try { JSON.parse(s); return null; } catch (e) { return e.message; } };

export const MqttSendBox = ({ t, deviceId, defaultTopic }) => {
  const [topic, setTopic] = useState(defaultTopic);
  const [payload, setPayload] = useState('{"d": {"setpoint_x10": [220]}}');
  const [hist, setHist] = useState([]);
  const [busy, setBusy] = useState(false);
  const loadHist = () => axios.get(`${API}/devices/${deviceId}/mqtt-sent`).then(({ data }) => setHist(data)).catch(() => {});
  useEffect(() => { loadHist(); }, [deviceId]); // eslint-disable-line react-hooks/exhaustive-deps
  const err = jsonError(payload);
  const send = async (tp, pl) => {
    if (jsonError(pl)) return;
    if (!window.confirm(t.rawConfirm.replace("{topic}", tp) + "\n\n" + pl)) return;
    setBusy(true);
    try { await axios.post(`${API}/devices/${deviceId}/mqtt-send`, { topic: tp, payload: pl }); toast.success(t.rawSent); }
    catch (e) { toast.error(e.response?.data?.detail?.toString() || t.saveFailed); }
    setBusy(false);
    loadHist();
  };
  return (
    <div data-testid="mqtt-raw-box" style={{ marginTop: 10, borderTop: "1px solid var(--border)", paddingTop: 8 }}>
      <div style={{ fontWeight: 700 }}>{t.rawTitle}</div>
      <div style={{ color: "var(--muted)", fontSize: 10, margin: "2px 0 4px" }}>{t.rawHint}</div>
      <input style={inp} value={topic} onChange={(e) => setTopic(e.target.value)} data-testid="mqtt-raw-topic" />
      <textarea style={{ ...inp, marginTop: 4, minHeight: 80 }} value={payload} onChange={(e) => setPayload(e.target.value)} data-testid="mqtt-raw-payload" />
      {err && <div style={{ color: "var(--accent)", fontSize: 10 }} data-testid="mqtt-raw-error">{t.rawBadJson}: {err}</div>}
      <button className="action-btn" disabled={!!err || busy || !topic.trim()} onClick={() => send(topic.trim(), payload)} data-testid="mqtt-raw-send"
        style={{ marginTop: 6, padding: "7px 12px", fontSize: 12, color: "var(--primary)", borderColor: "var(--primary)", opacity: err || busy ? 0.5 : 1 }}>
        <Send size={12} /> {t.rawSend}</button>
      <div style={{ marginTop: 8, fontWeight: 700 }}>{t.rawHistory}</div>
      {!hist.length ? <div style={{ color: "var(--muted)" }} data-testid="mqtt-raw-history-empty">{t.mqttNoCmd}</div> : (
        <div data-testid="mqtt-raw-history" style={{ maxHeight: 220, overflow: "auto" }}>
          {hist.map((h, i) => (
            <div key={h.ts + i} className="flex items-start gap-2" style={{ borderBottom: "1px solid var(--border)", padding: "4px 0" }} data-testid={`mqtt-raw-history-item-${i}`}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ color: h.ok ? "var(--muted)" : "var(--accent)", fontSize: 10 }}>{new Date(h.ts).toLocaleString("pl-PL")} · {h.topic}</div>
                <code style={{ fontSize: 10, wordBreak: "break-all" }}>{h.payload}</code>
              </div>
              <button className="sp-btn" title={t.rawResend} onClick={() => { setTopic(h.topic); setPayload(h.payload); send(h.topic, h.payload); }}
                data-testid={`mqtt-raw-resend-${i}`}><RotateCcw size={12} /></button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

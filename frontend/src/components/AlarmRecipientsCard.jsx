import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { BellRing, Trash2, Plus, Send, AlertTriangle } from "lucide-react";
import { API } from "@/api";

const OfflineMin = ({ t, value, onSave }) => {
  const [v, setV] = useState(String(value ?? 5));
  return (
    <div className="flex items-center gap-2" style={{ fontSize: 12, marginBottom: 10 }} data-testid="offline-min-row">
      <span style={{ flex: 1 }}>{t.offlineAlarm}</span>
      <input className="num-input" type="number" min="0" max="1440" value={v} onChange={(e) => setV(e.target.value)}
        data-testid="offline-min-input" style={{ width: 70, fontSize: 13, padding: "6px 8px" }} />
      <span style={{ color: "var(--muted)" }}>min</span>
      <button className="action-btn" data-testid="offline-min-save" style={{ padding: "6px 10px", fontSize: 12 }}
        onClick={() => { const m = parseInt(v, 10); if (Number.isNaN(m) || m < 0 || m > 1440) { toast.error(t.recipientInvalid); return; } onSave(m); }}>{t.save}</button>
    </div>
  );
};

export const AlarmRecipientsCard = ({ t, clientId, clientName }) => {
  const q = clientId ? `?client_id=${clientId}` : "";
  const [cfg, setCfg] = useState(null);
  const [type, setType] = useState("email");
  const [value, setValue] = useState("");
  const load = useCallback(() => axios.get(`${API}/alarm-settings${q}`).then(({ data }) => setCfg(data)).catch(() => {}), [q]);
  useEffect(() => { load(); }, [load]);
  if (!cfg) return null;

  const save = async (next) => {
    try {
      const { data } = await axios.put(`${API}/alarm-settings${q}`, { enabled: next.enabled, recipients: next.recipients, offline_min: next.offline_min });
      setCfg(data);
      return true;
    } catch (e) {
      toast.error(e.response?.status === 422 ? t.recipientInvalid : t.saveFailed);
      return false;
    }
  };
  const add = async () => {
    if (!value.trim()) return;
    if (await save({ ...cfg, recipients: [...cfg.recipients, { type, value: value.trim() }] })) {
      setValue("");
      toast.success(t.saved);
    }
  };
  const remove = (i) => save({ ...cfg, recipients: cfg.recipients.filter((_, j) => j !== i) });
  const test = async () => {
    try { const { data } = await axios.post(`${API}/alarm-settings/test${q}`); setCfg(data); toast.success(t.testSent); }
    catch (e) { toast.error(t.saveFailed); }
  };

  return (
    <div className="panel panel-pad" data-testid="alarm-recipients-card">
      <div className="flex items-center justify-between" style={{ marginBottom: 8 }}>
        <span className="flex items-center gap-2 font-head" style={{ fontSize: 15, fontWeight: 600 }}><BellRing size={16} /> {t.alarmRecipients}{clientName ? ` · ${clientName}` : ""}</span>
        <label className="flex items-center gap-2" style={{ fontSize: 12 }}>
          <input type="checkbox" checked={cfg.enabled} onChange={(e) => save({ ...cfg, enabled: e.target.checked })} data-testid="alarm-enabled" />
          {cfg.enabled ? t.on : t.off}
        </label>
      </div>
      {(!cfg.email_configured || !cfg.sms_configured) && (
        <div className="flex gap-2" data-testid="alarm-mocked-banner" style={{ fontSize: 11, color: "var(--warn-text)", background: "var(--warn-bg)",
          border: "1px solid var(--warn-border)", borderRadius: 8, padding: "8px 10px", marginBottom: 10 }}>
          <AlertTriangle size={14} style={{ flexShrink: 0, marginTop: 1 }} />
          {t.alarmMocked.replace("{c}", [!cfg.email_configured && "E-mail (SMTP)", !cfg.sms_configured && "SMS (SMSAPI)"].filter(Boolean).join(", "))}
        </div>
      )}
      <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 10 }}>{t.alarmRule.replace("{m}", cfg.reminder_min)}</div>
      <OfflineMin t={t} value={cfg.offline_min} onSave={(m) => save({ ...cfg, offline_min: m }).then((ok) => ok && toast.success(t.saved))} />
      <div style={{ display: "flex", flexDirection: "column", gap: 6, marginBottom: 10 }}>
        {cfg.recipients.length === 0 && <div style={{ fontSize: 12, color: "var(--muted)" }}>{t.noRecipients}</div>}
        {cfg.recipients.map((r, i) => (
          <div key={`${r.type}-${r.value}`} className="flex items-center justify-between reg-cell" style={{ padding: "7px 10px" }} data-testid={`recipient-${i}`}>
            <span style={{ fontSize: 12 }}><span style={{ color: "var(--muted)" }}>{r.type === "email" ? "E-mail" : "SMS"} · </span>{r.value}</span>
            <button className="sp-btn" onClick={() => remove(i)} data-testid={`recipient-remove-${i}`} aria-label="remove"><Trash2 size={14} /></button>
          </div>
        ))}
      </div>
      <div className="grid gap-2" style={{ gridTemplateColumns: "88px 1fr 44px" }}>
        <select className="num-input" style={{ fontSize: 13 }} value={type} onChange={(e) => setType(e.target.value)} data-testid="recipient-type">
          <option value="email">E-mail</option>
          <option value="sms">SMS</option>
        </select>
        <input className="num-input" style={{ fontSize: 13 }} value={value} onChange={(e) => setValue(e.target.value)}
          placeholder={type === "email" ? "jan@firma.pl" : "+48 600 000 000"} data-testid="recipient-value"
          onKeyDown={(e) => e.key === "Enter" && add()} />
        <button className="sp-btn" style={{ width: 44, height: "auto" }} onClick={add} data-testid="recipient-add" aria-label="add"><Plus size={16} /></button>
      </div>
      <button className="action-btn" onClick={test} disabled={!cfg.recipients.length || !cfg.enabled} data-testid="alarm-test"
        style={{ width: "100%", padding: 9, marginTop: 10, fontSize: 13 }}><Send size={14} /> {t.sendTest}</button>
      {cfg.recent.length > 0 && (
        <div style={{ marginTop: 12 }} data-testid="alarm-recent">
          <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 6 }}>{t.recentNotifications}</div>
          {cfg.recent.slice(0, 5).map((n, i) => (
            <div key={i} style={{ fontSize: 11, padding: "4px 0", borderBottom: "1px solid var(--border)" }}>
              <span style={{ color: "var(--muted)" }}>{new Date(n.ts).toLocaleString()} · {n.to}</span>
              <span data-testid={`alarm-recent-status-${i}`} style={{ marginLeft: 6, fontWeight: 600, color: n.status === "sent" ? "var(--green)" : n.status === "failed" ? "var(--accent)" : "var(--muted)" }}
                title={n.error || ""}>{t[`notif_${n.status}`] || n.status}</span><br />{n.subject}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

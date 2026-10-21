import { useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Mail } from "lucide-react";
import { API } from "@/api";

export const MonthlyReportCard = ({ t, clientId, clientName }) => {
  const q = clientId ? `?client_id=${clientId}` : "";
  const [cfg, setCfg] = useState(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { axios.get(`${API}/monthly-report${q}`).then(({ data }) => setCfg(data)).catch(() => {}); }, [q]);
  if (!cfg) return null;
  const toggle = async () => {
    try { const { data } = await axios.put(`${API}/monthly-report${q}`, { enabled: !cfg.enabled }); setCfg({ ...cfg, ...data }); toast.success(t.saved); }
    catch (e) { toast.error(t.saveFailed); }
  };
  const sendNow = async () => {
    setBusy(true);
    try {
      const { data } = await axios.post(`${API}/monthly-report/send${q}`);
      if (!data.recipients?.length) toast.error(t.monthlyNoAdmins);
      else if (data.sent) toast.success(`${t.monthlySent}: ${data.sent}/${data.recipients.length}`);
      else toast.error(`${t.monthlyNotSent} (${(data.status || []).join(", ")})`);
    } catch (e) { toast.error(t.saveFailed); }
    setBusy(false);
  };
  return (
    <div className="panel panel-pad" data-testid="monthly-report-card">
      <div className="flex items-center gap-2 font-head" style={{ fontSize: 15, fontWeight: 600, marginBottom: 4 }}>
        <Mail size={16} /> {t.monthlyTitle}{clientName ? ` · ${clientName}` : ""}</div>
      <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 10 }}>{t.monthlyHint}</div>
      <label className="flex items-center gap-2" style={{ fontSize: 13, cursor: "pointer", marginBottom: 8 }}>
        <input type="checkbox" checked={cfg.enabled} onChange={toggle} data-testid="monthly-enabled" style={{ accentColor: "var(--primary)", width: 18, height: 18 }} />
        {t.monthlyEnabled}
      </label>
      <div style={{ fontSize: 12, color: "var(--muted)", marginBottom: 10 }} data-testid="monthly-recipients">
        {t.monthlyTo}: {cfg.recipients.length ? cfg.recipients.join(", ") : t.monthlyNoAdmins}</div>
      <button className="action-btn" onClick={sendNow} disabled={busy} data-testid="monthly-send-now" style={{ width: "100%", padding: 9, fontSize: 13 }}>
        {t.monthlySendNow} ({cfg.period[0].slice(0, 7)})</button>
    </div>
  );
};

import { useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Clock } from "lucide-react";
import { API } from "@/api";

export const AutoReturnCard = ({ t, clientId, clientName, onSaved }) => {
  const q = clientId ? `?client_id=${clientId}` : "";
  const [time, setTime] = useState("00:00");
  const [on, setOn] = useState(true);
  useEffect(() => {
    axios.get(`${API}/auto-return${q}`).then(({ data }) => { setOn(!!data.time); setTime(data.time || "00:00"); }).catch(() => {});
  }, [q]);
  const save = async () => {
    try { await axios.put(`${API}/auto-return${q}`, { time: on ? time : "" }); toast.success(t.saved); onSaved?.(); }
    catch (e) { toast.error(t.saveFailed); }
  };
  return (
    <div className="panel panel-pad" data-testid="auto-return-card">
      <div className="flex items-center gap-2 font-head" style={{ fontSize: 15, fontWeight: 600, marginBottom: 4 }}>
        <Clock size={16} /> {t.autoReturnTitle}{clientName ? ` · ${clientName}` : ""}</div>
      <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 10 }}>{t.autoReturnHint}</div>
      <div className="flex items-center gap-2">
        <label className="flex items-center gap-2" style={{ fontSize: 13, cursor: "pointer", flex: 1 }}>
          <input type="checkbox" checked={on} onChange={(e) => setOn(e.target.checked)} data-testid="auto-return-enabled" style={{ accentColor: "var(--primary)", width: 18, height: 18 }} />
          {t.autoReturnDaily}
        </label>
        <input type="time" className="num-input" value={time} disabled={!on} onChange={(e) => setTime(e.target.value)}
          data-testid="auto-return-time" style={{ width: 140, fontSize: 15, opacity: on ? 1 : 0.5 }} />
      </div>
      <button className="action-btn" onClick={save} data-testid="auto-return-save" style={{ width: "100%", padding: 9, marginTop: 10, fontSize: 13 }}>{t.save}</button>
    </div>
  );
};

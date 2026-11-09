import { useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Divide } from "lucide-react";
import { API } from "@/api";

const FIELDS = ["temp", "setpoint", "humidity", "co2", "curtain_left", "curtain_right", "chimney", "water_lpm", "water_total_l", "power_kw", "power_kwh"];

export const PlcScaleCard = ({ t }) => {
  const [s, setS] = useState(null);
  useEffect(() => { axios.get(`${API}/plc-scale`).then(({ data }) => setS(data)).catch(() => {}); }, []);
  const save = async () => {
    try { const { data } = await axios.put(`${API}/plc-scale`, s); setS(data); toast.success(t.saved); }
    catch (e) { toast.error(t.saveFailed); }
  };
  if (!s) return null;
  return (
    <div className="panel panel-pad" data-testid="plc-scale-card">
      <div className="flex items-center gap-2 font-head" style={{ fontSize: 15, fontWeight: 600, marginBottom: 4 }}>
        <Divide size={16} /> {t.scaleTitle}</div>
      <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 10 }}>{t.scaleHint}</div>
      {FIELDS.map((f) => (
        <div key={f} className="flex items-center justify-between" style={{ fontSize: 13, padding: "4px 0", borderBottom: "1px solid var(--border)" }}>
          <span>{t.scaleNames[f]} <code style={{ fontSize: 10, color: "var(--muted)" }}>{f}</code></span>
          <select value={s[f]} onChange={(e) => setS({ ...s, [f]: Number(e.target.value) })} data-testid={`plc-scale-${f}`}
            className="num-input" style={{ width: 120, fontSize: 12 }}>
            <option value={1}>{t.scaleAsIs}</option>
            <option value={10}>÷10</option>
            <option value={100}>÷100</option>
            <option value={1000}>÷1000</option>
          </select>
        </div>
      ))}
      <button className="action-btn" onClick={save} data-testid="plc-scale-save" style={{ width: "100%", padding: 9, marginTop: 10, fontSize: 13 }}>{t.save}</button>
    </div>
  );
};

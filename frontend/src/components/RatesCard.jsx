import { useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Coins } from "lucide-react";
import { API } from "@/api";

const num = (v) => (v === "" ? null : Number(String(v).replace(",", ".")));

export const RatesCard = ({ t, clientId, clientName }) => {
  const q = clientId ? `?client_id=${clientId}` : "";
  const [kwh, setKwh] = useState("");
  const [m3, setM3] = useState("");
  useEffect(() => {
    axios.get(`${API}/rates${q}`).then(({ data }) => { setKwh(data.kwh ?? ""); setM3(data.m3 ?? ""); }).catch(() => {});
  }, [q]);
  const save = async () => {
    const body = { kwh: num(kwh), m3: num(m3) };
    if ([body.kwh, body.m3].some((v) => v != null && (Number.isNaN(v) || v < 0))) { toast.error(t.ratesInvalid); return; }
    try { await axios.put(`${API}/rates${q}`, body); toast.success(t.saved); }
    catch (e) { toast.error(e.response?.status === 422 ? t.ratesInvalid : t.saveFailed); }
  };
  const field = (label, value, set, unit, testid) => (
    <label style={{ fontSize: 12, color: "var(--muted)", display: "flex", flexDirection: "column", gap: 4 }}>{label}
      <div className="flex items-center gap-2">
        <input className="num-input" inputMode="decimal" placeholder="0,00" value={value} onChange={(e) => set(e.target.value)} data-testid={testid} style={{ fontSize: 15 }} />
        <span style={{ whiteSpace: "nowrap", color: "var(--text)", fontSize: 13 }}>{unit}</span>
      </div>
    </label>
  );
  return (
    <div className="panel panel-pad" data-testid="rates-card">
      <div className="flex items-center gap-2 font-head" style={{ fontSize: 15, fontWeight: 600, marginBottom: 4 }}>
        <Coins size={16} /> {t.ratesTitle}{clientName ? ` · ${clientName}` : ""}</div>
      <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 10 }}>{t.ratesHint}</div>
      <div className="grid gap-3 sm:grid-cols-2">
        {field(t.ratesPower, kwh, setKwh, "zł / kWh", "rates-kwh")}
        {field(t.ratesWater, m3, setM3, "zł / m³", "rates-m3")}
      </div>
      <button className="action-btn" onClick={save} data-testid="rates-save" style={{ width: "100%", padding: 9, marginTop: 10, fontSize: 13 }}>{t.save}</button>
    </div>
  );
};

import { useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { CalendarRange, FileSpreadsheet } from "lucide-react";
import { API, chName } from "@/api";

const today = () => new Date().toLocaleDateString("sv-SE", { timeZone: "Europe/Warsaw" });
const Row = ({ label, value, testid, bold }) => (
  <div className="flex justify-between" style={{ fontSize: 13, padding: "5px 0", borderBottom: "1px solid var(--border)", fontWeight: bold ? 700 : 400 }}>
    <span style={{ color: bold ? "var(--text)" : "var(--muted)" }}>{label}</span><span data-testid={testid}>{value}</span>
  </div>
);

export const UsageRangeCard = ({ t, dev }) => {
  const [from, setFrom] = useState(today().slice(0, 8) + "01");
  const [to, setTo] = useState(today());
  const [res, setRes] = useState(null);
  const q = `start=${from}&end=${to}`;
  const show = async () => {
    try { const { data } = await axios.get(`${API}/devices/${dev.device_id}/usage/range?${q}`); setRes(data); }
    catch (e) { toast.error(t.rangeInvalid); }
  };
  return (
    <div className="panel panel-pad" data-testid="usage-range-card">
      <div className="flex items-center gap-2 font-head" style={{ fontSize: 15, fontWeight: 600, marginBottom: 10 }}><CalendarRange size={16} /> {t.rangeTitle}</div>
      <div className="grid gap-2" style={{ gridTemplateColumns: "1fr 1fr" }}>
        <input type="date" className="num-input" value={from} onChange={(e) => { setFrom(e.target.value); setRes(null); }} data-testid="range-from" style={{ fontSize: 14 }} />
        <input type="date" className="num-input" value={to} onChange={(e) => { setTo(e.target.value); setRes(null); }} data-testid="range-to" style={{ fontSize: 14 }} />
      </div>
      <button className="action-btn" onClick={show} data-testid="range-show"
        style={{ width: "100%", padding: 10, marginTop: 8, fontSize: 13, background: "var(--primary)", borderColor: "var(--primary)", color: "var(--on-primary)", fontWeight: 700 }}>{t.rangeShow}</button>
      {res && <div style={{ marginTop: 10 }} data-testid="range-result">
        <Row label={t.powerPlant} value={`${res.kwh} kWh`} testid="range-kwh" bold />
        <Row label={t.waterTotal} value={`${(res.water_total_l / 1000).toFixed(2)} m³`} testid="range-water-total" bold />
        {res.water_l.map((w, i) => <Row key={i} label={chName(t, dev, i)} value={`${(w / 1000).toFixed(2)} m³`} testid={`range-water-${i}`} />)}
        <a className="action-btn" href={`${API}/devices/${dev.device_id}/usage/range/xlsx?${q}`} data-testid="range-xlsx"
          style={{ width: "100%", padding: 10, marginTop: 10, fontSize: 13, textDecoration: "none", justifyContent: "center" }}><FileSpreadsheet size={15} /> {t.rangeExcel}</a>
        <a href={`${API}/devices/${dev.device_id}/usage/range/csv?${q}`} data-testid="range-csv"
          style={{ display: "block", textAlign: "center", marginTop: 8, fontSize: 12, color: "var(--muted)" }}>{t.orCsv}</a>
      </div>}
    </div>
  );
};

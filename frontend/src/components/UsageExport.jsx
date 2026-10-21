import { chName } from "@/api";
import { useEffect, useState } from "react";
import axios from "axios";
import { Download } from "lucide-react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const day = (d) => d.slice(8, 10) + "." + d.slice(5, 7);

const Bars = ({ data, dataKey, color, unit, testid }) => (
  <div style={{ width: "100%", height: 140 }} data-testid={testid}>
    <ResponsiveContainer>
      <BarChart data={data} margin={{ top: 4, right: 6, left: -18, bottom: 0 }}>
        <CartesianGrid stroke="var(--grid)" vertical={false} />
        <XAxis dataKey="date" tickFormatter={day} stroke="var(--axis)" fontSize={10} />
        <YAxis stroke="var(--axis)" fontSize={10} />
        <Tooltip labelFormatter={day} formatter={(v) => [`${v} ${unit}`]} cursor={{ fill: "var(--surface2)" }}
          contentStyle={{ background: "var(--card)", border: "1px solid var(--border)", fontSize: 12 }} />
        <Bar dataKey={dataKey} fill={color} radius={[3, 3, 0, 0]} isAnimationActive={false} />
      </BarChart>
    </ResponsiveContainer>
  </div>
);

export const DailyUsage = ({ t, deviceId }) => {
  const [days, setDays] = useState([]);
  useEffect(() => {
    const load = () => axios.get(`${API}/devices/${deviceId}/usage/daily?days=7`).then(({ data }) => setDays(data.days || [])).catch(() => {});
    load();
    const i = setInterval(load, 60000);
    return () => clearInterval(i);
  }, [deviceId]);
  return (
    <div className="panel panel-pad" data-testid="daily-usage">
      <div className="font-head" style={{ fontSize: 15, fontWeight: 600, marginBottom: 8 }}>{t.dailyUsage}</div>
      <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 4 }}>{t.power} (kWh)</div>
      <Bars data={days} dataKey="kwh" color="var(--c-power)" unit="kWh" testid="daily-power-chart" />
      <div style={{ fontSize: 11, color: "var(--muted)", margin: "10px 0 4px" }}>{t.water} (m³)</div>
      <Bars data={days} dataKey="water_m3" color="var(--c-water)" unit="m³" testid="daily-water-chart" />
    </div>
  );
};

export const CsvExport = ({ t, ch, deviceId, dev }) => {
  const [hours, setHours] = useState(24);
  const [fmt, setFmt] = useState("xlsx");
  const opts = [[24, "24 h"], [168, `7 ${t.daysShort}`], [720, `30 ${t.daysShort}`]];
  return (
    <div className="panel panel-pad" data-testid="csv-export">
      <div className="font-head" style={{ fontSize: 15, fontWeight: 600, marginBottom: 10 }}>{t.exportCsv} · {chName(t, dev, ch.id)}</div>
      <div className="flex gap-2 mb-3">
        {opts.map(([h, label]) => (
          <button key={h} data-testid={`csv-range-${h}`} onClick={() => setHours(h)} className="font-head"
            style={{
              flex: 1, background: hours === h ? "rgba(var(--primary-rgb),0.16)" : "transparent", color: hours === h ? "var(--primary)" : "var(--muted)",
              border: "1px solid var(--border)", borderRadius: 8, padding: "7px", fontSize: 13, fontWeight: 700, cursor: "pointer",
            }}>{label}</button>
        ))}
      </div>
      <div className="flex gap-2 mb-3">
        {[["xlsx", "Excel"], ["csv", "CSV"]].map(([k, label]) => (
          <button key={k} data-testid={`export-format-${k}`} onClick={() => setFmt(k)} className="font-head"
            style={{ flex: 1, background: fmt === k ? "rgba(var(--primary-rgb),0.16)" : "transparent", color: fmt === k ? "var(--primary)" : "var(--muted)",
              border: "1px solid var(--border)", borderRadius: 8, padding: "7px", fontSize: 13, fontWeight: 700, cursor: "pointer" }}>{label}</button>
        ))}
      </div>
      <a data-testid="csv-download" className="action-btn" href={`${API}/devices/${deviceId}/history/${fmt}?chamber=${ch.id}&hours=${hours}`}
        style={{ width: "100%", padding: 10, textDecoration: "none", color: "var(--text)" }}>
        <Download size={15} /> {t.download}
      </a>
    </div>
  );
};

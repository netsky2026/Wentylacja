import { useEffect, useState } from "react";
import axios from "axios";
import { BarChart, Bar, XAxis, YAxis, Cell, ResponsiveContainer } from "recharts";
import { Building2, Trophy, FileSpreadsheet } from "lucide-react";
import { API } from "@/api";

const fmt = (v, d = 3) => (v == null ? "–" : String(+v.toFixed(d)).replace(".", ","));
const METRICS = [["cost_per_head", "farmCost", "zł", 3], ["water_per_head_l", "farmWater", "l", 2], ["kwh_per_head", "farmPower", "kWh", 3]];
const TopLabel = ({ x, y, width, value, d }) => (
  <text x={x + width / 2} y={y - 4} textAnchor="middle" fontSize={9} style={{ fill: "var(--text)" }}>{fmt(value, d)}</text>
);

export const FarmCompareCard = ({ t }) => {
  const [rows, setRows] = useState(null);
  const [m, setM] = useState(0);
  useEffect(() => { axios.get(`${API}/farms/compare`).then(({ data }) => setRows(data.farms)).catch(() => setRows(false)); }, []);
  if (rows === null) return null;
  if (rows === false) return <div className="panel panel-pad" style={{ fontSize: 12, color: "var(--accent)" }} data-testid="farm-compare-error">{t.loadFailed}</div>;
  const [key, , unit, dec] = METRICS[m];
  const data = rows.filter((r) => r[key] != null);
  const best = data.length ? data.reduce((a, b) => (b[key] < a[key] ? b : a)) : null;
  return (
    <div className="panel panel-pad" data-testid="farm-compare-card">
      <div className="flex items-center gap-2 font-head" style={{ fontSize: 15, fontWeight: 600, marginBottom: 4 }}><Building2 size={16} /> {t.farmTitle}</div>
      <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 8 }}>{t.farmHint}</div>
      <div className="grid gap-1" style={{ gridTemplateColumns: "repeat(3, 1fr)", marginBottom: 8 }}>
        {METRICS.map(([k, label], i) => (
          <button key={k} className="action-btn" onClick={() => setM(i)} data-testid={`farm-metric-${k}`}
            style={{ padding: 7, fontSize: 12, ...(i === m ? { background: "var(--primary)", borderColor: "var(--primary)", color: "var(--on-primary)", fontWeight: 700 } : {}) }}>
            {t[label]} {t.perHeadShort}</button>
        ))}
      </div>
      {best ? (<>
        <div className="flex items-center gap-1" style={{ fontSize: 12, color: "var(--green)", marginBottom: 4 }} data-testid="farm-compare-best">
          <Trophy size={12} /> {t.compareBest}: <b>{best.name}</b> · {fmt(best[key], dec)} {unit} {t.perHeadShort}</div>
        <div style={{ width: "100%", height: 190 }}>
          <ResponsiveContainer>
            <BarChart data={data} margin={{ top: 16, right: 4, left: 0, bottom: 0 }}>
              <XAxis dataKey="name" tick={{ fontSize: 10, fill: "var(--muted)" }} tickLine={false} axisLine={false} interval={0} />
              <YAxis tick={{ fontSize: 10, fill: "var(--muted)" }} tickLine={false} axisLine={false} width={46} tickFormatter={(v) => fmt(v, 4)} />
              <Bar dataKey={key} radius={[4, 4, 0, 0]} isAnimationActive={false} label={(p) => <TopLabel key={p.index} {...p} d={dec} />}>
                {data.map((r) => <Cell key={r.client_id} fill={r.client_id === best.client_id ? "var(--green)" : "var(--primary)"} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </>) : <div style={{ fontSize: 12, color: "var(--muted)" }} data-testid="farm-compare-empty">{t.farmEmpty}</div>}
      <div style={{ overflowX: "auto", marginTop: 8 }}>
        <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }} data-testid="farm-compare-table">
          <thead><tr style={{ color: "var(--muted)", textAlign: "left" }}>
            <th style={{ padding: "4px 6px 4px 0" }}>{t.farmName}</th><th>{t.compareCycles}</th>
            {METRICS.map(([k, label]) => <th key={k} style={{ paddingRight: 6, whiteSpace: "nowrap" }}>{t[label]}</th>)}
          </tr></thead>
          <tbody>{rows.map((r) => (
            <tr key={r.client_id} style={{ borderTop: "1px solid var(--border)", color: best && r.client_id === best.client_id ? "var(--green)" : undefined }}
              data-testid={`farm-compare-row-${r.client_id}`}>
              <td style={{ padding: "5px 6px 5px 0" }}>{r.name}</td><td>{r.cycles}</td>
              {METRICS.map(([k, , , d]) => <td key={k} style={{ paddingRight: 6 }}>{fmt(r[k], d)}</td>)}
            </tr>
          ))}</tbody>
        </table>
      </div>
      <a className="action-btn" href={`${API}/farms/compare/xlsx`} data-testid="farm-compare-xlsx"
        style={{ marginTop: 10, padding: 8, fontSize: 12, textDecoration: "none", justifyContent: "center" }}><FileSpreadsheet size={13} /> {t.farmExport}</a>
    </div>
  );
};

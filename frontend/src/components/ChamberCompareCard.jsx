import { useEffect, useState } from "react";
import axios from "axios";
import { BarChart, Bar, XAxis, YAxis, Cell, ResponsiveContainer, LabelList } from "recharts";
import { Scale, Trophy, FileSpreadsheet } from "lucide-react";
import { API, chName } from "@/api";

const fmt = (v, d = 3) => (v == null ? "–" : String(+v.toFixed(d)).replace(".", ","));

export const ChamberCompareCard = ({ t, dev }) => {
  const [rows, setRows] = useState(null);
  useEffect(() => {
    axios.get(`${API}/devices/${dev.device_id}/cycles/compare`).then(({ data }) => setRows(data.chambers)).catch(() => setRows([]));
  }, [dev.device_id]);
  if (!rows) return null;
  const named = rows.map((r) => ({ ...r, label: chName(t, dev, r.chamber) }));
  const data = named.filter((r) => r.cost_per_head != null);
  const best = data.length ? data.reduce((a, b) => (b.cost_per_head < a.cost_per_head ? b : a)) : null;
  return (
    <div className="panel panel-pad" data-testid="chamber-compare-card">
      <div className="flex items-center gap-2 font-head" style={{ fontSize: 15, fontWeight: 600, marginBottom: 4 }}><Scale size={16} /> {t.compareTitle}</div>
      <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 8 }}>{t.compareHint}</div>
      {best ? (<>
        <div className="flex items-center gap-1" style={{ fontSize: 12, color: "var(--green)", marginBottom: 4 }} data-testid="chamber-compare-best">
          <Trophy size={12} /> {t.compareBest}: <b>{best.label}</b> · {fmt(best.cost_per_head)} zł / {t.cyclePcs}</div>
        <div style={{ width: "100%", height: 180 }}>
          <ResponsiveContainer>
            <BarChart data={data} margin={{ top: 16, right: 4, left: 0, bottom: 0 }}>
              <XAxis dataKey="label" tick={{ fontSize: 10, fill: "var(--muted)" }} tickLine={false} axisLine={false} interval={0} />
              <YAxis tick={{ fontSize: 10, fill: "var(--muted)" }} tickLine={false} axisLine={false} width={46} tickFormatter={(v) => fmt(v)} />
              <Bar dataKey="cost_per_head" radius={[4, 4, 0, 0]}>
                {data.map((d) => <Cell key={d.chamber} fill={d.chamber === best.chamber ? "var(--green)" : "var(--primary)"} />)}
                <LabelList dataKey="cost_per_head" position="top" formatter={(v) => fmt(v)} style={{ fontSize: 9, fill: "var(--text)" }} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </>) : <div style={{ fontSize: 12, color: "var(--muted)" }} data-testid="chamber-compare-empty">{t.compareEmpty}</div>}
      <div style={{ overflowX: "auto", marginTop: 8 }}>
        <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }} data-testid="chamber-compare-table">
          <thead><tr style={{ color: "var(--muted)", textAlign: "left" }}>
            <th style={{ padding: "4px 6px 4px 0" }}>{t.compareChamber}</th><th>{t.compareCycles}</th><th>{t.compareCost}</th><th>{t.compareWater}</th>
          </tr></thead>
          <tbody>{named.map((r) => (
            <tr key={r.chamber} style={{ borderTop: "1px solid var(--border)", color: best && r.chamber === best.chamber ? "var(--green)" : undefined }}
              data-testid={`chamber-compare-row-${r.chamber}`}>
              <td style={{ padding: "5px 6px 5px 0" }}>{r.label}</td><td>{r.cycles}</td>
              <td>{r.cost_per_head == null ? "–" : `${fmt(r.cost_per_head)} zł`}</td><td>{r.water_per_head_l == null ? "–" : `${fmt(r.water_per_head_l, 2)} l`}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
      <a className="action-btn" href={`${API}/devices/${dev.device_id}/cycles/export?fmt=xlsx`} data-testid="chamber-compare-xlsx"
        style={{ marginTop: 10, padding: 8, fontSize: 12, textDecoration: "none", justifyContent: "center" }}><FileSpreadsheet size={13} /> {t.cycleExport}</a>
    </div>
  );
};

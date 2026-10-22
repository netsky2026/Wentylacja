import { BarChart, Bar, XAxis, YAxis, Tooltip, Cell, ResponsiveContainer } from "recharts";
import { Trophy } from "lucide-react";

const fmt = (v) => v.toFixed(3).replace(".", ",");

const TopLabel = ({ x, y, width, value }) => (
  <text x={x + width / 2} y={y - 4} textAnchor="middle" fontSize={9} style={{ fill: "var(--text)" }}>{fmt(value)}</text>
);

export const CycleCostChart = ({ t, rows }) => {
  const data = rows.filter((c) => c.cost_per_head != null).sort((a, b) => a.start.localeCompare(b.start))
    .map((c) => ({ id: c.id, label: c.start.slice(2).split("-").reverse().join("."), v: c.cost_per_head, running: !c.end }));
  if (data.length === 0) return null;
  const done = data.filter((d) => !d.running);
  const best = done.length ? done.reduce((a, b) => (b.v < a.v ? b : a)) : null;
  return (
    <div style={{ marginTop: 10 }} data-testid="cycle-cost-chart">
      <div className="flex items-center justify-between" style={{ fontSize: 12, marginBottom: 4 }}>
        <span style={{ color: "var(--muted)" }}>{t.costChartTitle}</span>
        {best && <span className="flex items-center gap-1" style={{ color: "var(--green)" }} data-testid="cycle-cost-best">
          <Trophy size={12} /> {t.costChartBest}: {best.label} · {fmt(best.v)} zł</span>}
      </div>
      <div style={{ width: "100%", height: 170 }}>
        <ResponsiveContainer>
          <BarChart data={data} margin={{ top: 16, right: 4, left: 0, bottom: 0 }}>
            <XAxis dataKey="label" tick={{ fontSize: 10, fill: "var(--muted)" }} tickLine={false} axisLine={false} />
            <YAxis tick={{ fontSize: 10, fill: "var(--muted)" }} tickLine={false} axisLine={false} width={46} tickFormatter={(v) => String(+v.toFixed(3)).replace(".", ",")} />
            <Tooltip cursor={{ fill: "rgba(255,255,255,0.04)" }} contentStyle={{ background: "var(--card)", border: "1px solid var(--border)", fontSize: 12 }}
              formatter={(v, _n, p) => [`${fmt(v)} zł${p.payload.running ? ` (${t.costChartRunning})` : ""}`, t.costPerHead]} />
            <Bar dataKey="v" radius={[4, 4, 0, 0]} label={(p) => <TopLabel key={p.index} {...p} />}>
              {data.map((d) => (
                <Cell key={d.id} fill={best && d.id === best.id ? "var(--green)" : "var(--primary)"} fillOpacity={d.running ? 0.4 : 1} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      {data.some((d) => d.running) && <div style={{ fontSize: 10, color: "var(--muted)" }}>{t.costChartRunningHint}</div>}
    </div>
  );
};

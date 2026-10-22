import { chName } from "@/api";
import { UsageRangeCard } from "@/components/UsageRangeCard";
import { ChamberCompareCard } from "@/components/ChamberCompareCard";
import { useState, memo, useMemo } from "react";
import { Zap, Droplet } from "lucide-react";
import { DailyUsage, CsvExport } from "@/components/UsageExport";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";

const fmtTime = (ts) => new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

const ChartView = ({ title, data, lines, testid, t, domain = ["auto", "auto"] }) => (
  <div className="panel panel-pad" data-testid={testid}>
    <div className="font-head" style={{ fontSize: 15, fontWeight: 600, marginBottom: 8 }}>{title}</div>
    {data.length < 2 ? (
      <div style={{ color: "var(--muted)", fontSize: 12, padding: "20px 0" }}>{t.noHistory}</div>
    ) : (
      <div style={{ width: "100%", height: 170 }}>
        <ResponsiveContainer>
          <LineChart data={data} margin={{ top: 4, right: 6, left: -18, bottom: 0 }}>
            <CartesianGrid stroke="var(--grid)" vertical={false} />
            <XAxis dataKey="ts" tickFormatter={fmtTime} stroke="var(--axis)" fontSize={10} minTickGap={40} />
            <YAxis stroke="var(--axis)" fontSize={10} domain={domain} allowDataOverflow />
            <Tooltip labelFormatter={fmtTime} contentStyle={{ background: "var(--card)", border: "1px solid var(--border)", fontSize: 12 }} />
            {lines.map(([key, color, name]) => (
              <Line key={key} type="monotone" dataKey={key} name={name} stroke={color} dot={false} strokeWidth={2} isAnimationActive={false} />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    )}
  </div>
);
const Chart = memo(ChartView, (a, b) => a.data === b.data && a.title === b.title && a.t === b.t);

const PlantTile = ({ plant, t }) => {
  const Cell = ({ icon, label, value, unit, sub, testid }) => (
    <div className="sensor" data-testid={testid}>
      <span className="flex items-center gap-1" style={{ color: "var(--muted)", fontSize: 10 }}>{icon}{label}</span>
      <span className="font-head" style={{ fontSize: 22, fontWeight: 700 }}>
        {value}<span style={{ fontSize: 12, color: "var(--muted)", fontWeight: 500 }}> {unit}</span>
      </span>
      <span style={{ fontSize: 10, color: "var(--muted)" }}>{sub}</span>
    </div>
  );
  return (
    <div className="panel panel-pad" data-testid="plant-tile">
      <div className="font-head" style={{ fontSize: 15, fontWeight: 700, marginBottom: 10 }}>{t.plant}</div>
      <div className="grid gap-2" style={{ gridTemplateColumns: "1fr 1fr" }}>
        <Cell icon={<Zap size={11} />} label={t.power} value={plant.power_kw?.toFixed(2)} unit="kW"
          sub={`${t.total}: ${plant.power_kwh?.toFixed(1)} kWh`} testid="plant-power" />
        <Cell icon={<Droplet size={11} />} label={t.water} value={plant.water_lpm?.toFixed(1)} unit="l/min"
          sub={`${t.total}: ${(plant.water_total_l / 1000).toFixed(2)} m³`} testid="plant-water" />
      </div>
    </div>
  );
};

const FILTERS = [["all", "allLevels"], ["actions", "levelCommand"], ["alarms", "levelWarning"]];
const matches = (e, f) => f === "all" || (f === "actions" ? !!e.meta?.user : e.level === "warning");

const EventLog = ({ t, events }) => {
  const [f, setF] = useState("all");
  const list = events.filter((e) => matches(e, f));
  return (
    <div className="panel panel-pad" data-testid="event-log-card">
      <div className="flex items-center justify-between" style={{ marginBottom: 10 }}>
        <span className="font-head" style={{ fontSize: 15, fontWeight: 600 }}>{t.eventLog}</span>
        <div className="flex gap-1">
          {FILTERS.map(([k, label]) => (
            <button key={k} data-testid={`log-filter-${k}`} onClick={() => setF(k)} className="font-head"
              style={{ background: f === k ? "rgba(var(--primary-rgb),0.16)" : "transparent", color: f === k ? "var(--primary)" : "var(--muted)",
                border: `1px solid ${f === k ? "var(--primary)" : "var(--border)"}`, borderRadius: 999, padding: "3px 9px",
                fontSize: 11, fontWeight: 700, cursor: "pointer" }}>{t[label]}</button>
          ))}
        </div>
      </div>
      <div data-testid="event-log" style={{ maxHeight: 320, overflowY: "auto", display: "flex", flexDirection: "column", gap: 5 }}>
        {list.length === 0 && <div style={{ color: "var(--muted)", fontSize: 12 }}>{t.noEvents}</div>}
        {list.map((e, i) => (
          <div key={i} className={`log-line ${e.level}`} style={{ padding: "5px 10px" }} data-testid="event-line">
            <div style={{ fontSize: 12 }}>{e.message}</div>
            <div style={{ color: "var(--muted)", fontSize: 10 }}>
              {new Date(e.ts).toLocaleString([], { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" })}
              {e.meta?.user && <span data-testid="event-user"> · {e.meta.user}</span>}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export const DataView = ({ t, ch, deviceId, plant, history, plantHistory, events, dev }) => {
  const raw = history[String(ch?.id)];
  const data = useMemo(() => (raw || []).map((d) => ({
    ...d, cl_closed: d.curtain_left == null ? null : 100 - d.curtain_left,
    cr_closed: d.curtain_right == null ? null : 100 - d.curtain_right,
  })), [raw]);
  return (
    <div className="fade-in" style={{ display: "flex", flexDirection: "column", gap: 12 }} data-testid="data-view">
      {plant && <PlantTile plant={plant} t={t} />}
      <DailyUsage t={t} deviceId={deviceId} />
      {dev && <UsageRangeCard t={t} dev={dev} />}
      {dev && <ChamberCompareCard key={dev.device_id} t={t} dev={dev} />}
      <div className="font-head" style={{ fontSize: 13, color: "var(--muted)", marginTop: 4 }}>{t.history} · {chName(t, dev, ch?.id ?? 0)} · 3 {t.hours}</div>
      <Chart t={t} title={t.historyTemp} data={data} lines={[["temp", "var(--text)", t.temp]]} testid="chart-temp" />
      <Chart t={t} title={t.historyHum} data={data} lines={[["humidity", "var(--c-water)", t.humidity]]} testid="chart-humidity" domain={[0, 100]} />
      <Chart t={t} title={t.historyCo2} data={data} lines={[["co2", "var(--c-co2)", t.co2]]} testid="chart-co2" />
      <Chart t={t} title={t.historyVent} data={data} testid="chart-vent" domain={[0, 100]}
        lines={[["cl_closed", "var(--c-cl)", t.curtainLeft], ["cr_closed", "var(--c-cr)", t.curtainRight], ["chimney", "var(--c-chim)", t.chimney]]} />
      <Chart t={t} title={t.historyPlant} data={plantHistory} testid="chart-plant"
        lines={[["power_kw", "var(--c-power)", `${t.power} kW`], ["water_lpm", "var(--c-water)", `${t.water} l/min`]]} />

      {ch && <CsvExport t={t} ch={ch} deviceId={deviceId} dev={dev} />}

      <EventLog t={t} events={events} />
    </div>
  );
};

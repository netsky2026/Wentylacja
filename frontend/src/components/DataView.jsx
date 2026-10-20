import { Zap, Droplet } from "lucide-react";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";

const fmtTime = (ts) => new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

const Chart = ({ title, data, lines, testid, t }) => (
  <div className="panel panel-pad" data-testid={testid}>
    <div className="font-head" style={{ fontSize: 15, fontWeight: 600, marginBottom: 8 }}>{title}</div>
    {data.length < 2 ? (
      <div style={{ color: "var(--muted)", fontSize: 12, padding: "20px 0" }}>{t.noHistory}</div>
    ) : (
      <div style={{ width: "100%", height: 170 }}>
        <ResponsiveContainer>
          <LineChart data={data} margin={{ top: 4, right: 6, left: -18, bottom: 0 }}>
            <CartesianGrid stroke="#222" vertical={false} />
            <XAxis dataKey="ts" tickFormatter={fmtTime} stroke="#666" fontSize={10} minTickGap={40} />
            <YAxis stroke="#666" fontSize={10} domain={["auto", "auto"]} />
            <Tooltip labelFormatter={fmtTime} contentStyle={{ background: "#141414", border: "1px solid #262626", fontSize: 12 }} />
            {lines.map(([key, color, name]) => (
              <Line key={key} type="monotone" dataKey={key} name={name} stroke={color} dot={false} strokeWidth={2} isAnimationActive={false} />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    )}
  </div>
);

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

export const DataView = ({ t, ch, plant, history, plantHistory, events }) => {
  const data = (history[String(ch?.id)] || []).map((d) => ({
    ...d, cl_closed: d.curtain_left == null ? null : 100 - d.curtain_left,
    cr_closed: d.curtain_right == null ? null : 100 - d.curtain_right,
  }));
  return (
    <div className="fade-in" style={{ display: "flex", flexDirection: "column", gap: 12 }} data-testid="data-view">
      {plant && <PlantTile plant={plant} t={t} />}
      <div className="font-head" style={{ fontSize: 13, color: "var(--muted)", marginTop: 4 }}>{t.history} · {ch?.name} · 3 {t.hours}</div>
      <Chart t={t} title={t.historyTemp} data={data} lines={[["temp", "#d6dbe0", t.temp]]} testid="chart-temp" />
      <Chart t={t} title={t.historyHum} data={data} lines={[["humidity", "#7fa3b8", t.humidity]]} testid="chart-humidity" />
      <Chart t={t} title={t.historyCo2} data={data} lines={[["co2", "#b8a37f", t.co2]]} testid="chart-co2" />
      <Chart t={t} title={t.historyVent} data={data} testid="chart-vent"
        lines={[["cl_closed", "#8a9bb0", t.curtainLeft], ["cr_closed", "#6f8a7a", t.curtainRight], ["chimney", "#c9c9c9", t.chimney]]} />
      <Chart t={t} title={t.historyPlant} data={plantHistory} testid="chart-plant"
        lines={[["power_kw", "#c9a46a", `${t.power} kW`], ["water_lpm", "#7fa3b8", `${t.water} l/min`]]} />

      <div className="panel panel-pad">
        <div className="font-head" style={{ fontSize: 15, fontWeight: 600, marginBottom: 10 }}>{t.eventLog}</div>
        <div data-testid="event-log" style={{ maxHeight: 280, overflowY: "auto", display: "flex", flexDirection: "column", gap: 5 }}>
          {events.length === 0 && <div style={{ color: "var(--muted)", fontSize: 12 }}>{t.noEvents}</div>}
          {events.map((e, i) => (
            <div key={i} className={`log-line ${e.level}`} style={{ padding: "5px 10px" }}>
              <div style={{ fontSize: 12 }}>{e.message}</div>
              <div style={{ color: "var(--muted)", fontSize: 10 }}>{new Date(e.ts).toLocaleTimeString()}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

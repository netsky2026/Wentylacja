import { AlertTriangle, ChevronRight } from "lucide-react";

const DeviceCard = ({ d, st, t, onOpen }) => {
  const chambers = st?.chambers || [];
  const alarms = chambers.filter((c) => c.alarm).length;
  return (
    <button className={`panel panel-pad tile ${alarms ? "alarm-card" : ""}`} onClick={onOpen} data-testid={`overview-device-${d.device_id}`}
      style={{ textAlign: "left", width: "100%", cursor: "pointer" }}>
      <div className="flex items-center justify-between" style={{ marginBottom: 10, width: "100%" }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: 11, color: "var(--muted)" }}>{d.client_name}</div>
          <div className="font-head flex items-center gap-2" style={{ fontSize: 17, fontWeight: 700 }}>
            <span className={`led ${alarms ? "warn pulse" : d.online ? "ok" : ""}`} style={!d.online && !alarms ? { background: "var(--off)" } : undefined} />
            {d.name}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {alarms > 0 && <span className="badge badge-alarm" data-testid={`overview-alarms-${d.device_id}`}><AlertTriangle size={11} /> {alarms}</span>}
          {!d.online && <span style={{ fontSize: 11, color: "var(--muted)" }}>{t.offlineShort}</span>}
          <ChevronRight size={16} color="var(--muted)" />
        </div>
      </div>
      <div className="grid gap-1" style={{ width: "100%", gridTemplateColumns: `repeat(${Math.min(5, Math.max(chambers.length, 1))}, 1fr)` }}>
        {chambers.map((c) => (
          <div key={c.id} className="reg-cell" style={{ padding: "6px 4px", textAlign: "center", opacity: c.on ? 1 : 0.5,
            borderColor: c.alarm ? "var(--accent)" : undefined }} data-testid={`overview-${d.device_id}-ch-${c.id}`}>
            <div style={{ fontSize: 9, color: "var(--muted)" }}>{t.chamberShort}{c.id + 1}</div>
            <div className="font-head" style={{ fontSize: 15, fontWeight: 700, color: c.temp_alarm ? "var(--accent)" : "var(--text)" }}>{c.temp.toFixed(1)}°</div>
            <div style={{ fontSize: 9, color: c.co2_alarm ? "var(--accent)" : "var(--muted)" }}>{Math.round(c.co2)}</div>
          </div>
        ))}
        {chambers.length === 0 && <div style={{ fontSize: 11, color: "var(--muted)" }}>{t.waitingData}</div>}
      </div>
    </button>
  );
};

export const OverviewView = ({ t, devices, states, onOpen }) => {
  const sorted = [...devices].sort((a, b) => {
    const al = (d) => (states[d.device_id]?.chambers || []).filter((c) => c.alarm).length;
    return al(b) - al(a) || Number(b.online) - Number(a.online);
  });
  return (
    <div className="fade-in" style={{ display: "flex", flexDirection: "column", gap: 10 }} data-testid="overview-view">
      <div className="font-head" style={{ fontSize: 13, color: "var(--muted)" }}>{t.overviewHint}</div>
      {sorted.map((d) => <DeviceCard key={d.device_id} d={d} st={states[d.device_id]} t={t} onOpen={() => onOpen(d.device_id)} />)}
    </div>
  );
};

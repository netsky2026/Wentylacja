import { LayoutGrid, LineChart, Settings, Building2 } from "lucide-react";

export const BottomNav = ({ view, setView, t, showOverview }) => {
  const items = [...(showOverview ? [["overview", t.overview, Building2]] : []),
    ["chambers", t.chambers, LayoutGrid], ["data", t.details, LineChart], ["settings", t.settingsTab, Settings]];
  return (
    <nav className="bottom-nav" data-testid="bottom-nav">
      {items.map(([k, label, Icon]) => (
        <button key={k} data-testid={`nav-${k}`} onClick={() => setView(k)}
          className={`bottom-nav-btn ${view === k ? "active" : ""}`}>
          <Icon size={20} />
          <span>{label}</span>
        </button>
      ))}
    </nav>
  );
};

export const ChamberSwitch = ({ chambers, selected, setSelected, t }) => {
  const many = chambers.length > 3;
  return (
    <div className="panel flex mb-3 chamber-switch" style={{ overflowX: "auto" }} data-testid="chamber-switch">
      {chambers.map((ch) => (
        <button key={ch.id} data-testid={`chamber-tab-${ch.id}`} onClick={() => setSelected(ch.id)}
          className="font-head flex items-center justify-center gap-2"
          style={{
            flex: many ? "1 0 auto" : 1, minWidth: many ? 52 : 0, background: selected === ch.id ? "rgba(var(--primary-rgb),0.14)" : "transparent",
            color: selected === ch.id ? "var(--text)" : "var(--muted)", border: "none",
            boxShadow: selected === ch.id ? "inset 0 -2px 0 var(--primary)" : "none",
            padding: many ? "11px 6px" : "11px 10px", cursor: "pointer", fontSize: 14, fontWeight: 700, whiteSpace: "nowrap",
            transition: "background-color 0.2s ease, color 0.2s ease",
          }}>
          <span className={`led ${ch.alarm ? "warn pulse" : ch.on ? "ok" : ""}`} style={!ch.on && !ch.alarm ? { background: "var(--off)" } : undefined} />
          {many ? `${t.chamberShort}${ch.id + 1}` : `${t.chamberWord} ${ch.id + 1}`}
        </button>
      ))}
    </div>
  );
};

export const DevicePicker = ({ devices, value, onChange, t, states }) => {
  const label = (d) => `${d.client_name} · ${d.name}`;
  const alarm = (d) => (states[d.device_id]?.chambers || []).some((c) => c.alarm);
  const cur = devices.find((d) => d.device_id === value) || devices[0];
  return (
    <div className="panel flex items-center gap-2 mb-3" style={{ padding: "4px 6px 4px 14px" }} data-testid="device-picker">
      <span className={`led ${alarm(cur) ? "warn pulse" : cur.online ? "ok" : ""}`} style={!cur.online && !alarm(cur) ? { background: "var(--off)" } : undefined} />
      {devices.length === 1 ? (
        <span className="font-head" data-testid="device-name" style={{ fontSize: 15, fontWeight: 700, padding: "8px 0" }}>{label(cur)}</span>
      ) : (
        <select className="device-select font-head" value={cur.device_id} onChange={(e) => onChange(e.target.value)} data-testid="device-select">
          {devices.map((d) => (
            <option key={d.device_id} value={d.device_id}>{alarm(d) ? "⚠ " : ""}{label(d)}{d.online ? "" : ` (${t.offlineShort})`}</option>
          ))}
        </select>
      )}
    </div>
  );
};

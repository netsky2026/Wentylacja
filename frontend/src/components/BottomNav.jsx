import { LayoutGrid, LineChart, Settings } from "lucide-react";

export const BottomNav = ({ view, setView, t }) => {
  const items = [["chambers", t.chambers, LayoutGrid], ["data", t.details, LineChart], ["settings", t.settingsTab, Settings]];
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

export const ChamberSwitch = ({ chambers, selected, setSelected }) => (
  <div className="panel flex mb-3" style={{ overflow: "hidden" }} data-testid="chamber-switch">
    {chambers.map((ch) => (
      <button key={ch.id} data-testid={`chamber-tab-${ch.id}`} onClick={() => setSelected(ch.id)}
        className="font-head flex items-center justify-center gap-2"
        style={{
          flex: 1, background: selected === ch.id ? "#2a2f35" : "transparent",
          color: selected === ch.id ? "var(--text)" : "var(--muted)", border: "none",
          padding: "11px 4px", cursor: "pointer", fontSize: 14, fontWeight: 700,
          transition: "background-color 0.2s ease, color 0.2s ease",
        }}>
        <span className={`led ${ch.alarm ? "warn pulse" : ch.on ? "ok" : ""}`} style={!ch.on && !ch.alarm ? { background: "#444" } : undefined} />
        {ch.name}
      </button>
    ))}
  </div>
);

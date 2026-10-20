import { useEffect, useRef, useState, useCallback } from "react";
import axios from "axios";
import { Snowflake, Thermometer, Droplets, Wind, Power, DoorOpen, DoorClosed,
  AlertTriangle, Minus, Plus, LayoutGrid, Database, Fan } from "lucide-react";
import { I18N } from "@/i18n";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export default function App() {
  const [lang, setLang] = useState("pl");
  const t = I18N[lang];
  const [view, setView] = useState("chambers");
  const [selected, setSelected] = useState(null);
  const [state, setState] = useState(null);
  const [online, setOnline] = useState(false);
  const [brokerConnected, setBrokerConnected] = useState(false);
  const [simOn, setSimOn] = useState(true);
  const [config, setConfig] = useState(null);
  const [events, setEvents] = useState([]);
  const wsRef = useRef(null);

  const loadHealth = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/health`);
      setBrokerConnected(data.broker_connected);
      setOnline(data.device_online);
      setSimOn(data.simulator_enabled);
    } catch (e) { /* noop */ }
  }, []);

  useEffect(() => {
    axios.get(`${API}/config`).then(({ data }) => setConfig(data));
    axios.get(`${API}/events?limit=50`).then(({ data }) => setEvents(data.events || []));
    loadHealth();
    const hi = setInterval(loadHealth, 3000);
    return () => clearInterval(hi);
  }, [loadHealth]);

  useEffect(() => {
    const wsUrl = `${BACKEND_URL.replace(/^http/, "ws")}/api/ws`;
    let stop = false;
    const connect = () => {
      if (stop) return;
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;
      ws.onclose = () => { if (!stop) setTimeout(connect, 2000); };
      ws.onmessage = (e) => {
        const msg = JSON.parse(e.data);
        if (msg.type === "state") { setState(msg.payload); setOnline(true); }
        else if (msg.type === "event") setEvents((p) => [msg.event, ...p].slice(0, 50));
      };
    };
    connect();
    return () => { stop = true; if (wsRef.current) wsRef.current.close(); };
  }, []);

  const send = async (body) => {
    try { await axios.post(`${API}/device/chlodnia-01/command`, body); } catch (e) { /* noop */ }
  };
  const toggleSim = async () => {
    const { data } = await axios.post(`${API}/simulator/toggle?enable=${!simOn}`);
    setSimOn(data.simulator_enabled);
  };

  const chambers = state?.chambers || [];

  return (
    <div className="app-shell">
      <div className="mobile-wrap">
        {/* Header */}
        <header className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Snowflake size={22} color="#007AFF" />
            <span className="font-head" data-testid="app-title" style={{ fontSize: 20, fontWeight: 700 }}>{t.appName}</span>
          </div>
          <div className="panel flex" style={{ overflow: "hidden" }}>
            {["pl", "en"].map((l) => (
              <button key={l} data-testid={`lang-${l}`} onClick={() => setLang(l)} className="font-head"
                style={{
                  background: lang === l ? "var(--primary)" : "transparent",
                  color: lang === l ? "#fff" : "var(--muted)",
                  border: "none", padding: "7px 11px", cursor: "pointer", fontSize: 13, fontWeight: 700,
                }}>{l.toUpperCase()}</button>
            ))}
          </div>
        </header>

        {/* Connection line */}
        <div className="panel flex items-center justify-between mb-3" data-testid="status-bar" style={{ padding: "9px 14px" }}>
          <span className="flex items-center gap-2" style={{ fontSize: 12 }}>
            <span className={`led ${brokerConnected ? "ok" : "warn"} ${brokerConnected ? "" : "pulse"}`} />
            {brokerConnected ? t.brokerConnected : t.brokerDisconnected}
          </span>
          <span className="flex items-center gap-2" style={{ fontSize: 12, color: online ? "var(--green)" : "var(--muted)" }}>
            <span className={`led ${online ? "ok" : "warn"}`} />
            {online ? t.deviceOnline : t.deviceOffline}
          </span>
        </div>

        {/* Tabs */}
        <div className="panel flex mb-4" style={{ overflow: "hidden" }}>
          {[["chambers", t.chambers, <LayoutGrid size={15} key="a" />], ["details", t.details, <Database size={15} key="b" />]].map(([k, label, icon]) => (
            <button key={k} data-testid={`tab-${k}`} onClick={() => setView(k)}
              className="font-head flex items-center justify-center gap-2"
              style={{
                flex: 1, background: view === k ? "var(--primary)" : "transparent",
                color: view === k ? "#fff" : "var(--muted)", border: "none",
                padding: "11px", cursor: "pointer", fontSize: 14, fontWeight: 700,
              }}>{icon}{label}</button>
          ))}
        </div>

        {view === "chambers" ? (
          <div>
            <div className="tile-grid">
              {chambers.length === 0 && (
                <div className="panel panel-pad" style={{ color: "var(--muted)", textAlign: "center", gridColumn: "1 / -1" }}>…</div>
              )}
              {chambers.map((ch) => (
                <ChamberTile key={ch.id} ch={ch} t={t} active={selected === ch.id}
                  onClick={() => setSelected(selected === ch.id ? null : ch.id)} />
              ))}
            </div>
            {selected != null && chambers.find((c) => c.id === selected) && (
              <div style={{ marginTop: 14 }}>
                <ChamberDetail ch={chambers.find((c) => c.id === selected)} t={t} send={send}
                  onClose={() => setSelected(null)} />
              </div>
            )}
          </div>
        ) : (
          <DetailsView t={t} config={config} chambers={chambers} events={events}
            simOn={simOn} toggleSim={toggleSim} ts={state?.ts} />
        )}
      </div>
    </div>
  );
}

function Sensor({ icon, label, value, unit, color, testid, warn }) {
  return (
    <div className="sensor" data-testid={testid}>
      <span className="flex items-center gap-1" style={{ color: "var(--muted)", fontSize: 10 }}>
        {icon}{label}
      </span>
      <span className="font-head" style={{ fontSize: 24, fontWeight: 700, color: warn ? "var(--accent)" : color }}>
        {value}<span style={{ fontSize: 12, color: "var(--muted)", fontWeight: 500 }}> {unit}</span>
      </span>
    </div>
  );
}

function ChamberTile({ ch, t, active, onClick }) {
  return (
    <button data-testid={`chamber-${ch.id}`} onClick={onClick}
      className={`tile ${active ? "tile-active" : ""} ${ch.alarm ? "alarm-card" : ""}`}
      style={{ opacity: ch.on ? 1 : 0.68 }}>
      <div className="flex items-center justify-between" style={{ width: "100%" }}>
        <span className="flex items-center gap-1" style={{ minWidth: 0 }}>
          <span className={`led ${ch.on ? "ok" : "warn"}`} />
          <span className="font-head" style={{ fontSize: 15, fontWeight: 700, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{ch.name}</span>
        </span>
        {ch.alarm
          ? <AlertTriangle size={14} color="#FF3B30" data-testid={`chamber-${ch.id}-alarm`} />
          : ch.cooling ? <Snowflake size={14} color="#007AFF" /> : null}
      </div>

      <div className="font-head" data-testid={`chamber-${ch.id}-temp`}
        style={{ fontSize: 38, fontWeight: 700, lineHeight: 1, color: ch.alarm ? "var(--accent)" : "#5AC8FA", margin: "8px 0 2px" }}>
        {ch.temp?.toFixed(1)}<span style={{ fontSize: 15, color: "var(--muted)" }}>°C</span>
      </div>

      <div className="flex items-center justify-between" style={{ width: "100%", marginTop: 6 }}>
        <span className="flex items-center gap-1" data-testid={`chamber-${ch.id}-humidity`} style={{ fontSize: 12, color: "#64D2FF" }}>
          <Droplets size={12} /> {Math.round(ch.humidity)}%
        </span>
        <span className="flex items-center gap-1" data-testid={`chamber-${ch.id}-co2`} style={{ fontSize: 12, color: ch.co2 > 1500 ? "var(--accent)" : "#FFD60A" }}>
          <Wind size={12} /> {Math.round(ch.co2)}
        </span>
      </div>
    </button>
  );
}

function ChamberDetail({ ch, t, send, onClose }) {
  return (
    <div className={`panel panel-pad ${ch.alarm ? "alarm-card" : ""}`} data-testid={`chamber-${ch.id}-detail`}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className={`led ${ch.on ? "ok" : "warn"}`} />
          <span className="font-head" style={{ fontSize: 20, fontWeight: 700 }}>{ch.name}</span>
        </div>
        <div className="flex items-center gap-2">
          {ch.alarm && <span className="badge badge-alarm"><AlertTriangle size={12} /> {t.alarm}</span>}
          <span className="font-head" style={{ fontSize: 12, color: ch.on ? "var(--green)" : "var(--muted)" }}>{ch.on ? t.running : t.off}</span>
        </div>
      </div>

      <div className="grid gap-2 mb-3" style={{ gridTemplateColumns: "repeat(3, 1fr)" }}>
        <Sensor icon={<Thermometer size={11} />} label={t.temp} value={ch.temp?.toFixed(1)} unit="°C" color="#5AC8FA" warn={ch.alarm} />
        <Sensor icon={<Droplets size={11} />} label={t.humidity} value={Math.round(ch.humidity)} unit="%" color="#64D2FF" />
        <Sensor icon={<Wind size={11} />} label={t.co2} value={Math.round(ch.co2)} unit="ppm" color="#FFD60A" warn={ch.co2 > 1500} />
      </div>

      <div className="flex flex-wrap gap-2 mb-3">
        <StatusChip on={ch.cooling} icon={<Snowflake size={11} />} label={t.cooling} color="var(--primary)" />
        <StatusChip on={ch.compressor} icon={<Fan size={11} />} label={t.compressor} color="var(--green)" />
        <StatusChip on={ch.defrost} icon={<Thermometer size={11} />} label={t.defrost} color="var(--accent)" />
        <span className="badge" style={{ color: ch.door_open ? "var(--accent)" : "var(--muted)", borderColor: ch.door_open ? "var(--accent)" : "var(--border)" }}>
          {ch.door_open ? <DoorOpen size={11} /> : <DoorClosed size={11} />} {ch.door_open ? t.doorOpen : t.doorClosed}
        </span>
      </div>

      {ch.on && (
        <div className="flex items-center justify-between reg-cell mb-3" style={{ padding: "8px 12px" }}>
          <span style={{ color: "var(--muted)", fontSize: 12 }}>{t.setpoint}</span>
          <div className="flex items-center gap-3">
            <button data-testid={`chamber-${ch.id}-sp-down`} className="sp-btn"
              onClick={() => send({ type: "set_setpoint", chamber: ch.id, value: Math.round((ch.setpoint - 0.5) * 10) / 10 })}>
              <Minus size={16} />
            </button>
            <span className="font-head" data-testid={`chamber-${ch.id}-setpoint`} style={{ fontSize: 20, fontWeight: 700, minWidth: 64, textAlign: "center" }}>
              {ch.setpoint?.toFixed(1)}°C
            </span>
            <button data-testid={`chamber-${ch.id}-sp-up`} className="sp-btn"
              onClick={() => send({ type: "set_setpoint", chamber: ch.id, value: Math.round((ch.setpoint + 0.5) * 10) / 10 })}>
              <Plus size={16} />
            </button>
          </div>
        </div>
      )}

      <div className="grid gap-2" style={{ gridTemplateColumns: ch.on ? "1fr 1fr" : "1fr" }}>
        <button data-testid={`chamber-${ch.id}-power`} onClick={() => send({ type: "chamber_power", chamber: ch.id, value: !ch.on })}
          className="action-btn" style={{
            background: ch.on ? "rgba(255,59,48,0.12)" : "rgba(48,209,88,0.14)",
            color: ch.on ? "var(--accent)" : "var(--green)",
            borderColor: ch.on ? "var(--accent)" : "var(--green)",
          }}>
          <Power size={16} /> {ch.on ? t.turnOff : t.turnOn}
        </button>
        {ch.on && (
          <button data-testid={`chamber-${ch.id}-defrost`} onClick={() => send({ type: "defrost", chamber: ch.id, value: !ch.defrost })}
            className="action-btn" style={{
              background: ch.defrost ? "rgba(255,59,48,0.12)" : "#141414",
              color: ch.defrost ? "var(--accent)" : "var(--text)",
              borderColor: ch.defrost ? "var(--accent)" : "var(--border)",
            }}>
            <Thermometer size={16} /> {ch.defrost ? t.stopDefrost : t.startDefrost}
          </button>
        )}
      </div>
    </div>
  );
}

function StatusChip({ on, icon, label, color }) {
  return (
    <span className="badge" style={{ color: on ? color : "var(--muted)", borderColor: on ? color : "var(--border)", opacity: on ? 1 : 0.6 }}>
      {icon} {label}
    </span>
  );
}

function DetailsView({ t, config, chambers, events, simOn, toggleSim, ts }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      {/* raw data table */}
      <div className="panel panel-pad">
        <h3 className="font-head mb-3" style={{ fontSize: 16, fontWeight: 600, margin: "0 0 12px" }}>{t.rawData}</h3>
        <div style={{ overflowX: "auto" }}>
          <table className="data-table" data-testid="raw-table">
            <thead>
              <tr>
                <th>#</th><th>{t.temp}</th><th>{t.setpoint}</th><th>{t.humidity}</th><th>{t.co2}</th><th>{t.status}</th>
              </tr>
            </thead>
            <tbody>
              {chambers.map((ch) => (
                <tr key={ch.id} data-testid={`raw-row-${ch.id}`}>
                  <td className="font-head">{ch.name}</td>
                  <td style={{ color: ch.alarm ? "var(--accent)" : "#5AC8FA" }}>{ch.temp?.toFixed(1)}°C</td>
                  <td>{ch.setpoint?.toFixed(1)}°C</td>
                  <td>{Math.round(ch.humidity)}%</td>
                  <td>{Math.round(ch.co2)} ppm</td>
                  <td>{ch.on ? (ch.defrost ? t.defrost : ch.cooling ? t.cooling : t.running) : t.off}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* simulator */}
      <div className="panel flex items-center justify-between" style={{ padding: "12px 16px" }}>
        <span style={{ fontSize: 13 }}>{t.simulator}</span>
        <button data-testid="sim-toggle" onClick={toggleSim} className="font-head"
          style={{
            background: simOn ? "rgba(48,209,88,0.15)" : "#1a1a1a",
            color: simOn ? "var(--green)" : "var(--muted)",
            border: `1px solid ${simOn ? "var(--green)" : "var(--border)"}`,
            borderRadius: 6, padding: "4px 14px", cursor: "pointer", fontWeight: 700, fontSize: 13,
          }}>{simOn ? t.on : t.off}</button>
      </div>

      {/* broker settings */}
      {config && (
        <div className="panel panel-pad">
          <h3 className="font-head mb-2" style={{ fontSize: 16, fontWeight: 600, margin: "0 0 6px" }}>{t.settings}</h3>
          <Row k={t.host} v={config.broker_host} testid="cfg-host" />
          <Row k={t.port} v={config.broker_port} testid="cfg-port" />
          <Row k={t.prefix} v={config.prefix} testid="cfg-prefix" />
          <Row k={t.stateTopic} v={config.state_topic} small testid="cfg-state-topic" />
          <Row k={t.commandTopic} v={config.command_topic} small testid="cfg-command-topic" />
        </div>
      )}

      {/* event log */}
      <div className="panel panel-pad">
        <h3 className="font-head mb-2" style={{ fontSize: 16, fontWeight: 600, margin: "0 0 10px" }}>{t.eventLog}</h3>
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

      {ts && <div style={{ color: "var(--muted)", fontSize: 11, textAlign: "center" }}>{t.lastUpdate}: {new Date(ts).toLocaleTimeString()}</div>}
    </div>
  );
}

function Row({ k, v, small, testid }) {
  return (
    <div className="flex items-center justify-between" style={{ padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
      <span style={{ color: "var(--muted)", fontSize: 12 }}>{k}</span>
      <span data-testid={testid} style={{ fontSize: small ? 11 : 13, textAlign: "right", wordBreak: "break-all", maxWidth: "62%" }}>{v}</span>
    </div>
  );
}

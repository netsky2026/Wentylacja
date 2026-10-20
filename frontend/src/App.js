import { useEffect, useRef, useState, useCallback } from "react";
import axios from "axios";
import { Power, Cpu, Activity, Radio, Settings2, ScrollText, Zap, CircuitBoard, Languages } from "lucide-react";
import { I18N } from "@/i18n";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

function IODot({ label, on, kind, onClick, testid }) {
  const cls = on ? (kind === "Y" ? "on-y" : kind === "M" ? "on-m" : "on-x") : "";
  return (
    <div
      data-testid={testid}
      className={`io-dot ${cls} ${onClick ? "clickable" : ""}`}
      onClick={onClick}
    >
      <span className="font-head" style={{ fontSize: 15, fontWeight: 700 }}>{label}</span>
      <span style={{ fontSize: 10, opacity: 0.85 }}>{on ? "1" : "0"}</span>
    </div>
  );
}

function Panel({ title, hint, icon, children }) {
  return (
    <div className="panel panel-pad">
      <div className="flex items-center gap-2 mb-1">
        <span style={{ color: "var(--primary)" }}>{icon}</span>
        <h3 className="font-head" style={{ fontSize: 18, fontWeight: 600, margin: 0 }}>{title}</h3>
      </div>
      {hint && <p style={{ color: "var(--muted)", fontSize: 11, margin: "0 0 14px" }}>{hint}</p>}
      {children}
    </div>
  );
}

export default function App() {
  const [lang, setLang] = useState("pl");
  const t = I18N[lang];
  const [config, setConfig] = useState(null);
  const [state, setState] = useState(null);
  const [online, setOnline] = useState(false);
  const [brokerConnected, setBrokerConnected] = useState(false);
  const [simOn, setSimOn] = useState(true);
  const [events, setEvents] = useState([]);
  const [logFilter, setLogFilter] = useState("all");
  const [regInputs, setRegInputs] = useState({});
  const [wsUp, setWsUp] = useState(false);
  const wsRef = useRef(null);

  const loadConfig = useCallback(async () => {
    const { data } = await axios.get(`${API}/config`);
    setConfig(data);
  }, []);

  const loadEvents = useCallback(async () => {
    const { data } = await axios.get(`${API}/events?limit=120`);
    setEvents(data.events || []);
  }, []);

  const loadHealth = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/health`);
      setBrokerConnected(data.broker_connected);
      setOnline(data.device_online);
      setSimOn(data.simulator_enabled);
    } catch (e) { /* noop */ }
  }, []);

  useEffect(() => {
    loadConfig();
    loadEvents();
    loadHealth();
    const hi = setInterval(loadHealth, 3000);
    return () => clearInterval(hi);
  }, [loadConfig, loadEvents, loadHealth]);

  useEffect(() => {
    const wsUrl = `${BACKEND_URL.replace(/^http/, "ws")}/api/ws`;
    let stop = false;
    const connect = () => {
      if (stop) return;
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;
      ws.onopen = () => setWsUp(true);
      ws.onclose = () => { setWsUp(false); if (!stop) setTimeout(connect, 2000); };
      ws.onmessage = (e) => {
        const msg = JSON.parse(e.data);
        if (msg.type === "state") { setState(msg.payload); setOnline(true); }
        else if (msg.type === "event") { setEvents((prev) => [msg.event, ...prev].slice(0, 120)); }
      };
    };
    connect();
    return () => { stop = true; if (wsRef.current) wsRef.current.close(); };
  }, []);

  const sendCommand = async (body) => {
    try { await axios.post(`${API}/device/plc-01/command`, body); } catch (e) { /* noop */ }
  };

  const togglePlc = () => sendCommand({ type: "plc_run", value: !state?.running });
  const toggleOutput = (target, index, current) =>
    sendCommand({ type: "set_output", target, index, value: !current });
  const writeRegister = (index) => {
    const v = parseInt(regInputs[index], 10);
    if (!Number.isNaN(v)) sendCommand({ type: "set_register", index, value: v });
  };
  const toggleSim = async () => {
    const { data } = await axios.post(`${API}/simulator/toggle?enable=${!simOn}`);
    setSimOn(data.simulator_enabled);
  };

  const filtered = events.filter((e) => logFilter === "all" || e.level === logFilter);
  const running = state?.running;

  return (
    <div className="app-shell">
      <div style={{ maxWidth: 1280, margin: "0 auto", padding: "28px 20px 60px" }}>
        {/* Header */}
        <header className="flex items-start justify-between flex-wrap gap-4 mb-7">
          <div className="flex items-center gap-3">
            <div className="panel" style={{ padding: 12 }}>
              <CircuitBoard size={28} color="#007AFF" />
            </div>
            <div>
              <h1 className="font-head" data-testid="app-title"
                  style={{ fontSize: 30, fontWeight: 700, margin: 0, lineHeight: 1 }}>
                {t.title}
              </h1>
              <p style={{ color: "var(--muted)", fontSize: 12, margin: "6px 0 0" }}>{t.subtitle}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <div className="panel flex" style={{ overflow: "hidden" }}>
              {["pl", "en"].map((l) => (
                <button key={l} data-testid={`lang-${l}`} onClick={() => setLang(l)}
                  className="font-head"
                  style={{
                    background: lang === l ? "var(--primary)" : "transparent",
                    color: lang === l ? "#fff" : "var(--muted)",
                    border: "none", padding: "10px 14px", cursor: "pointer",
                    fontSize: 14, fontWeight: 600, display: "flex", alignItems: "center", gap: 6,
                  }}>
                  {l === "pl" ? <Languages size={14} /> : null}{l.toUpperCase()}
                </button>
              ))}
            </div>
          </div>
        </header>

        {/* Status bar */}
        <div className="grid gap-3 mb-6" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))" }}>
          <StatusChip testid="status-broker" ok={brokerConnected}
            label={brokerConnected ? t.brokerConnected : t.brokerDisconnected} />
          <StatusChip testid="status-device" ok={online}
            label={online ? t.deviceOnline : t.deviceOffline} />
          <StatusChip testid="status-ws" ok={wsUp}
            label={wsUp ? "WebSocket" : t.connecting} />
          <div className="panel flex items-center justify-between" style={{ padding: "12px 16px" }}>
            <span className="flex items-center gap-2" style={{ color: "var(--muted)", fontSize: 12 }}>
              <Radio size={14} /> {t.simulator}
            </span>
            <button data-testid="sim-toggle" onClick={toggleSim} className="font-head"
              style={{
                background: simOn ? "rgba(48,209,88,0.15)" : "#1a1a1a",
                color: simOn ? "var(--green)" : "var(--muted)",
                border: `1px solid ${simOn ? "var(--green)" : "var(--border)"}`,
                borderRadius: 6, padding: "4px 12px", cursor: "pointer", fontWeight: 700, fontSize: 13,
              }}>
              {simOn ? t.on : t.off}
            </button>
          </div>
        </div>

        <div className="grid gap-5" style={{ gridTemplateColumns: "minmax(0,2fr) minmax(0,1fr)" }}>
          {/* Left column */}
          <div className="grid gap-5" style={{ gridAutoRows: "min-content" }}>
            {/* PLC master */}
            <div className="panel panel-pad flex items-center justify-between flex-wrap gap-4">
              <div className="flex items-center gap-4">
                <Cpu size={36} color={running ? "#30D158" : "#8E8E93"} className={running ? "pulse" : ""} />
                <div>
                  <div style={{ color: "var(--muted)", fontSize: 11 }}>{state?.model || "Fatek FBs"}</div>
                  <div className="font-head" data-testid="plc-run-state"
                    style={{ fontSize: 26, fontWeight: 700, color: running ? "var(--green)" : "var(--muted)" }}>
                    {running ? t.running : t.stopped}
                  </div>
                </div>
              </div>
              <button data-testid="plc-power-btn" onClick={togglePlc} className="font-head flex items-center gap-2"
                style={{
                  background: running ? "rgba(255,59,48,0.14)" : "rgba(48,209,88,0.14)",
                  color: running ? "var(--accent)" : "var(--green)",
                  border: `1px solid ${running ? "var(--accent)" : "var(--green)"}`,
                  borderRadius: 10, padding: "12px 26px", cursor: "pointer", fontSize: 17, fontWeight: 700,
                }}>
                <Power size={18} /> {running ? t.stop : t.start}
              </button>
            </div>

            {/* Inputs X */}
            <Panel title={t.inputs} hint={t.inputsHint} icon={<Activity size={18} />}>
              <div className="grid gap-2" style={{ gridTemplateColumns: "repeat(8, 1fr)" }}>
                {(state?.x || Array(8).fill(false)).map((v, i) => (
                  <IODot key={i} testid={`input-x-${i}`} label={`X${i}`} on={v} kind="X" />
                ))}
              </div>
            </Panel>

            {/* Outputs Y */}
            <Panel title={t.outputs} hint={t.outputsHint} icon={<Zap size={18} />}>
              <div className="grid gap-2" style={{ gridTemplateColumns: "repeat(8, 1fr)" }}>
                {(state?.y || Array(8).fill(false)).map((v, i) => (
                  <IODot key={i} testid={`output-y-${i}`} label={`Y${i}`} on={v} kind="Y"
                    onClick={() => toggleOutput("Y", i, v)} />
                ))}
              </div>
            </Panel>

            {/* Relays M */}
            <Panel title={t.relays} hint={t.relaysHint} icon={<CircuitBoard size={18} />}>
              <div className="grid gap-2" style={{ gridTemplateColumns: "repeat(8, 1fr)" }}>
                {(state?.m || Array(8).fill(false)).map((v, i) => (
                  <IODot key={i} testid={`relay-m-${i}`} label={`M${i}`} on={v} kind="M"
                    onClick={() => toggleOutput("M", i, v)} />
                ))}
              </div>
            </Panel>

            {/* Registers R */}
            <Panel title={t.registers} icon={<Settings2 size={18} />}>
              <div className="grid gap-3" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))" }}>
                {(state?.r || Array(6).fill(0)).map((v, i) => (
                  <div key={i} className="reg-cell">
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-head" style={{ fontWeight: 700 }}>R{i}</span>
                      <span data-testid={`reg-value-${i}`} style={{ color: "var(--primary)", fontSize: 18, fontWeight: 700 }}>{v}</span>
                    </div>
                    <div className="flex gap-2">
                      <input className="app-input" data-testid={`reg-input-${i}`}
                        placeholder={t.value} value={regInputs[i] ?? ""}
                        onChange={(e) => setRegInputs((p) => ({ ...p, [i]: e.target.value }))}
                        style={{ fontSize: 12, padding: "6px 8px" }} />
                      <button data-testid={`reg-write-${i}`} onClick={() => writeRegister(i)}
                        style={{
                          background: "var(--primary)", color: "#fff", border: "none",
                          borderRadius: 6, padding: "0 12px", cursor: "pointer", fontSize: 12, fontWeight: 700,
                        }}>→</button>
                    </div>
                  </div>
                ))}
              </div>
            </Panel>
          </div>

          {/* Right column */}
          <div className="grid gap-5" style={{ gridAutoRows: "min-content" }}>
            {/* Broker settings */}
            {config && (
              <Panel title={t.settings} icon={<Radio size={18} />}>
                <Row k={t.host} v={config.broker_host} testid="cfg-host" />
                <Row k={t.port} v={config.broker_port} testid="cfg-port" />
                <Row k={t.prefix} v={config.prefix} testid="cfg-prefix" />
                <Row k={t.stateTopic} v={config.state_topic} small testid="cfg-state-topic" />
                <Row k={t.commandTopic} v={config.command_topic} small testid="cfg-command-topic" />
              </Panel>
            )}

            {/* Event log */}
            <Panel title={t.eventLog} icon={<ScrollText size={18} />}>
              <div className="flex gap-1 mb-3 flex-wrap">
                {[["all", t.allLevels], ["info", t.levelInfo], ["command", t.levelCommand], ["warning", t.levelWarning]].map(([k, label]) => (
                  <button key={k} data-testid={`log-filter-${k}`} onClick={() => setLogFilter(k)}
                    style={{
                      background: logFilter === k ? "var(--primary)" : "#1a1a1a",
                      color: logFilter === k ? "#fff" : "var(--muted)",
                      border: "1px solid var(--border)", borderRadius: 6,
                      padding: "4px 10px", cursor: "pointer", fontSize: 11, fontWeight: 600,
                    }}>{label}</button>
                ))}
              </div>
              <div data-testid="event-log" style={{ maxHeight: 440, overflowY: "auto", display: "flex", flexDirection: "column", gap: 6 }}>
                {filtered.length === 0 && <div style={{ color: "var(--muted)", fontSize: 12 }}>{t.noEvents}</div>}
                {filtered.map((e, i) => (
                  <div key={i} className={`log-line ${e.level}`} style={{ padding: "6px 10px" }}>
                    <div style={{ fontSize: 12 }}>{e.message}</div>
                    <div style={{ color: "var(--muted)", fontSize: 10 }}>
                      {new Date(e.ts).toLocaleTimeString()}
                    </div>
                  </div>
                ))}
              </div>
            </Panel>
          </div>
        </div>

        {state?.ts && (
          <div style={{ color: "var(--muted)", fontSize: 11, marginTop: 20, textAlign: "center" }}>
            {t.lastUpdate}: {new Date(state.ts).toLocaleTimeString()}
          </div>
        )}
      </div>
    </div>
  );
}

function StatusChip({ ok, label, testid }) {
  return (
    <div className="panel flex items-center gap-3" data-testid={testid} style={{ padding: "12px 16px" }}>
      <span className={`led ${ok ? "ok" : "warn"} ${ok ? "" : "pulse"}`} />
      <span style={{ fontSize: 13 }}>{label}</span>
    </div>
  );
}

function Row({ k, v, small, testid }) {
  return (
    <div className="flex items-center justify-between" style={{ padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
      <span style={{ color: "var(--muted)", fontSize: 12 }}>{k}</span>
      <span data-testid={testid} style={{ fontSize: small ? 11 : 13, color: "var(--text)", textAlign: "right", wordBreak: "break-all", maxWidth: "62%" }}>{v}</span>
    </div>
  );
}

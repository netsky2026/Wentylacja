import { useEffect, useRef, useState, useCallback } from "react";
import axios from "axios";
import { Toaster, toast } from "sonner";
import { I18N } from "@/i18n";
import { API, refreshSession, setOnAuthLost } from "@/api";
import { LoginScreen } from "@/components/LoginScreen";
import { ChamberScreen } from "@/components/ChamberScreen";
import { DataView } from "@/components/DataView";
import { SettingsView } from "@/components/SettingsView";
import { BottomNav, ChamberSwitch } from "@/components/BottomNav";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

export default function App() {
  const [lang, setLang] = useState(() => localStorage.getItem("lang") || "pl");
  const [user, setUser] = useState(null);
  const t = I18N[lang];
  const changeLang = (l) => { setLang(l); localStorage.setItem("lang", l); };
  useEffect(() => {
    setOnAuthLost(() => setUser(false));
    axios.get(`${API}/auth/me`).then(({ data }) => setUser(data))
      .catch(() => refreshSession().then(({ data }) => setUser(data)).catch(() => setUser(false)));
  }, []);
  const logout = async () => {
    try { await axios.post(`${API}/auth/logout`); } catch (e) { /* noop */ }
    setUser(false);
  };
  if (user === null) return <div className="app-shell" data-testid="auth-loading" />;
  if (user === false) {
    return <><LoginScreen t={t} onLogin={setUser} lang={lang} setLang={changeLang} /><Toaster theme="dark" position="top-center" /></>;
  }
  return <Dashboard t={t} lang={lang} setLang={changeLang} user={user} onLogout={logout} />;
}

function Dashboard({ t, lang, setLang, user, onLogout }) {
  const canControl = user.role === "operator" || user.role === "admin";
  const [view, setView] = useState("chambers");
  const [selected, setSelected] = useState(0);
  const [state, setState] = useState(null);
  const [online, setOnline] = useState(false);
  const [brokerConnected, setBrokerConnected] = useState(false);
  const [simOn, setSimOn] = useState(true);
  const [config, setConfig] = useState(null);
  const [events, setEvents] = useState([]);
  const [history, setHistory] = useState({});
  const [plantHistory, setPlantHistory] = useState([]);
  const [thresholds, setThresholds] = useState([]);
  const [notifPerm, setNotifPerm] = useState(typeof Notification !== "undefined" ? Notification.permission : "unsupported");
  const wsRef = useRef(null);

  const loadHealth = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/health`);
      setBrokerConnected(data.broker_connected);
      setOnline(data.device_online);
      setSimOn(data.simulator_enabled);
    } catch (e) { /* noop */ }
  }, []);

  const loadHistory = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/history?hours=3`);
      setHistory(data.history || {});
      setPlantHistory(data.plant || []);
    } catch (e) { /* noop */ }
  }, []);

  const loadThresholds = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/thresholds`);
      setThresholds(data.thresholds || []);
    } catch (e) { /* noop */ }
  }, []);

  const saveThreshold = useCallback(async (chamber, temp_max, co2_max) => {
    await axios.put(`${API}/thresholds/${chamber}`, { temp_max, co2_max });
    loadThresholds();
  }, [loadThresholds]);

  const requestNotif = useCallback(async () => {
    if (typeof Notification === "undefined") return;
    setNotifPerm(await Notification.requestPermission());
  }, []);

  useEffect(() => {
    axios.get(`${API}/config`).then(({ data }) => setConfig(data));
    axios.get(`${API}/events?limit=50`).then(({ data }) => setEvents(data.events || []));
    loadHealth();
    loadHistory();
    loadThresholds();
    const hi = setInterval(loadHealth, 3000);
    const hh = setInterval(loadHistory, 15000);
    return () => { clearInterval(hi); clearInterval(hh); };
  }, [loadHealth, loadHistory, loadThresholds]);

  useEffect(() => {
    const wsUrl = `${BACKEND_URL.replace(/^http/, "ws")}/api/ws`;
    let stop = false;
    const connect = () => {
      if (stop) return;
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;
      ws.onclose = () => {
        if (stop) return;
        refreshSession().catch(() => {}).finally(() => setTimeout(connect, 2000));
      };
      ws.onmessage = (e) => {
        const msg = JSON.parse(e.data);
        if (msg.type === "state") { setState(msg.payload); setOnline(true); }
        else if (msg.type === "event") setEvents((p) => [msg.event, ...p].slice(0, 50));
        else if (msg.type === "alarm" && typeof Notification !== "undefined" && Notification.permission === "granted") {
          try { new Notification(msg.title, { body: msg.body }); } catch (err) { /* noop */ }
        }
      };
    };
    connect();
    return () => { stop = true; if (wsRef.current) wsRef.current.close(); };
  }, []);

  const send = async (body) => {
    try { await axios.post(`${API}/device/${config?.device_id || "chlodnia-01"}/command`, body); }
    catch (e) { toast.error(t.cmdFailed); }
  };
  const toggleSim = async () => {
    const { data } = await axios.post(`${API}/simulator/toggle?enable=${!simOn}`);
    setSimOn(data.simulator_enabled);
  };

  const chambers = state?.chambers || [];
  const ch = chambers.find((c) => c.id === selected);

  return (
    <div className="app-shell">
      <div className="mobile-wrap">
        <header className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <img src="/icon-192.png" alt="" data-testid="app-logo" style={{ width: 28, height: 28, borderRadius: 7 }} />
            <span className="font-head" data-testid="app-title" style={{ fontSize: 20, fontWeight: 700 }}>{t.appName}</span>
          </div>
          <div className="panel flex" style={{ overflow: "hidden" }}>
            {["pl", "en"].map((l) => (
              <button key={l} data-testid={`lang-${l}`} onClick={() => setLang(l)} className="font-head"
                style={{
                  background: lang === l ? "#2a2f35" : "transparent", color: lang === l ? "var(--text)" : "var(--muted)",
                  border: "none", padding: "7px 11px", cursor: "pointer", fontSize: 13, fontWeight: 700,
                }}>{l.toUpperCase()}</button>
            ))}
          </div>
        </header>

        <div className="panel flex items-center justify-between mb-3" data-testid="status-bar" style={{ padding: "9px 14px" }}>
          <span className="flex items-center gap-2" style={{ fontSize: 12 }}>
            <span className={`led ${brokerConnected ? "ok" : "warn pulse"}`} />
            {brokerConnected ? t.brokerConnected : t.brokerDisconnected}
          </span>
          <span className="flex items-center gap-2" style={{ fontSize: 12, color: online ? "var(--green)" : "var(--muted)" }}>
            <span className={`led ${online ? "ok" : "warn"}`} />
            {online ? t.deviceOnline : t.deviceOffline}
          </span>
        </div>

        {view !== "settings" && chambers.length > 0 && (
          <ChamberSwitch chambers={chambers} selected={selected} setSelected={setSelected} t={t} />
        )}

        {chambers.length === 0 ? (
          <div className="panel panel-pad" style={{ color: "var(--muted)", textAlign: "center" }}>…</div>
        ) : view === "chambers" ? (
          ch && <ChamberScreen key={ch.id} ch={ch} t={t} send={send} canControl={canControl} />
        ) : view === "data" ? (
          <DataView t={t} ch={ch} plant={state?.plant} history={history} plantHistory={plantHistory} events={events} />
        ) : (
          <SettingsView t={t} chambers={chambers} thresholds={thresholds} send={send} saveThreshold={saveThreshold}
            notifPerm={notifPerm} requestNotif={requestNotif} simOn={simOn} toggleSim={toggleSim} config={config} onConfigSaved={setConfig}
            user={user} onLogout={onLogout} canControl={canControl} />
        )}
      </div>
      <BottomNav view={view} setView={setView} t={t} />
      <Toaster theme="dark" position="top-center" />
    </div>
  );
}

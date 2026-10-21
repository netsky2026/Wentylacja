import { useEffect, useRef, useState, useCallback } from "react";
import axios from "axios";
import { Toaster, toast } from "sonner";
import { I18N } from "@/i18n";
import { API, refreshSession, setOnAuthLost, siteLogoUrl } from "@/api";
import { LoginScreen } from "@/components/LoginScreen";
import { WelcomeScreen } from "@/components/WelcomeScreen";
import { OverviewView } from "@/components/OverviewView";
import { ChamberScreen } from "@/components/ChamberScreen";
import { DataView } from "@/components/DataView";
import { SettingsView } from "@/components/SettingsView";
import { BottomNav, ChamberSwitch, DevicePicker } from "@/components/BottomNav";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
document.documentElement.dataset.theme = localStorage.getItem("theme") || "green";
const urlSlug = new URLSearchParams(window.location.search).get("klient");
if (urlSlug && /^[a-z0-9][a-z0-9-]{1,39}$/.test(urlSlug)) localStorage.setItem("brand_slug", urlSlug);

const setHeadLink = (sel, attr, val) => { const el = document.querySelector(sel); if (el) el.setAttribute(attr, val); };

const usePublicBrand = () => {
  const [pb, setPb] = useState(null);
  useEffect(() => {
    const slug = localStorage.getItem("brand_slug");
    if (!slug) return;
    axios.get(`${API}/public/branding/${slug}`).then(({ data }) => {
      setPb(data);
      setHeadLink('link[rel="manifest"]', "href", `${API}/public/manifest/${slug}`);
      if (data.logo_version) setHeadLink('link[rel="apple-touch-icon"]', "href", `${API}/public/logo/${slug}?size=180&v=${data.logo_version}`);
      if (data.app_name) {
        document.title = data.app_name;
        setHeadLink('meta[name="apple-mobile-web-app-title"]', "content", data.app_name);
      }
    }).catch(() => localStorage.removeItem("brand_slug"));
  }, []);
  return pb;
};

const useSite = () => {
  const [site, setSite] = useState(null);
  const load = useCallback(() => axios.get(`${API}/public/site`).then(({ data }) => {
    setSite(data);
    if (localStorage.getItem("brand_slug") || !data.logo_version) return;
    setHeadLink('link[rel="manifest"]', "href", `${API}/public/manifest?v=${data.logo_version}`);
    setHeadLink('link[rel="apple-touch-icon"]', "href", siteLogoUrl(data, 180));
    setHeadLink('link[rel="icon"]', "href", siteLogoUrl(data, 32));
  }).catch(() => {}), []);
  useEffect(() => { load(); }, [load]);
  return [site, load];
};

export default function App() {
  const [lang, setLang] = useState(() => localStorage.getItem("lang") || "pl");
  const [user, setUser] = useState(null);
  const [showLogin, setShowLogin] = useState(false);
  const publicBrand = usePublicBrand();
  const [site, reloadSite] = useSite();
  const t = I18N[lang];
  const changeLang = (l) => { setLang(l); localStorage.setItem("lang", l); };
  useEffect(() => {
    setOnAuthLost(() => setUser(false));
    axios.get(`${API}/auth/me`).then(({ data }) => setUser(data))
      .catch(() => refreshSession().then(({ data }) => setUser(data)).catch(() => setUser(false)));
  }, []);
  const logout = async () => {
    try { await axios.post(`${API}/auth/logout`); } catch (e) { /* noop */ }
    setShowLogin(true);
    setUser(false);
  };
  if (user === null) return <div className="app-shell" data-testid="auth-loading" />;
  if (user === false && !showLogin && !localStorage.getItem("brand_slug")) {
    return <WelcomeScreen t={t} site={site} lang={lang} setLang={changeLang} onLogin={() => setShowLogin(true)} />;
  }
  if (user === false) {
    return <><LoginScreen t={t} onLogin={setUser} lang={lang} setLang={changeLang} brand={publicBrand} site={site}
      onBack={localStorage.getItem("brand_slug") ? undefined : () => setShowLogin(false)} /><Toaster theme="dark" position="top-center" /></>;
  }
  return <Dashboard t={t} lang={lang} setLang={changeLang} user={user} onLogout={logout} onUserChange={setUser} site={site} reloadSite={reloadSite} />;
}

function Dashboard({ t, lang, setLang, user, onLogout, onUserChange, site, reloadSite }) {
  const [brand, setBrand] = useState({ client_id: null, app_name: null, theme: null, logo_version: null, loaded: false });
  const canControl = ["operator", "admin", "superadmin"].includes(user.role);
  const [view, setView] = useState("chambers");
  const [devices, setDevices] = useState(null);
  const [deviceId, setDeviceId] = useState(() => localStorage.getItem("device") || "");
  const [selected, setSelected] = useState(0);
  const [states, setStates] = useState({});
  const [brokerConnected, setBrokerConnected] = useState(false);
  const [config, setConfig] = useState(null);
  const [events, setEvents] = useState([]);
  const [history, setHistory] = useState({});
  const [plantHistory, setPlantHistory] = useState([]);
  const [thresholds, setThresholds] = useState([]);
  const [notifPerm, setNotifPerm] = useState(typeof Notification !== "undefined" ? Notification.permission : "unsupported");
  const wsRef = useRef(null);

  const loadDevices = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/devices`);
      setDevices(data.devices);
      setStates((p) => {
        const n = { ...p };
        data.devices.forEach((d) => { if (d.state) n[d.device_id] = d.state; });
        return n;
      });
      setBrokerConnected((await axios.get(`${API}/health`)).data.broker_connected);
    } catch (e) { /* noop */ }
  }, []);

  const dev = devices?.find((d) => d.device_id === deviceId) || devices?.find((d) => d.online) || devices?.[0];
  useEffect(() => {
    if (devices && deviceId && !devices.some((d) => d.device_id === deviceId)) localStorage.removeItem("device");
  }, [devices, deviceId]);
  const devId = dev?.device_id;

  const loadHistory = useCallback(async () => {
    if (!devId) return;
    try {
      const { data } = await axios.get(`${API}/devices/${devId}/history?hours=3`);
      setHistory(data.history || {});
      setPlantHistory(data.plant || []);
    } catch (e) { /* noop */ }
  }, [devId]);

  const loadThresholds = useCallback(async () => {
    if (!devId) return;
    try { setThresholds((await axios.get(`${API}/devices/${devId}/thresholds`)).data.thresholds || []); } catch (e) { /* noop */ }
  }, [devId]);

  const saveThreshold = useCallback(async (chamber, temp_max, co2_max) => {
    await axios.put(`${API}/devices/${devId}/thresholds/${chamber}`, { temp_max, co2_max });
    loadThresholds();
  }, [devId, loadThresholds]);

  const requestNotif = useCallback(async () => {
    if (typeof Notification === "undefined") return;
    setNotifPerm(await Notification.requestPermission());
  }, []);

  useEffect(() => {
    axios.get(`${API}/config`).then(({ data }) => setConfig(data)).catch(() => {});
    loadDevices();
    const i = setInterval(loadDevices, 5000);
    return () => clearInterval(i);
  }, [loadDevices]);

  useEffect(() => {
    if (!devId) return undefined;
    setHistory({}); setPlantHistory([]);
    loadHistory();
    loadThresholds();
    axios.get(`${API}/events?limit=50&device_id=${devId}`).then(({ data }) => setEvents(data.events || [])).catch(() => {});
    const hh = setInterval(loadHistory, 15000);
    return () => clearInterval(hh);
  }, [devId, loadHistory, loadThresholds]);

  const brandClient = user.role === "superadmin" ? dev?.client_id : user.client_id;
  const loadBrand = useCallback(() => {
    if (user.role === "superadmin" && !brandClient) return;
    const q = user.role === "superadmin" && brandClient ? `?client_id=${brandClient}` : "";
    axios.get(`${API}/branding${q}`).then(({ data }) => setBrand({ ...data, loaded: true })).catch(() => {});
  }, [user.role, brandClient]);
  useEffect(() => { loadBrand(); }, [loadBrand]);
  const theme = user.theme || brand.theme || (brand.loaded ? "green" : localStorage.getItem("theme") || "green");
  useEffect(() => {
    if (!user.theme && !brand.loaded) return;
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("theme", theme);
    if (user.theme) localStorage.setItem("theme_user", "1"); else localStorage.removeItem("theme_user");
    const bg = getComputedStyle(document.documentElement).getPropertyValue("--bg").trim();
    document.querySelector('meta[name="theme-color"]')?.setAttribute("content", bg);
  }, [theme, user.theme, brand.loaded]);

  const devRef = useRef(devId);
  devRef.current = devId;
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
        if (msg.type === "state") setStates((p) => ({ ...p, [msg.payload.device_id]: msg.payload }));
        else if (msg.type === "event") {
          const ev = msg.event;
          if (!ev.device_id || ev.device_id === devRef.current) setEvents((p) => [ev, ...p].slice(0, 50));
        } else if (msg.type === "alarm" && typeof Notification !== "undefined" && Notification.permission === "granted") {
          try { new Notification(msg.title, { body: msg.body }); } catch (err) { /* noop */ }
        }
      };
    };
    connect();
    return () => { stop = true; if (wsRef.current) wsRef.current.close(); };
  }, []);

  const pickDevice = (id) => { setDeviceId(id); localStorage.setItem("device", id); setSelected(0); };
  const send = async (body) => {
    try { await axios.post(`${API}/devices/${devId}/command`, body); }
    catch (e) { toast.error(t.cmdFailed); }
  };

  const state = devId ? states[devId] : null;
  const chambers = state?.chambers || [];
  const ch = chambers.find((c) => c.id === selected) || chambers[0];
  const online = dev?.online;

  return (
    <div className="app-shell">
      <div className="mobile-wrap">
        <header className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2" style={{ minWidth: 0 }}>
            <img src={brand.logo_version ? `${API}/clients/${brand.client_id}/logo?v=${brand.logo_version}` : siteLogoUrl(site)}
              alt="" data-testid="app-logo" style={{ width: 28, height: 28, borderRadius: 7, objectFit: "contain" }} />
            <span className="font-head" data-testid="app-title" style={{ fontSize: 20, fontWeight: 700, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
              {brand.app_name || t.appName}</span>
          </div>
          <div className="panel flex" style={{ overflow: "hidden", flexShrink: 0 }}>
            {["pl", "en"].map((l) => (
              <button key={l} data-testid={`lang-${l}`} onClick={() => setLang(l)} className="font-head"
                style={{
                  background: lang === l ? "rgba(var(--primary-rgb),0.16)" : "transparent", color: lang === l ? "var(--primary)" : "var(--muted)",
                  border: "none", padding: "7px 11px", cursor: "pointer", fontSize: 13, fontWeight: 700,
                }}>{l.toUpperCase()}</button>
            ))}
          </div>
        </header>

        {devices && devices.length > 0 && view !== "overview" && (
          <DevicePicker devices={devices} value={devId} onChange={pickDevice} t={t} states={states} />
        )}

        {view !== "overview" && <div className="panel flex items-center justify-between mb-3" data-testid="status-bar" style={{ padding: "9px 14px" }}>
          <span className="flex items-center gap-2" style={{ fontSize: 12 }}>
            <span className={`led ${brokerConnected ? "ok" : "warn pulse"}`} />
            {brokerConnected ? t.brokerConnected : t.brokerDisconnected}
          </span>
          <span className="flex items-center gap-2" data-testid="device-online" style={{ fontSize: 12, color: online ? "var(--green)" : "var(--muted)" }}>
            <span className={`led ${online ? "ok" : "warn"}`} />
            {online ? t.deviceOnline : t.deviceOffline}
          </span>
        </div>}

        {(view === "chambers" || view === "data") && chambers.length > 0 && (
          <ChamberSwitch chambers={chambers} selected={ch?.id} setSelected={setSelected} t={t} />
        )}

        {devices && devices.length === 0 && view !== "settings" ? (
          <div className="panel panel-pad" data-testid="no-devices" style={{ color: "var(--muted)", textAlign: "center", fontSize: 13 }}>{t.noDevices}</div>
        ) : view === "overview" && devices ? (
          <OverviewView t={t} devices={devices} states={states} onOpen={(id) => { pickDevice(id); setView("chambers"); }} />
        ) : view === "settings" ? (
          <SettingsView t={t} chambers={chambers} thresholds={thresholds} send={send} saveThreshold={saveThreshold}
            notifPerm={notifPerm} requestNotif={requestNotif} config={config} onConfigSaved={setConfig}
            user={user} onLogout={onLogout} canControl={canControl} dev={dev} reloadDevices={() => { loadDevices(); loadBrand(); }}
            onUserChange={onUserChange} clientTheme={brand.theme} site={site} reloadSite={reloadSite} />
        ) : chambers.length === 0 ? (
          <div className="panel panel-pad" style={{ color: "var(--muted)", textAlign: "center", fontSize: 13 }}>{dev ? t.waitingData : "…"}</div>
        ) : view === "chambers" ? (
          ch && <ChamberScreen key={`${devId}-${ch.id}`} ch={ch} t={t} send={send} canControl={canControl} />
        ) : (
          <DataView t={t} ch={ch} deviceId={devId} plant={state?.plant} history={history} plantHistory={plantHistory} events={events} />
        )}
      </div>
      <BottomNav view={view} setView={setView} t={t} showOverview={(devices?.length || 0) > 1} />
      <Toaster theme={theme === "light" ? "light" : "dark"} position="top-center" />
    </div>
  );
}

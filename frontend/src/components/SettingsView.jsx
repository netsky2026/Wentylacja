import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { BrokerForm } from "@/components/BrokerForm";
import { InstallCard } from "@/components/InstallCard";
import { Minus, Plus, Bell, BellOff, Check } from "lucide-react";

const ChamberSettings = ({ ch, th, t, send, saveThreshold }) => {
  const [tmax, setTmax] = useState("");
  const [cmax, setCmax] = useState("");
  const [saved, setSaved] = useState(false);
  useEffect(() => { if (th) { setTmax(String(th.temp_max)); setCmax(String(th.co2_max)); } }, [th]);
  const save = async () => {
    const a = parseFloat(tmax), b = parseFloat(cmax);
    if (!Number.isFinite(a) || !Number.isFinite(b)) { toast.error(t.invalidValue); return; }
    try { await saveThreshold(ch.id, a, b); } catch (e) { toast.error(t.saveFailed); return; }
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };
  const pending = useRef(null);
  useEffect(() => { pending.current = null; }, [ch.setpoint]);
  const sp = (d) => {
    const base = pending.current ?? ch.setpoint;
    const value = Math.max(5, Math.min(35, Math.round((base + d) * 10) / 10));
    pending.current = value;
    send({ type: "set_setpoint", chamber: ch.id, value });
  };
  return (
    <div className="panel panel-pad" data-testid={`settings-chamber-${ch.id}`}>
      <div className="font-head" style={{ fontSize: 17, fontWeight: 700, marginBottom: 10 }}>{t.chamberWord} {ch.id + 1}</div>
      <div className="flex items-center justify-between reg-cell mb-3" style={{ padding: "8px 12px" }}>
        <span style={{ color: "var(--muted)", fontSize: 12 }}>{t.setpoint}</span>
        <div className="flex items-center gap-3">
          <button data-testid={`chamber-${ch.id}-sp-down`} className="sp-btn" onClick={() => sp(-0.5)}><Minus size={16} /></button>
          <span className="font-head" data-testid={`settings-chamber-${ch.id}-setpoint`} style={{ fontSize: 20, fontWeight: 700, minWidth: 64, textAlign: "center" }}>
            {ch.setpoint?.toFixed(1)}°C
          </span>
          <button data-testid={`chamber-${ch.id}-sp-up`} className="sp-btn" onClick={() => sp(0.5)}><Plus size={16} /></button>
        </div>
      </div>
      <div className="grid gap-2 mb-3" style={{ gridTemplateColumns: "1fr 1fr" }}>
        <label className="flex flex-col" style={{ gap: 4, fontSize: 11, color: "var(--muted)" }}>{t.tempMax}
          <input type="number" step="0.5" className="num-input" data-testid={`threshold-${ch.id}-temp`} value={tmax} onChange={(e) => setTmax(e.target.value)} />
        </label>
        <label className="flex flex-col" style={{ gap: 4, fontSize: 11, color: "var(--muted)" }}>{t.co2Max}
          <input type="number" step="100" className="num-input" data-testid={`threshold-${ch.id}-co2`} value={cmax} onChange={(e) => setCmax(e.target.value)} />
        </label>
      </div>
      <button className="action-btn" data-testid={`threshold-${ch.id}-save`} onClick={save} style={{ width: "100%", padding: 10 }}>
        {saved ? <><Check size={15} /> {t.saved}</> : t.save}
      </button>
    </div>
  );
};


export const SettingsView = ({ t, chambers, thresholds, send, saveThreshold, notifPerm, requestNotif, simOn, toggleSim, config, onConfigSaved }) => (
  <div className="fade-in" style={{ display: "flex", flexDirection: "column", gap: 12 }} data-testid="settings-view">
    <div className="font-head" style={{ fontSize: 13, color: "var(--muted)" }}>{t.thresholds} / {t.setpoint}</div>
    {chambers.map((ch) => (
      <ChamberSettings key={ch.id} ch={ch} t={t} send={send} saveThreshold={saveThreshold}
        th={thresholds.find((x) => x.chamber === ch.id)} />
    ))}

    <div className="panel flex items-center justify-between" style={{ padding: "12px 16px" }}>
      <span className="flex items-center gap-2" style={{ fontSize: 13 }}>
        {notifPerm === "granted" ? <Bell size={15} /> : <BellOff size={15} />} {t.notifications}
      </span>
      {notifPerm === "granted" ? <span data-testid="notif-status" style={{ fontSize: 12, color: "var(--green)" }}>{t.notifOn}</span>
        : notifPerm === "denied" ? <span data-testid="notif-status" style={{ fontSize: 12, color: "var(--accent)" }}>{t.notifBlocked}</span>
        : notifPerm === "unsupported" ? <span data-testid="notif-status" style={{ fontSize: 12, color: "var(--muted)" }}>{t.notifUnsupported}</span>
        : <button data-testid="notif-enable" className="action-btn" onClick={requestNotif} style={{ padding: "6px 12px", fontSize: 12 }}>{t.enableNotif}</button>}
    </div>

    <div className="panel flex items-center justify-between" style={{ padding: "12px 16px" }}>
      <span style={{ fontSize: 13 }}>{t.simulator}</span>
      <button data-testid="sim-toggle" onClick={toggleSim} className="font-head"
        style={{
          background: simOn ? "rgba(48,209,88,0.15)" : "#1a1a1a", color: simOn ? "var(--green)" : "var(--muted)",
          border: `1px solid ${simOn ? "var(--green)" : "var(--border)"}`, borderRadius: 6, padding: "4px 14px",
          cursor: "pointer", fontWeight: 700, fontSize: 13,
        }}>{simOn ? t.on : t.off}</button>
    </div>

    <BrokerForm t={t} config={config} onSaved={onConfigSaved} />
    <InstallCard t={t} />
  </div>
);

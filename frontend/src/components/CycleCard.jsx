import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { PiggyBank, Plus, Square, History } from "lucide-react";
import { API } from "@/api";

const today = () => new Date().toLocaleDateString("sv-SE", { timeZone: "Europe/Warsaw" });
const m3 = (l) => (l / 1000).toFixed(2);

const StartForm = ({ t, onStart, onCancel }) => {
  const [start, setStart] = useState(today());
  const [animals, setAnimals] = useState("");
  return (
    <div className="grid gap-2" style={{ gridTemplateColumns: "1fr 1fr" }}>
      <input type="date" className="num-input" value={start} max={today()} onChange={(e) => setStart(e.target.value)} data-testid="cycle-start-date" style={{ fontSize: 14 }} />
      <input type="number" min="0" className="num-input" placeholder={t.cycleAnimals} value={animals} onChange={(e) => setAnimals(e.target.value)} data-testid="cycle-animals" style={{ fontSize: 14 }} />
      <button className="action-btn" onClick={onCancel} data-testid="cycle-start-cancel" style={{ padding: 9, fontSize: 13 }}>{t.cancel}</button>
      <button className="action-btn" onClick={() => onStart(start, animals)} data-testid="cycle-start-save"
        style={{ padding: 9, fontSize: 13, background: "var(--primary)", borderColor: "var(--primary)", color: "var(--on-primary)", fontWeight: 700 }}>{t.save}</button>
    </div>
  );
};

const Past = ({ t, rows }) => (
  <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 6 }} data-testid="cycle-history">
    {rows.length === 0 && <div style={{ fontSize: 12, color: "var(--muted)" }}>{t.cycleNoHistory}</div>}
    {rows.map((c) => (
      <div key={c.id} className="reg-cell" style={{ padding: "8px 10px", fontSize: 12 }} data-testid={`cycle-row-${c.id}`}>
        <div style={{ fontWeight: 700 }}>{c.start} – {c.end} · {c.days} {t.cycleDays}{c.animals != null ? ` · ${c.animals} ${t.cyclePcs}` : ""}</div>
        <div style={{ color: "var(--muted)" }}>{t.water}: {m3(c.water_l)} m³ · {t.powerPlant}: {c.kwh} kWh</div>
        <div style={{ color: "var(--muted)", fontSize: 10 }}>{c.started_by}{c.ended_by && c.ended_by !== c.started_by ? ` / ${c.ended_by}` : ""}</div>
      </div>
    ))}
  </div>
);

export const CycleCard = ({ t, ch, deviceId, canEdit }) => {
  const [rows, setRows] = useState([]);
  const [form, setForm] = useState(false);
  const [hist, setHist] = useState(false);
  const load = useCallback(() => axios.get(`${API}/devices/${deviceId}/cycles?chamber=${ch.id}`).then(({ data }) => setRows(data.cycles)).catch(() => {}), [deviceId, ch.id]);
  useEffect(() => { load(); const i = setInterval(load, 60000); return () => clearInterval(i); }, [load]);
  const active = rows.find((c) => !c.end);
  const start = async (date, animals) => {
    try {
      await axios.post(`${API}/devices/${deviceId}/chambers/${ch.id}/cycles`, { start: date, animals: animals === "" ? null : Number(animals) });
      setForm(false); load(); toast.success(t.saved);
    } catch (e) { toast.error(e.response?.status === 409 ? t.cycleActiveExists : t.saveFailed); }
  };
  const end = async () => {
    if (!window.confirm(t.cycleEndConfirm)) return;
    try { await axios.post(`${API}/devices/${deviceId}/cycles/${active.id}/end`, {}); load(); toast.success(t.saved); }
    catch (e) { toast.error(t.saveFailed); }
  };
  return (
    <div className="reg-cell mb-3" data-testid={`chamber-${ch.id}-cycle`}>
      <div className="flex items-center gap-1 mb-2" style={{ color: "var(--muted)", fontSize: 11 }}><PiggyBank size={12} /> {t.cycleTitle}
        {ch.water_lpm != null && <span style={{ marginLeft: "auto" }} data-testid={`chamber-${ch.id}-water-flow`}>{t.water}: {ch.water_lpm.toFixed(1)} l/min</span>}
      </div>
      {active ? (
        <div data-testid="cycle-active">
          <div className="font-head" style={{ fontSize: 17, fontWeight: 700 }}>{t.cycleSince} {active.start} · {t.cycleDay} {active.days}</div>
          <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 2 }}>
            {active.animals != null && <>{active.animals} {t.cyclePcs} · </>}{t.water}: <b style={{ color: "var(--text)" }} data-testid="cycle-active-water">{m3(active.water_l)} m³</b> · {t.powerPlant}: {active.kwh} kWh</div>
          <div style={{ fontSize: 10, color: "var(--muted)", marginTop: 2 }}>{t.cycleBy} {active.started_by}</div>
        </div>
      ) : !form && <div style={{ fontSize: 12, color: "var(--muted)" }}>{t.cycleNone}</div>}
      {form && <div style={{ marginTop: 8 }}><StartForm t={t} onStart={start} onCancel={() => setForm(false)} /></div>}
      <div className="flex gap-2" style={{ marginTop: 10 }}>
        {canEdit && !form && (active
          ? <button className="action-btn" onClick={end} data-testid="cycle-end" style={{ flex: 1, padding: 9, fontSize: 13, color: "var(--accent)", borderColor: "var(--accent)" }}><Square size={13} /> {t.cycleEnd}</button>
          : <button className="action-btn" onClick={() => setForm(true)} data-testid="cycle-new" style={{ flex: 1, padding: 9, fontSize: 13, color: "var(--primary)", borderColor: "var(--primary)" }}><Plus size={13} /> {t.cycleNew}</button>)}
        <button className="action-btn" onClick={() => setHist(!hist)} data-testid="cycle-history-toggle" style={{ flex: 1, padding: 9, fontSize: 13 }}><History size={13} /> {t.cycleHistory}</button>
      </div>
      {hist && <Past t={t} rows={rows.filter((c) => c.end)} />}
    </div>
  );
};

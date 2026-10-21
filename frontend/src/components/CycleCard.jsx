import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { PiggyBank, Plus, Square, History } from "lucide-react";
import { API } from "@/api";

const today = () => new Date().toLocaleDateString("sv-SE", { timeZone: "Europe/Warsaw" });
const m3 = (l) => (l / 1000).toFixed(2);
const PerHead = ({ t, c, avg }) => {
  if (c.water_per_head_l == null) return null;
  const diff = avg ? Math.round((c.water_per_head_l / avg - 1) * 100) : null;
  return (
    <span data-testid={`cycle-per-head-${c.id}`}> · {t.perHead}: <b style={{ color: "var(--text)" }}>{c.water_per_head_l} l</b>
      {diff != null && <span style={{ color: diff > 10 ? "var(--accent)" : diff < -10 ? "var(--green)" : "var(--muted)" }}> ({diff > 0 ? "+" : ""}{diff}% {t.vsAvg})</span>}
    </span>
  );
};
const avgOf = (rows) => {
  const v = rows.map((c) => c.water_per_head_l).filter((x) => x != null);
  return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null;
};

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

const Past = ({ t, rows }) => (<>
  {avgOf(rows) != null && <div style={{ fontSize: 12, marginTop: 10 }} data-testid="cycle-avg-per-head">{t.avgPerHead}: <b>{avgOf(rows).toFixed(2)} l</b></div>}
  <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 6 }} data-testid="cycle-history">
    {rows.length === 0 && <div style={{ fontSize: 12, color: "var(--muted)" }}>{t.cycleNoHistory}</div>}
    {rows.map((c) => (
      <div key={c.id} className="reg-cell" style={{ padding: "8px 10px", fontSize: 12 }} data-testid={`cycle-row-${c.id}`}>
        <div style={{ fontWeight: 700 }}>{c.start} – {c.end} · {c.days} {t.cycleDays}{c.animals != null ? ` · ${c.animals} ${t.cyclePcs}` : ""}</div>
        <div style={{ color: "var(--muted)" }}>{t.water}: {m3(c.water_l)} m³<PerHead t={t} c={c} avg={avgOf(rows.filter((x) => x.id !== c.id))} /> · {t.powerPlant}: {c.kwh} kWh</div>
        <div style={{ color: "var(--muted)", fontSize: 10 }}>{c.started_by}{c.ended_by && c.ended_by !== c.started_by ? ` / ${c.ended_by}` : ""}</div>
      </div>
    ))}
  </div>
</>);

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
            {active.animals != null && <>{active.animals} {t.cyclePcs} · </>}{t.water}: <b style={{ color: "var(--text)" }} data-testid="cycle-active-water">{m3(active.water_l)} m³</b><PerHead t={t} c={active} avg={avgOf(rows.filter((c) => c.end))} /> · {t.powerPlant}: {active.kwh} kWh</div>
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

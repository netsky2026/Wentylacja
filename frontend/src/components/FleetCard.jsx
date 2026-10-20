import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Building2, Cpu, Plus, Trash2, KeyRound, Copy } from "lucide-react";
import { API, formatApiError } from "@/api";

const Creds = ({ c, t, onClose }) => {
  const text = `Broker: ${c.broker_host}:${c.broker_port}${c.tls ? " (TLS)" : ""}\nLogin: ${c.mqtt_username}\n${t.password}: ${c.mqtt_password}\nState: ${c.state_topic}\nCommand: ${c.command_topic}`;
  return (
    <div className="reg-cell" data-testid="device-credentials" style={{ fontSize: 11, marginTop: 8, whiteSpace: "pre-wrap", wordBreak: "break-all" }}>
      {text}
      <div className="flex gap-2" style={{ marginTop: 8 }}>
        <button className="action-btn" style={{ padding: "5px 10px", fontSize: 11 }} data-testid="credentials-copy"
          onClick={() => { navigator.clipboard?.writeText(text); toast.success(t.copied); }}><Copy size={12} /> {t.copy}</button>
        <button className="action-btn" style={{ padding: "5px 10px", fontSize: 11 }} onClick={onClose} data-testid="credentials-close">OK</button>
      </div>
      <div style={{ color: "var(--muted)", marginTop: 6 }}>{t.credsHint}</div>
    </div>
  );
};

export const FleetCard = ({ t, reloadDevices }) => {
  const [clients, setClients] = useState([]);
  const [devices, setDevices] = useState([]);
  const [clientName, setClientName] = useState("");
  const [f, setF] = useState({ client_id: "", name: "", device_id: "", chambers: 3, simulated: false });
  const [creds, setCreds] = useState(null);
  const load = useCallback(async () => {
    try {
      const [c, d] = await Promise.all([axios.get(`${API}/clients`), axios.get(`${API}/devices`)]);
      setClients(c.data.clients);
      setDevices(d.data.devices);
    } catch (e) { /* noop */ }
  }, []);
  useEffect(() => { load(); }, [load]);
  const refresh = () => { load(); reloadDevices(); };
  const err = (e) => toast.error(e.response?.status === 409 ? t.alreadyExists : formatApiError(e.response?.data?.detail, t.saveFailed));

  const addClient = async () => {
    if (!clientName.trim()) return;
    try { await axios.post(`${API}/clients`, { name: clientName.trim() }); setClientName(""); refresh(); } catch (e) { err(e); }
  };
  const delClient = async (c) => {
    if (!window.confirm(`${t.confirmDeleteClient} ${c.name}?`)) return;
    try { await axios.delete(`${API}/clients/${c.id}`); refresh(); } catch (e) { toast.error(e.response?.status === 409 ? t.clientHasDevices : t.saveFailed); }
  };
  const addDevice = async () => {
    if (!f.client_id || !f.name.trim() || !/^[a-z0-9][a-z0-9_-]{2,47}$/.test(f.device_id)) { toast.error(t.deviceInvalid); return; }
    try {
      const { data } = await axios.post(`${API}/devices`, { ...f, chambers: Number(f.chambers) });
      setCreds(await (await axios.get(`${API}/devices/${data.device_id}/credentials`)).data);
      setF({ ...f, name: "", device_id: "" });
      refresh();
    } catch (e) { err(e); }
  };
  const toggleSim = async (d) => { try { await axios.patch(`${API}/devices/${d.device_id}`, { simulated: !d.simulated }); refresh(); } catch (e) { err(e); } };
  const showCreds = async (d) => { try { setCreds((await axios.get(`${API}/devices/${d.device_id}/credentials`)).data); } catch (e) { err(e); } };
  const delDevice = async (d) => {
    if (!window.confirm(`${t.confirmDeleteDevice} ${d.name}?`)) return;
    try { await axios.delete(`${API}/devices/${d.device_id}`); refresh(); } catch (e) { err(e); }
  };
  const set = (k) => (e) => setF({ ...f, [k]: k === "simulated" ? e.target.checked : e.target.value });

  return (
    <div className="panel panel-pad" data-testid="fleet-card">
      <div className="flex items-center gap-2 font-head" style={{ fontSize: 15, fontWeight: 600, marginBottom: 10 }}><Building2 size={16} /> {t.fleet}</div>
      {clients.map((c) => (
        <div key={c.id} className="reg-cell" style={{ marginBottom: 8, padding: "8px 10px" }} data-testid={`client-${c.id}`}>
          <div className="flex items-center justify-between">
            <span className="font-head" style={{ fontSize: 14, fontWeight: 700 }}>{c.name}</span>
            <button className="sp-btn" onClick={() => delClient(c)} data-testid={`client-delete-${c.id}`} aria-label="delete"><Trash2 size={13} /></button>
          </div>
          {devices.filter((d) => d.client_id === c.id).map((d) => (
            <div key={d.device_id} className="flex items-center justify-between" style={{ padding: "6px 0", borderTop: "1px solid var(--border)", marginTop: 6 }}
              data-testid={`fleet-device-${d.device_id}`}>
              <div style={{ minWidth: 0 }}>
                <div className="flex items-center gap-1" style={{ fontSize: 12 }}><Cpu size={12} /> {d.name}
                  <span className={`led ${d.online ? "ok" : ""}`} style={{ marginLeft: 4, ...(d.online ? {} : { background: "#444" }) }} /></div>
                <div style={{ fontSize: 10, color: "var(--muted)" }}>{d.device_id} · {d.chambers} {t.chambersShort}{d.simulated ? ` · ${t.simulator}` : ""}</div>
              </div>
              <div className="flex gap-1">
                <button className="sp-btn" title={t.simulator} onClick={() => toggleSim(d)} data-testid={`device-sim-${d.device_id}`}
                  style={{ width: "auto", padding: "0 8px", fontSize: 10, color: d.simulated ? "var(--primary)" : "var(--muted)" }}>SIM</button>
                <button className="sp-btn" onClick={() => showCreds(d)} data-testid={`device-creds-${d.device_id}`} aria-label="credentials"><KeyRound size={13} /></button>
                <button className="sp-btn" onClick={() => delDevice(d)} data-testid={`device-delete-${d.device_id}`} aria-label="delete"><Trash2 size={13} /></button>
              </div>
            </div>
          ))}
        </div>
      ))}
      {creds && <Creds c={creds} t={t} onClose={() => setCreds(null)} />}

      <div style={{ fontSize: 11, color: "var(--muted)", margin: "12px 0 6px" }}>{t.addClient}</div>
      <div className="grid gap-2" style={{ gridTemplateColumns: "1fr 44px" }}>
        <input className="num-input" style={{ fontSize: 13 }} placeholder={t.clientName} value={clientName}
          onChange={(e) => setClientName(e.target.value)} data-testid="new-client-name" />
        <button className="sp-btn" style={{ width: 44, height: "auto" }} onClick={addClient} data-testid="new-client-add" aria-label="add"><Plus size={16} /></button>
      </div>

      <div style={{ fontSize: 11, color: "var(--muted)", margin: "12px 0 6px" }}>{t.addDevice}</div>
      <div className="grid gap-2" style={{ gridTemplateColumns: "1fr 1fr" }}>
        <select className="num-input" style={{ fontSize: 13, gridColumn: "1 / -1" }} value={f.client_id} onChange={set("client_id")} data-testid="new-device-client">
          <option value="">{t.chooseClient}</option>
          {clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <input className="num-input" style={{ fontSize: 13 }} placeholder={t.deviceName} value={f.name} onChange={set("name")} data-testid="new-device-name" />
        <input className="num-input" style={{ fontSize: 13 }} placeholder={t.deviceIdPh} value={f.device_id}
          onChange={(e) => setF({ ...f, device_id: e.target.value.toLowerCase() })} data-testid="new-device-id" />
        <label className="flex items-center gap-2" style={{ fontSize: 12 }}>{t.chambersCount}
          <select className="num-input" style={{ fontSize: 13, width: 70 }} value={f.chambers} onChange={set("chambers")} data-testid="new-device-chambers">
            {Array.from({ length: 10 }, (_, i) => <option key={i + 1} value={i + 1}>{i + 1}</option>)}
          </select>
        </label>
        <label className="flex items-center gap-2" style={{ fontSize: 12 }}>
          <input type="checkbox" checked={f.simulated} onChange={set("simulated")} data-testid="new-device-simulated" /> {t.simulator}
        </label>
      </div>
      <button className="action-btn" onClick={addDevice} data-testid="new-device-add" style={{ width: "100%", padding: 9, marginTop: 8, fontSize: 13 }}>
        <Plus size={14} /> {t.addDevice}
      </button>
    </div>
  );
};

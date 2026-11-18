import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { ShieldCheck, Trash2, UserPlus } from "lucide-react";
import { API } from "@/api";

const ROLES = ["viewer", "operator", "admin"];
const RK = { viewer: "roleViewer", operator: "roleOperator", admin: "roleAdmin", superadmin: "roleSuperadmin" };
const EMPTY = { email: "", name: "", password: "", role: "operator", client_ids: [] };

const FarmChecks = ({ clients, value, onChange, testid }) => (
  <div className="flex flex-wrap gap-2" style={{ marginTop: 6 }}>
    {clients.map((c) => (
      <label key={c.id} className="flex items-center gap-1" style={{ fontSize: 12, cursor: "pointer" }}>
        <input type="checkbox" checked={value.includes(c.id)} data-testid={`${testid}-${c.id}`} style={{ accentColor: "var(--primary)", width: 16, height: 16 }}
          onChange={(e) => onChange(e.target.checked ? [...value, c.id] : value.filter((x) => x !== c.id))} />
        {c.display_name || c.name}
      </label>
    ))}
  </div>
);

const UserRow = ({ u, t, clients, me, onChanged }) => {
  const [role, setRole] = useState(u.role);
  const [ids, setIds] = useState(u.client_ids || []);
  const dirty = role !== u.role || ids.join() !== (u.client_ids || []).join();
  const save = async () => {
    try { await axios.put(`${API}/users/${u.id}/access`, { role, client_ids: ids }); toast.success(t.saved); onChanged(); }
    catch (e) { toast.error(t.saveFailed); }
  };
  const del = async () => {
    if (!window.confirm(`${t.confirmDelete} ${u.email}?`)) return;
    try { await axios.delete(`${API}/users/${u.id}`); onChanged(); } catch (e) { toast.error(t.saveFailed); }
  };
  if (u.role === "superadmin") return (
    <div className="reg-cell" style={{ padding: "8px 10px", fontSize: 12 }} data-testid={`access-row-${u.email}`}>
      {u.email} <span style={{ color: "var(--muted)", fontSize: 10 }}>· {t.roleSuperadmin} · {t.accessAll}</span></div>
  );
  return (
    <div className="reg-cell" style={{ padding: "8px 10px" }} data-testid={`access-row-${u.email}`}>
      <div className="flex items-center gap-2">
        <div style={{ fontSize: 12, flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis" }}>{u.email}</div>
        <select className="num-input" value={role} onChange={(e) => setRole(e.target.value)} data-testid={`access-role-${u.email}`} style={{ fontSize: 11, width: 120, padding: "3px 6px" }}>
          {ROLES.map((r) => <option key={r} value={r}>{t[RK[r]]}</option>)}
        </select>
        {u.id !== me.id && <button className="sp-btn" onClick={del} data-testid={`access-delete-${u.email}`} aria-label="delete"><Trash2 size={13} /></button>}
      </div>
      <FarmChecks clients={clients} value={ids} onChange={setIds} testid={`access-farm-${u.email}`} />
      {!ids.length && <div style={{ fontSize: 10, color: "var(--accent)", marginTop: 4 }}>{t.accessNone}</div>}
      {dirty && <button className="action-btn" onClick={save} data-testid={`access-save-${u.email}`} style={{ marginTop: 6, padding: "5px 12px", fontSize: 12 }}>{t.save}</button>}
    </div>
  );
};

export const AccessCard = ({ t, me }) => {
  const [users, setUsers] = useState([]);
  const [clients, setClients] = useState([]);
  const [f, setF] = useState(EMPTY);
  const load = useCallback(async () => {
    try {
      const [u, c] = await Promise.all([axios.get(`${API}/users`), axios.get(`${API}/clients`)]);
      setUsers(u.data.users); setClients(c.data.clients || c.data);
    } catch (e) { /* ignore */ }
  }, []);
  useEffect(() => { load(); }, [load]);
  const add = async () => {
    try { await axios.post(`${API}/users`, f); setF(EMPTY); toast.success(t.userAdded); load(); }
    catch (e) { toast.error(e.response?.status === 409 ? t.userExists : e.response?.status === 422 ? t.userInvalid : t.saveFailed); }
  };
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  return (
    <div className="panel panel-pad" data-testid="access-card">
      <div className="flex items-center gap-2 font-head" style={{ fontSize: 15, fontWeight: 600, marginBottom: 4 }}><ShieldCheck size={16} /> {t.accessTitle}</div>
      <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 10 }}>{t.accessHint}</div>
      <div style={{ display: "flex", flexDirection: "column", gap: 6, marginBottom: 14 }}>
        {users.map((u) => <UserRow key={u.id + (u.client_ids || []).join() + u.role} u={u} t={t} clients={clients} me={me} onChanged={load} />)}
      </div>
      <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 6 }}>{t.accessNew}</div>
      <div className="grid gap-2" style={{ gridTemplateColumns: "1fr 1fr" }}>
        <input className="num-input" style={{ fontSize: 13 }} placeholder={t.email} value={f.email} onChange={set("email")} data-testid="access-new-email" />
        <input className="num-input" style={{ fontSize: 13 }} type="password" placeholder={t.passwordMin} value={f.password} onChange={set("password")} data-testid="access-new-password" autoComplete="new-password" />
        <select className="num-input" style={{ fontSize: 13, gridColumn: "1 / -1" }} value={f.role} onChange={set("role")} data-testid="access-new-role">
          {ROLES.map((r) => <option key={r} value={r}>{t[RK[r]]}</option>)}
        </select>
      </div>
      <FarmChecks clients={clients} value={f.client_ids} onChange={(client_ids) => setF({ ...f, client_ids })} testid="access-new-farm" />
      <button className="action-btn" data-testid="access-new-add" onClick={add} style={{ width: "100%", padding: 9, fontSize: 13, marginTop: 10 }}>
        <UserPlus size={14} /> {t.addUser}</button>
    </div>
  );
};

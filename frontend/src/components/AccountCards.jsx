import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { LogOut, Trash2, UserPlus } from "lucide-react";
import { API, formatApiError } from "@/api";

const ROLE_KEYS = { viewer: "roleViewer", operator: "roleOperator", admin: "roleAdmin", superadmin: "roleSuperadmin" };

export const THEMES = ["green", "light", "blue", "amber", "red", "teal", "graphite", "lightblue", "forest", "grass", "sun", "orange"];

export const ThemeSelect = ({ t, value, onChange, withDefault, testid, defaultLabel }) => (
  <select className="num-input" style={{ fontSize: 13 }} value={value || ""} onChange={(e) => onChange(e.target.value || null)} data-testid={testid}>
    {withDefault && <option value="">{defaultLabel}</option>}
    {THEMES.map((k) => <option key={k} value={k}>{t[`theme_${k}`]}</option>)}
  </select>
);

export const AccountCard = ({ t, user, onLogout, onUserChange, clientTheme }) => {
  const setTheme = async (theme) => {
    try { const { data } = await axios.put(`${API}/auth/preferences`, { theme }); onUserChange(data); }
    catch (e) { toast.error(t.saveFailed); }
  };
  const [cur, setCur] = useState("");
  const [nw, setNw] = useState("");
  const change = async () => {
    if (nw.length < 8) { toast.error(t.passwordShort); return; }
    try {
      await axios.put(`${API}/auth/password`, { current_password: cur, new_password: nw });
      setCur(""); setNw("");
      toast.success(t.passwordChanged);
    } catch (e) { toast.error(e.response?.status === 400 ? t.passwordWrong : t.saveFailed); }
  };
  return (
    <div className="panel panel-pad" data-testid="account-card">
      <div className="flex items-center justify-between" style={{ marginBottom: 12 }}>
        <div>
          <div className="font-head" style={{ fontSize: 15, fontWeight: 600 }} data-testid="account-email">{user.email}</div>
          <div style={{ fontSize: 11, color: "var(--muted)" }} data-testid="account-role">{t[ROLE_KEYS[user.role]]}</div>
        </div>
        <button className="action-btn" data-testid="logout-btn" onClick={onLogout} style={{ padding: "7px 12px", fontSize: 12 }}>
          <LogOut size={14} /> {t.logout}
        </button>
      </div>
      <label className="flex flex-col" style={{ gap: 4, fontSize: 11, color: "var(--muted)", marginBottom: 10 }}>{t.colorTheme}
        <ThemeSelect t={t} value={user.theme} onChange={setTheme} withDefault testid="theme-select"
          defaultLabel={`${t.themeDefault} (${t[`theme_${clientTheme || "green"}`]})`} />
      </label>
      <div className="grid gap-2" style={{ gridTemplateColumns: "1fr 1fr" }}>
        <input className="num-input" style={{ fontSize: 13 }} type="password" placeholder={t.currentPassword} value={cur}
          onChange={(e) => setCur(e.target.value)} data-testid="pw-current" autoComplete="current-password" />
        <input className="num-input" style={{ fontSize: 13 }} type="password" placeholder={t.newPassword} value={nw}
          onChange={(e) => setNw(e.target.value)} data-testid="pw-new" autoComplete="new-password" />
      </div>
      <button className="action-btn" data-testid="pw-change" onClick={change} style={{ width: "100%", padding: 9, marginTop: 8, fontSize: 13 }}>
        {t.changePassword}
      </button>
    </div>
  );
};

export const UsersCard = ({ t, me, clientId, clientName }) => {
  const q = clientId ? `?client_id=${clientId}` : "";
  const [users, setUsers] = useState([]);
  const [f, setF] = useState({ email: "", name: "", password: "", role: "operator" });
  const load = useCallback(() => axios.get(`${API}/users${q}`).then(({ data }) => setUsers(data.users)).catch(() => {}), [q]);
  useEffect(() => { load(); }, [load]);
  const add = async () => {
    try {
      await axios.post(`${API}/users`, { ...f, client_id: clientId });
      setF({ email: "", name: "", password: "", role: "operator" });
      toast.success(t.userAdded);
      load();
    } catch (e) {
      toast.error(e.response?.status === 409 ? t.userExists : e.response?.status === 422 ? t.userInvalid : formatApiError(e.response?.data?.detail, t.saveFailed));
    }
  };
  const del = async (id, email) => {
    if (!window.confirm(`${t.confirmDelete} ${email}?`)) return;
    try { await axios.delete(`${API}/users/${id}`); load(); } catch (e) { toast.error(t.saveFailed); }
  };
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  return (
    <div className="panel panel-pad" data-testid="users-card">
      <div className="font-head" style={{ fontSize: 15, fontWeight: 600, marginBottom: 10 }}>{t.users}{clientName ? ` · ${clientName}` : ""}</div>
      <div style={{ display: "flex", flexDirection: "column", gap: 6, marginBottom: 14 }}>
        {users.map((u) => (
          <div key={u.id} className="flex items-center justify-between reg-cell" style={{ padding: "8px 10px" }} data-testid={`user-row-${u.email}`}>
            <div style={{ minWidth: 0 }}>
              <div style={{ fontSize: 12, overflow: "hidden", textOverflow: "ellipsis" }}>{u.email}</div>
              <div style={{ fontSize: 10, color: "var(--muted)" }}>{t[ROLE_KEYS[u.role]]}</div>
            </div>
            {u.id !== me.id && (
              <button className="sp-btn" data-testid={`user-delete-${u.email}`} onClick={() => del(u.id, u.email)} aria-label="delete"><Trash2 size={14} /></button>
            )}
          </div>
        ))}
      </div>
      <div className="grid gap-2" style={{ gridTemplateColumns: "1fr 1fr" }}>
        <input className="num-input" style={{ fontSize: 13 }} placeholder={t.email} value={f.email} onChange={set("email")} data-testid="new-user-email" />
        <input className="num-input" style={{ fontSize: 13 }} type="password" placeholder={t.passwordMin} value={f.password} onChange={set("password")} data-testid="new-user-password" autoComplete="new-password" />
        <select className="num-input" style={{ fontSize: 13 }} value={f.role} onChange={set("role")} data-testid="new-user-role">
          <option value="viewer">{t.roleViewer}</option>
          <option value="operator">{t.roleOperator}</option>
          <option value="admin">{t.roleAdmin}</option>
        </select>
        <button className="action-btn" data-testid="new-user-add" onClick={add} style={{ padding: 9, fontSize: 13 }}>
          <UserPlus size={14} /> {t.addUser}
        </button>
      </div>
    </div>
  );
};

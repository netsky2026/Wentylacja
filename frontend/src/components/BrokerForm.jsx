import { useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const Field = ({ label, children }) => (
  <label className="flex flex-col" style={{ gap: 4, fontSize: 11, color: "var(--muted)" }}>{label}{children}</label>
);

export const BrokerForm = ({ t, config, onSaved }) => {
  const [f, setF] = useState(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (config) setF({ host: config.broker_host, port: String(config.broker_port), username: config.username || "",
      password: "", tls: !!config.tls, prefix: config.prefix });
  }, [config]);
  if (!f) return null;
  const set = (k) => (e) => {
    if (k !== "tls") return setF({ ...f, [k]: e.target.value });
    const tls = e.target.checked;
    const port = tls && f.port === "1883" ? "8883" : !tls && f.port === "8883" ? "1883" : f.port;
    setF({ ...f, tls, port });
  };
  const inp = (k, type = "text", extra = {}) => (
    <input className="num-input" style={{ fontSize: 13 }} type={type} value={f[k]} onChange={set(k)} data-testid={`broker-${k}`} {...extra} />
  );
  const save = async () => {
    const port = parseInt(f.port, 10);
    if (!f.host.trim() || !f.prefix.trim() || !(port >= 1 && port <= 65535)) {
      toast.error(t.invalidBroker); return;
    }
    setBusy(true);
    try {
      const body = { host: f.host.trim(), port, username: f.username.trim(), tls: f.tls,
        prefix: f.prefix.trim() };
      if (f.password) body.password = f.password;
      const { data } = await axios.put(`${API}/broker`, body);
      onSaved(data);
      toast.success(t.brokerSaved);
    } catch (e) { toast.error(t.saveFailed); }
    setBusy(false);
  };
  return (
    <div className="panel panel-pad" data-testid="broker-form">
      <div className="font-head" style={{ fontSize: 15, fontWeight: 600, marginBottom: 4 }}>{t.settings}</div>
      <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 12 }}>{t.brokerHint}</div>
      <div className="grid gap-2" style={{ gridTemplateColumns: "2fr 1fr" }}>
        <Field label={t.host}>{inp("host")}</Field>
        <Field label={t.port}>{inp("port", "number")}</Field>
        <Field label={t.username}>{inp("username", "text", { autoComplete: "off" })}</Field>
        <Field label={t.password}>{inp("password", "password", { autoComplete: "new-password", placeholder: config.has_password ? "••••••" : "" })}</Field>
      </div>
      <div className="grid gap-2" style={{ gridTemplateColumns: "1fr 1fr", marginTop: 8 }}>
        <Field label={t.prefix}>{inp("prefix")}</Field>
      </div>
      <label className="flex items-center gap-2" style={{ fontSize: 12, margin: "12px 0" }}>
        <input type="checkbox" checked={f.tls} onChange={set("tls")} data-testid="broker-tls" /> TLS (8883)
      </label>
      <div style={{ fontSize: 10, color: "var(--muted)", marginBottom: 10, wordBreak: "break-all" }}>
        {t.stateTopic}: {f.prefix}/&lt;ID&gt;/state · {t.commandTopic}: {f.prefix}/&lt;ID&gt;/command
      </div>
      <button className="action-btn" data-testid="broker-save" onClick={save} disabled={busy} style={{ width: "100%", padding: 10 }}>
        {busy ? "…" : t.saveConnect}
      </button>
    </div>
  );
};

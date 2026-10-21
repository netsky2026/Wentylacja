import { useEffect, useState } from "react";
import axios from "axios";
import { LogIn, ArrowLeft } from "lucide-react";
import { API, formatApiError } from "@/api";

export const LoginScreen = ({ t, onLogin, lang, setLang, brand, onBack }) => {
  useEffect(() => {
    if (brand?.theme && !localStorage.getItem("theme_user")) document.documentElement.dataset.theme = brand.theme;
  }, [brand]);
  const logo = brand?.logo_version ? `${API}/public/logo/${brand.slug}?v=${brand.logo_version}` : "/icon-192.png";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const { data } = await axios.post(`${API}/auth/login`, { email, password });
      onLogin(data);
    } catch (err) {
      const st = err.response?.status;
      setError(st === 401 ? t.loginInvalid : st === 429 ? t.loginLocked : formatApiError(err.response?.data?.detail, t.loginFailed));
    }
    setBusy(false);
  };
  return (
    <div className="app-shell">
      <div className="mobile-wrap fade-in" style={{ maxWidth: 420, paddingTop: "calc(12vh + env(safe-area-inset-top))" }}>
        <div className="flex items-center justify-between" style={{ marginBottom: 28 }}>
          <div className="flex items-center gap-3">
            {onBack && <button className="sp-btn" onClick={onBack} data-testid="login-back" aria-label={t.back}><ArrowLeft size={16} /></button>}
            <img src={logo} alt="" data-testid="login-logo" style={{ width: 56, height: 56, borderRadius: 14, objectFit: "contain" }} />
          </div>
          <div className="panel flex" style={{ overflow: "hidden" }}>
            {["pl", "en"].map((l) => (
              <button key={l} data-testid={`login-lang-${l}`} onClick={() => setLang(l)} className="font-head"
                style={{ background: lang === l ? "var(--surface2)" : "transparent", color: lang === l ? "var(--text)" : "var(--muted)",
                  border: "none", padding: "7px 11px", cursor: "pointer", fontSize: 13, fontWeight: 700 }}>{l.toUpperCase()}</button>
            ))}
          </div>
        </div>
        <h1 className="font-head" style={{ fontSize: 34, fontWeight: 700, lineHeight: 1.05, margin: "0 0 6px" }} data-testid="login-title">{brand?.app_name || t.appName}</h1>
        <p style={{ color: "var(--muted)", fontSize: 13, margin: "0 0 28px" }}>{t.loginSubtitle}</p>
        <form onSubmit={submit} className="panel panel-pad" data-testid="login-form" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <label className="flex flex-col" style={{ gap: 4, fontSize: 11, color: "var(--muted)" }}>{t.email}
            <input className="num-input" type="email" autoComplete="username" required value={email}
              onChange={(e) => setEmail(e.target.value)} data-testid="login-email" />
          </label>
          <label className="flex flex-col" style={{ gap: 4, fontSize: 11, color: "var(--muted)" }}>{t.password}
            <input className="num-input" type="password" autoComplete="current-password" required value={password}
              onChange={(e) => setPassword(e.target.value)} data-testid="login-password" />
          </label>
          {error && <div data-testid="login-error" style={{ color: "var(--accent)", fontSize: 12 }}>{error}</div>}
          <button type="submit" className="action-btn" disabled={busy} data-testid="login-submit"
            style={{ background: "var(--primary)", borderColor: "var(--primary)", color: "var(--on-primary)", fontWeight: 700 }}>
            <LogIn size={16} /> {busy ? "…" : t.loginBtn}
          </button>
        </form>
      </div>
    </div>
  );
};

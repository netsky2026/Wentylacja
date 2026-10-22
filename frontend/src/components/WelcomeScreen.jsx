import { LogIn, Phone, Mail, Thermometer, Droplets, Wind } from "lucide-react";
import { useEffect } from "react";
import { siteLogoUrl } from "@/api";

export const Contact = ({ site }) => {
  if (!site?.phone && !site?.email) return null;
  return (
    <div className="welcome-rise flex flex-wrap gap-x-6 gap-y-2" style={{ animationDelay: "420ms", fontSize: 13 }} data-testid="welcome-contact-block">
      {site.phone && <a href={`tel:${site.phone.replace(/[^0-9+]/g, "")}`} className="welcome-link" data-testid="welcome-contact-phone"><Phone size={14} /> {site.phone}</a>}
      {site.email && <a href={`mailto:${site.email}`} className="welcome-link" data-testid="welcome-contact-email"><Mail size={14} /> {site.email}</a>}
    </div>
  );
};

const BrandLogo = ({ site }) => site?.logo_version
  ? <img src={siteLogoUrl(site)} alt="" className="welcome-rise welcome-logo-img" data-testid="welcome-brand-logo" />
  : <img src="/marco-polo.png" alt="Grupa Marco-Polo" className="welcome-rise welcome-logo" data-testid="welcome-brand-logo" />;

export const WelcomeScreen = ({ t, site, lang, setLang, onLogin }) => {
  useEffect(() => { document.documentElement.dataset.theme = "green"; }, []);
  const pills = [[Thermometer, t.welcomeTemp], [Droplets, t.humidity], [Wind, "CO₂"]];
  return (
    <div className="welcome-page" data-testid="welcome-page-container">
      <div className="welcome-photo" aria-hidden="true" style={{ backgroundImage: "url(/welcome.jpg)" }} />
      <div className="welcome-content">
        <header className="flex items-center justify-between welcome-rise">
          <div className="flex items-center gap-3">
            <span className="font-head" style={{ fontSize: 15, fontWeight: 600, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--muted)" }}>Marco Polo</span>
          </div>
          <div className="panel flex" style={{ overflow: "hidden" }}>
            {["pl", "en"].map((l) => (
              <button key={l} data-testid={`welcome-lang-${l}`} onClick={() => setLang(l)} className="font-head"
                style={{ background: lang === l ? "var(--surface2)" : "transparent", color: lang === l ? "var(--text)" : "var(--muted)",
                  border: "none", padding: "7px 11px", cursor: "pointer", fontSize: 13, fontWeight: 700 }}>{l.toUpperCase()}</button>
            ))}
          </div>
        </header>

        <main className="welcome-main">
          <BrandLogo site={site} />
          <div className="welcome-rise flex items-center gap-2" style={{ animationDelay: "80ms", fontSize: 11, letterSpacing: "0.14em", textTransform: "uppercase", color: "var(--primary)" }}>
            <span className="welcome-led" /> {t.welcomeKicker}
          </div>
          <h1 className="font-head welcome-rise text-5xl sm:text-6xl lg:text-7xl" data-testid="welcome-brand-title"
            style={{ animationDelay: "160ms", fontWeight: 700, lineHeight: 0.92, textTransform: "uppercase", margin: "14px 0 18px" }}>
            Marco Polo<br /><span style={{ color: "var(--primary)" }}>Wentylacja</span>
          </h1>
          <p className="welcome-rise text-sm sm:text-base" style={{ animationDelay: "240ms", color: "var(--muted)", maxWidth: 440, lineHeight: 1.6, margin: "0 0 22px" }}>{t.welcomeTagline}</p>
          <div className="welcome-rise flex flex-wrap gap-2" style={{ animationDelay: "300ms", marginBottom: 30 }}>
            {pills.map(([Icon, label]) => (
              <span key={label} className="welcome-pill"><Icon size={13} /> {label}</span>
            ))}
          </div>
          <button className="welcome-cta welcome-rise" style={{ animationDelay: "360ms" }} onClick={onLogin} data-testid="welcome-login-button">
            <LogIn size={18} /> {t.loginBtn}
          </button>
          {(site?.phone || site?.email) && (
            <div className="welcome-rise welcome-contact" style={{ animationDelay: "420ms" }} data-testid="welcome-contact-card">
              <div style={{ fontSize: 11, letterSpacing: "0.12em", textTransform: "uppercase", color: "var(--muted)", marginBottom: 8 }}>{t.loginContact}</div>
              <Contact site={site} />
            </div>
          )}
        </main>

        <footer className="flex flex-col gap-3" style={{ paddingBottom: "calc(20px + env(safe-area-inset-bottom))" }}>
          <div style={{ fontSize: 11, color: "var(--muted)" }}>© {new Date().getFullYear()} Marco Polo Wentylacja</div>
        </footer>
      </div>
    </div>
  );
};

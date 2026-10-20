import { useEffect, useState } from "react";
import { Smartphone, Check } from "lucide-react";

const isStandalone = () => window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone === true;

export const InstallCard = ({ t }) => {
  const [prompt, setPrompt] = useState(null);
  const [installed, setInstalled] = useState(isStandalone());
  useEffect(() => {
    const onPrompt = (e) => { e.preventDefault(); setPrompt(e); };
    const onInstalled = () => setInstalled(true);
    window.addEventListener("beforeinstallprompt", onPrompt);
    window.addEventListener("appinstalled", onInstalled);
    return () => { window.removeEventListener("beforeinstallprompt", onPrompt); window.removeEventListener("appinstalled", onInstalled); };
  }, []);
  const install = async () => { prompt.prompt(); await prompt.userChoice; setPrompt(null); };
  return (
    <div className="panel panel-pad" data-testid="install-card">
      <div className="flex items-center gap-2 font-head" style={{ fontSize: 15, fontWeight: 600, marginBottom: 8 }}>
        <Smartphone size={16} /> {t.installTitle}
      </div>
      {installed ? (
        <div data-testid="install-status" className="flex items-center gap-2" style={{ fontSize: 12, color: "var(--green)" }}><Check size={14} /> {t.installed}</div>
      ) : (
        <>
          {prompt && <button className="action-btn mb-3" data-testid="install-btn" onClick={install} style={{ width: "100%", padding: 10 }}>{t.installBtn}</button>}
          <div style={{ fontSize: 11, color: "var(--muted)", lineHeight: 1.6 }}>{t.installIos}<br />{t.installAndroid}</div>
        </>
      )}
    </div>
  );
};

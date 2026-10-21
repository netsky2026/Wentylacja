import { useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Globe, Upload, Trash2 } from "lucide-react";
import { API, siteLogoUrl } from "@/api";

const SiteLogo = ({ t, site, reloadSite }) => {
  const upload = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    if (file.size > 1_000_000) { toast.error(t.logoInvalid); return; }
    const fd = new FormData();
    fd.append("file", file);
    try { await axios.post(`${API}/site/logo`, fd); reloadSite(); toast.success(t.saved); } catch (err) { toast.error(t.logoInvalid); }
  };
  const remove = async () => { try { await axios.delete(`${API}/site/logo`); reloadSite(); } catch (e) { toast.error(t.saveFailed); } };
  return (
    <div className="flex items-center gap-2" style={{ marginBottom: 10 }}>
      <div style={{ width: 44, height: 44, borderRadius: 10, border: "1px solid var(--border)", background: "var(--surface)", overflow: "hidden" }}>
        <img src={siteLogoUrl(site)} alt="" data-testid="site-logo-preview" style={{ width: "100%", height: "100%", objectFit: "contain" }} />
      </div>
      <label className="action-btn" style={{ padding: "6px 12px", fontSize: 12, cursor: "pointer" }}>
        <Upload size={13} /> {t.uploadLogo}
        <input type="file" accept="image/png,image/jpeg,image/webp" onChange={upload} style={{ display: "none" }} data-testid="site-logo-input" />
      </label>
      {site?.logo_version && <button className="sp-btn" onClick={remove} data-testid="site-logo-remove" aria-label={t.removeLogo}><Trash2 size={13} /></button>}
    </div>
  );
};

export const SiteCard = ({ t, site, reloadSite }) => {
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  useEffect(() => { if (site) { setPhone(site.phone); setEmail(site.email); } }, [site]);
  const save = async () => {
    try { await axios.put(`${API}/site`, { phone: phone.trim(), email: email.trim() }); reloadSite(); toast.success(t.saved); }
    catch (e) { toast.error(e.response?.status === 422 ? t.recipientInvalid : t.saveFailed); }
  };
  return (
    <div className="panel panel-pad" data-testid="site-card">
      <div className="flex items-center gap-2 font-head" style={{ fontSize: 15, fontWeight: 600, marginBottom: 4 }}><Globe size={16} /> {t.siteTitle}</div>
      <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 10 }}>{t.siteLogoHint}</div>
      <SiteLogo t={t} site={site} reloadSite={reloadSite} />
      <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 6 }}>{t.siteHint}</div>
      <div className="grid gap-2" style={{ gridTemplateColumns: "1fr 1fr" }}>
        <input className="num-input" style={{ fontSize: 13 }} placeholder="+48 600 000 000" value={phone} onChange={(e) => setPhone(e.target.value)} data-testid="site-phone" />
        <input className="num-input" style={{ fontSize: 13 }} placeholder="biuro@firma.pl" value={email} onChange={(e) => setEmail(e.target.value)} data-testid="site-email" />
      </div>
      <button className="action-btn" onClick={save} data-testid="site-save" style={{ width: "100%", padding: 9, marginTop: 10, fontSize: 13 }}>{t.save}</button>
    </div>
  );
};

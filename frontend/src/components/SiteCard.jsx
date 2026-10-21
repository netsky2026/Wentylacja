import { useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Globe } from "lucide-react";
import { API } from "@/api";

export const SiteCard = ({ t }) => {
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  useEffect(() => {
    axios.get(`${API}/public/site`).then(({ data }) => { setPhone(data.phone); setEmail(data.email); }).catch(() => {});
  }, []);
  const save = async () => {
    try { await axios.put(`${API}/site`, { phone: phone.trim(), email: email.trim() }); toast.success(t.saved); }
    catch (e) { toast.error(e.response?.status === 422 ? t.recipientInvalid : t.saveFailed); }
  };
  return (
    <div className="panel panel-pad" data-testid="site-card">
      <div className="flex items-center gap-2 font-head" style={{ fontSize: 15, fontWeight: 600, marginBottom: 4 }}><Globe size={16} /> {t.siteTitle}</div>
      <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 10 }}>{t.siteHint}</div>
      <div className="grid gap-2" style={{ gridTemplateColumns: "1fr 1fr" }}>
        <input className="num-input" style={{ fontSize: 13 }} placeholder="+48 600 000 000" value={phone} onChange={(e) => setPhone(e.target.value)} data-testid="site-phone" />
        <input className="num-input" style={{ fontSize: 13 }} placeholder="biuro@firma.pl" value={email} onChange={(e) => setEmail(e.target.value)} data-testid="site-email" />
      </div>
      <button className="action-btn" onClick={save} data-testid="site-save" style={{ width: "100%", padding: 9, marginTop: 10, fontSize: 13 }}>{t.save}</button>
    </div>
  );
};

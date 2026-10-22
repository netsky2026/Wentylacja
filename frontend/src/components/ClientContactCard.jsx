import { useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Contact as ContactIcon } from "lucide-react";
import { API } from "@/api";

const FIELDS = [["phone", "+48 600 000 000", 40], ["email", "biuro@ferma.pl", 254], ["website", "www.ferma.pl", 200], ["address", "ul. Polna 1, 00-000 Wieś", 200]];

export const ClientContactCard = ({ t, clientId, clientName }) => {
  const q = clientId ? `?client_id=${clientId}` : "";
  const [f, setF] = useState({ phone: "", email: "", website: "", address: "" });
  useEffect(() => { axios.get(`${API}/client-contact${q}`).then(({ data }) => setF(data)).catch(() => {}); }, [q]);
  const save = async () => {
    try { await axios.put(`${API}/client-contact${q}`, f); toast.success(t.saved); }
    catch (e) { toast.error(e.response?.status === 422 ? t.recipientInvalid : t.saveFailed); }
  };
  return (
    <div className="panel panel-pad" data-testid="client-contact-card">
      <div className="flex items-center gap-2 font-head" style={{ fontSize: 15, fontWeight: 600, marginBottom: 4 }}>
        <ContactIcon size={16} /> {t.myContactTitle}{clientName ? ` · ${clientName}` : ""}</div>
      <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 10 }}>{t.myContactHint}</div>
      <div className="grid gap-2 sm:grid-cols-2">
        {FIELDS.map(([k, ph, max]) => (
          <label key={k} style={{ fontSize: 11, color: "var(--muted)", display: "flex", flexDirection: "column", gap: 4 }}>{t[`field_${k}`]}
            <input className="num-input" style={{ fontSize: 13 }} placeholder={ph} value={f[k] || ""} maxLength={max}
              onChange={(e) => setF({ ...f, [k]: e.target.value })} data-testid={`client-contact-${k}`} />
          </label>
        ))}
      </div>
      <button className="action-btn" onClick={save} data-testid="client-contact-save" style={{ width: "100%", padding: 9, marginTop: 10, fontSize: 13 }}>{t.save}</button>
    </div>
  );
};

import { useState } from "react";
import axios from "axios";
import { Send, MessageSquare, CheckCircle2 } from "lucide-react";
import { API } from "@/api";

const EMPTY = { name: "", phone: "", email: "", message: "", company: "" };

export const ContactForm = ({ t }) => {
  const [open, setOpen] = useState(false);
  const [f, setF] = useState(EMPTY);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [sent, setSent] = useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    if (!f.phone.trim() && !f.email.trim()) { setError(t.contactNeedReach); return; }
    setBusy(true);
    try {
      await axios.post(`${API}/public/contact`, f);
      setSent(true); setF(EMPTY);
    } catch (err) {
      const st = err.response?.status;
      setError(st === 429 ? t.contactTooMany : st === 422 ? t.contactInvalid : t.contactFailed);
    }
    setBusy(false);
  };

  if (!open) return (
    <button className="welcome-link welcome-rise contact-toggle" style={{ animationDelay: "480ms" }} onClick={() => setOpen(true)} data-testid="contact-form-open">
      <MessageSquare size={15} /> {t.contactOpen}
    </button>
  );
  if (sent) return (
    <div className="welcome-contact contact-sent" data-testid="contact-form-success"><CheckCircle2 size={18} /> {t.contactSent}</div>
  );
  return (
    <form className="welcome-contact contact-form" onSubmit={submit} data-testid="contact-form">
      <div style={{ fontSize: 11, letterSpacing: "0.12em", textTransform: "uppercase", color: "var(--muted)" }}>{t.contactTitle}</div>
      <input className="num-input" placeholder={t.contactName} value={f.name} onChange={set("name")} required minLength={2} maxLength={80} data-testid="contact-name" />
      <div className="grid gap-2" style={{ gridTemplateColumns: "1fr 1fr" }}>
        <input className="num-input" type="tel" placeholder={t.contactPhone} value={f.phone} onChange={set("phone")} maxLength={40} data-testid="contact-phone" />
        <input className="num-input" type="email" placeholder="E-mail" value={f.email} onChange={set("email")} maxLength={254} data-testid="contact-email" />
      </div>
      <textarea className="num-input" rows={4} placeholder={t.contactMessage} value={f.message} onChange={set("message")} required minLength={5} maxLength={2000} data-testid="contact-message" />
      <input className="contact-hp" tabIndex={-1} autoComplete="off" aria-hidden="true" value={f.company} onChange={set("company")} name="company" />
      {error && <div className="err-text" style={{ fontSize: 12, color: "#f87171" }} data-testid="contact-form-error">{error}</div>}
      <button className="welcome-cta" style={{ fontSize: 16, padding: "12px 20px" }} disabled={busy} data-testid="contact-form-submit">
        <Send size={16} /> {busy ? t.contactSending : t.contactSend}
      </button>
    </form>
  );
};

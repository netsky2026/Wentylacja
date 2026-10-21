import { useEffect, useRef, useState } from "react";
import QRCode from "qrcode";
import { Download } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";

const W = 600, H = 1120;
const loadImg = (src) => new Promise((res) => { const i = new Image(); i.onload = () => res(i); i.onerror = () => res(null); i.src = src; });

const wrap = (ctx, text, x, y, max, lh) => {
  let line = "";
  for (const w of text.split(" ")) {
    if (ctx.measureText(line + w).width > max && line) { ctx.fillText(line.trim(), x, y); y += lh; line = ""; }
    line += w + " ";
  }
  ctx.fillText(line.trim(), x, y);
  return y + lh;
};

const drawSteps = (ctx, title, steps) => {
  ctx.fillStyle = "#F0F3F0";
  ctx.fillRect(30, 760, W - 60, 330);
  ctx.textAlign = "left";
  ctx.fillStyle = "#1E8A50";
  ctx.font = "700 26px 'Barlow Condensed', sans-serif";
  ctx.fillText(title.toUpperCase(), 54, 800);
  let y = 842;
  steps.forEach((st, i) => {
    ctx.fillStyle = "#1E8A50";
    ctx.beginPath(); ctx.arc(68, y - 7, 14, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = "#FFFFFF"; ctx.textAlign = "center";
    ctx.font = "700 17px 'JetBrains Mono', monospace";
    ctx.fillText(String(i + 1), 68, y - 1);
    ctx.fillStyle = "#101612"; ctx.textAlign = "left";
    ctx.font = "500 17px 'JetBrains Mono', monospace";
    y = wrap(ctx, st, 94, y, W - 140, 24) + 14;
  });
};

const drawPoster = async (canvas, { link, name, logoSrc, t }) => {
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#FFFFFF";
  ctx.fillRect(0, 0, W, H);
  const logo = await loadImg(logoSrc);
  if (logo) {
    const s = Math.min(110 / logo.width, 110 / logo.height);
    ctx.drawImage(logo, (W - logo.width * s) / 2, 40 + (110 - logo.height * s) / 2, logo.width * s, logo.height * s);
  }
  const qr = document.createElement("canvas");
  await QRCode.toCanvas(qr, link, { width: 440, margin: 1, errorCorrectionLevel: "M", color: { dark: "#0A0A0A", light: "#FFFFFF" } });
  ctx.drawImage(qr, (W - 440) / 2, 175);
  ctx.fillStyle = "#0A0A0A";
  ctx.textAlign = "center";
  ctx.font = "700 40px 'Barlow Condensed', sans-serif";
  ctx.fillText(name, W / 2, 680, W - 60);
  ctx.fillStyle = "#59635C";
  ctx.font = "500 18px 'JetBrains Mono', monospace";
  ctx.fillText(link.replace(/^https?:\/\//, ""), W / 2, 722, W - 60);
  drawSteps(ctx, t.qrStepsTitle, t.qrSteps);
};

export const QrDialog = ({ open, onOpenChange, t, link, name, logoSrc, slug }) => {
  const ref = useRef(null);
  const [url, setUrl] = useState("");
  useEffect(() => {
    if (!open || !link) return;
    const c = document.createElement("canvas");
    c.width = W; c.height = H;
    ref.current = c;
    drawPoster(c, { link, name, logoSrc, t }).then(() => setUrl(c.toDataURL("image/png")));
  }, [open, link, name, logoSrc, t]);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="qr-dialog" style={{ background: "var(--card)", borderColor: "var(--border)", color: "var(--text)", maxWidth: 400 }}>
        <DialogHeader>
          <DialogTitle className="font-head">{t.qrTitle}</DialogTitle>
          <DialogDescription style={{ color: "var(--muted)", fontSize: 12 }}>{t.qrHint}</DialogDescription>
        </DialogHeader>
        {url ? <img src={url} alt="QR" data-testid="qr-image" style={{ width: "100%", borderRadius: 12 }} />
          : <div style={{ aspectRatio: `${W}/${H}`, background: "var(--surface)", borderRadius: 12 }} />}
        <a className="action-btn" href={url || undefined} download={`qr-${slug}.png`} data-testid="qr-download"
          style={{ background: "var(--primary)", borderColor: "var(--primary)", color: "var(--on-primary)", fontWeight: 700, padding: 10, textDecoration: "none" }}>
          <Download size={15} /> {t.qrDownload}
        </a>
      </DialogContent>
    </Dialog>
  );
};

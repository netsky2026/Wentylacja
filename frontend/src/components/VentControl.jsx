import { useEffect, useState } from "react";
import { Slider } from "@/components/ui/slider";

const Row = ({ label, value, onChange, onCommit, testid }) => (
  <div style={{ marginBottom: 14 }} data-testid={testid}>
    <div className="flex items-center justify-between" style={{ fontSize: 12, marginBottom: 8 }}>
      <span style={{ color: "var(--muted)" }}>{label}</span>
      <span className="font-head" data-testid={`${testid}-value`} style={{ fontSize: 15, fontWeight: 700 }}>{value}%</span>
    </div>
    <Slider className="vent-slider" min={0} max={100} step={5} value={[value]}
      onValueChange={([v]) => onChange(v)} onValueCommit={([v]) => onCommit(v)} />
  </div>
);

export const VentControl = ({ ch, t, send }) => {
  const manual = ch.mode === "manual";
  const m = ch.manual || {};
  const [cl, setCl] = useState(0);
  const [cr, setCr] = useState(0);
  const [cc, setCc] = useState(0);
  useEffect(() => {
    setCl(Math.round(100 - (m.curtain_left ?? ch.curtain_left)));
    setCr(Math.round(100 - (m.curtain_right ?? ch.curtain_right)));
    setCc(Math.round(m.chimney ?? ch.chimney));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ch.id, ch.mode, m.curtain_left, m.curtain_right, m.chimney]);
  const vent = (key, v) => send({ type: "set_vent", chamber: ch.id, value: { [key]: v } });
  const mode = (v) => send({ type: "set_mode", chamber: ch.id, value: v });

  return (
    <div className="reg-cell mb-3" data-testid={`chamber-${ch.id}-vent-control`}>
      <div className="flex items-center justify-between" style={{ marginBottom: manual ? 14 : 0 }}>
        <span style={{ fontSize: 12, color: "var(--muted)" }}>{t.controlMode}</span>
        <div className="flex" style={{ border: "1px solid var(--border)", borderRadius: 8, overflow: "hidden" }}>
          {[["auto", t.modeAuto], ["manual", t.modeManual]].map(([k, label]) => (
            <button key={k} data-testid={`chamber-${ch.id}-mode-${k}`} onClick={() => !ch.on || ch.mode === k ? null : mode(k)}
              disabled={!ch.on} className="font-head"
              style={{
                background: ch.mode === k ? "#2a2f35" : "transparent", color: ch.mode === k ? "var(--text)" : "var(--muted)",
                border: "none", padding: "6px 14px", fontSize: 13, fontWeight: 700, cursor: ch.on ? "pointer" : "not-allowed",
                transition: "background-color 0.2s ease, color 0.2s ease",
              }}>{label}</button>
          ))}
        </div>
      </div>
      {manual && ch.on && (
        <div className="fade-in">
          <Row label={`${t.curtainLeft} (${t.closedPct})`} value={cl} onChange={setCl} onCommit={(v) => vent("curtain_left", 100 - v)} testid={`chamber-${ch.id}-slider-curtain-left`} />
          <Row label={`${t.curtainRight} (${t.closedPct})`} value={cr} onChange={setCr} onCommit={(v) => vent("curtain_right", 100 - v)} testid={`chamber-${ch.id}-slider-curtain-right`} />
          <Row label={`${t.chimney} (${t.openPct})`} value={cc} onChange={setCc} onCommit={(v) => vent("chimney", v)} testid={`chamber-${ch.id}-slider-chimney`} />
          <div style={{ fontSize: 10, color: "var(--muted)" }}>{t.manualHint}</div>
        </div>
      )}
    </div>
  );
};

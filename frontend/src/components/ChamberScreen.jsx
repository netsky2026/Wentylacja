import { Thermometer, Droplets, Wind, Flame, AlertTriangle, Target } from "lucide-react";
import { CurtainWindow, ChimneyGauge } from "@/components/Gauges";
import { VentControl } from "@/components/VentControl";
import { ChamberNameEdit } from "@/components/ChamberNameEdit";
import { CycleCard } from "@/components/CycleCard";

const Sensor = ({ icon, label, value, unit, warn, testid }) => (
  <div className="sensor" data-testid={testid}>
    <span className="flex items-center gap-1" style={{ color: "var(--muted)", fontSize: 10 }}>{icon}{label}</span>
    <span className="font-head" style={{ fontSize: 26, fontWeight: 700, color: warn ? "var(--accent)" : "var(--text)" }}>
      {value}<span style={{ fontSize: 12, color: "var(--muted)", fontWeight: 500 }}> {unit}</span>
    </span>
  </div>
);

export const ChamberScreen = ({ ch, t, send, canControl, dev, canRename, onRenamed }) => (
  <div className={`panel panel-pad fade-in ${ch.alarm ? "alarm-card" : ""}`} data-testid={`chamber-${ch.id}-screen`}
    style={{ opacity: ch.on ? 1 : 0.75 }}>
    <div className="flex items-center justify-between mb-3">
      <span className="flex items-center gap-2" style={{ minWidth: 0, flex: 1, marginRight: 8 }}>
        <span className={`led ${ch.on ? "ok" : "warn"}`} />
        <ChamberNameEdit t={t} dev={dev} id={ch.id} size={22} editable={canRename} onSaved={onRenamed} />
      </span>
      <span className="flex items-center gap-2">
        {ch.alarm && <span className="badge badge-alarm" data-testid={`chamber-${ch.id}-alarm`}><AlertTriangle size={12} /> {t.alarm}</span>}
        <span className="font-head" data-testid={`chamber-${ch.id}-status`} style={{ fontSize: 13, color: ch.on ? "var(--green)" : "var(--muted)" }}>{ch.on ? t.running : t.off}</span>
      </span>
    </div>

    <div className="flex items-end justify-between mb-3">
      <div className="font-head" data-testid={`chamber-${ch.id}-temp`}
        style={{ fontSize: 56, fontWeight: 700, lineHeight: 1, color: ch.temp_alarm ? "var(--accent)" : "var(--text)" }}>
        {ch.temp?.toFixed(1)}<span style={{ fontSize: 20, color: "var(--muted)" }}>°C</span>
      </div>
      <div className="flex flex-col items-end" style={{ gap: 6, fontSize: 12, color: "var(--muted)" }}>
        <span className="flex items-center gap-1" data-testid={`chamber-${ch.id}-setpoint`}><Target size={12} /> {t.setpoint}: {ch.setpoint?.toFixed(1)}°C</span>
        <span className="flex items-center gap-1" data-testid={`chamber-${ch.id}-heating`} style={{ color: ch.heating ? "var(--warn-text)" : "var(--muted)" }}>
          <Flame size={12} /> {t.heating}: {ch.heating ? t.on : t.off}
        </span>
      </div>
    </div>

    <div className="grid gap-2 mb-3" style={{ gridTemplateColumns: "1fr 1fr" }}>
      <Sensor icon={<Droplets size={11} />} label={t.humidity} value={Math.round(ch.humidity)} unit="%" testid={`chamber-${ch.id}-humidity`} />
      <Sensor icon={<Wind size={11} />} label={t.co2} value={Math.round(ch.co2)} unit="ppm" warn={ch.co2_alarm} testid={`chamber-${ch.id}-co2`} />
    </div>

    <div className="reg-cell mb-3">
      <div className="flex items-center gap-1 mb-3" style={{ color: "var(--muted)", fontSize: 11 }}><Thermometer size={11} /> {t.ventilation}
        <span data-testid={`chamber-${ch.id}-mode-badge`} style={{ marginLeft: "auto", fontWeight: 600, letterSpacing: "0.04em", padding: "1px 7px", borderRadius: 999,
          ...(ch.mode === "manual" ? { color: "var(--warn-text)", background: "var(--warn-bg)", border: "1px solid var(--warn-border)" } : { color: "var(--muted)" }) }}>
          {ch.mode === "manual" ? t.modeManual : t.modeAuto}</span></div>
      <div className="grid" style={{ gridTemplateColumns: "1fr 1fr 1fr", alignItems: "end" }}>
        <CurtainWindow open={ch.curtain_left} label={t.curtainLeft} testid={`chamber-${ch.id}-curtain-left`} scale={1.3} />
        <ChimneyGauge open={ch.chimney} label={t.chimney} testid={`chamber-${ch.id}-chimney`} scale={1.3} />
        <CurtainWindow open={ch.curtain_right} label={t.curtainRight} testid={`chamber-${ch.id}-curtain-right`} scale={1.3} />
      </div>
      <div style={{ fontSize: 10, color: "var(--muted)", textAlign: "center", marginTop: 8 }}>{t.curtainHint}</div>
    </div>

    {dev && <CycleCard t={t} ch={ch} deviceId={dev.device_id} canEdit={canControl} />}

    {canControl && <VentControl ch={ch} t={t} send={send} autoReturn={dev?.auto_return} />}
  </div>
);

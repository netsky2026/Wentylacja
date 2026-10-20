// Window with a roller blind; closed% = 100 - open%
export const CurtainWindow = ({ open, label, testid, scale = 1 }) => {
  const closed = Math.round(100 - (open ?? 0));
  return (
    <div className="flex flex-col items-center" data-testid={testid} style={{ gap: 4 }}>
      <div className="win-frame" style={{ width: 54 * scale, height: 64 * scale }}>
        <div className="win-glass">
          <span className="win-mullion-v" />
          <span className="win-mullion-h" />
        </div>
        <div className="win-blind" style={{ height: `${closed}%` }}>
          <span className="win-blind-bar" />
        </div>
        <div className="win-box" />
      </div>
      <span className="font-head" data-testid={`${testid}-value`} style={{ fontSize: 14 * scale, fontWeight: 700 }}>{closed}%</span>
      <span style={{ fontSize: 10 + scale, color: "var(--muted)" }}>{label}</span>
    </div>
  );
};

export const ChimneyGauge = ({ open, label, testid, scale = 1 }) => {
  const v = Math.round(open ?? 0);
  const size = 64 * scale;
  const r = 26;
  const c = 2 * Math.PI * r;
  return (
    <div className="flex flex-col items-center" data-testid={testid} style={{ gap: 4 }}>
      <div style={{ position: "relative", width: size, height: size }}>
        <svg width={size} height={size} viewBox="0 0 64 64">
          <circle cx="32" cy="32" r={r} fill="none" stroke="#262626" strokeWidth="6" />
          <circle cx="32" cy="32" r={r} fill="none" stroke="#34A56A" strokeWidth="6" strokeLinecap="round"
            strokeDasharray={c} strokeDashoffset={c * (1 - v / 100)} transform="rotate(-90 32 32)"
            style={{ transition: "stroke-dashoffset 0.6s ease" }} />
        </svg>
        <span className="font-head" data-testid={`${testid}-value`} style={{ position: "absolute", inset: 0,
          display: "flex", alignItems: "center", justifyContent: "center", fontSize: 13 * scale, fontWeight: 700 }}>{v}%</span>
      </div>
      <span style={{ fontSize: 10 + scale, color: "var(--muted)" }}>{label}</span>
    </div>
  );
};

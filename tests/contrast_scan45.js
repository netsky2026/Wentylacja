() => {
  const parse = (s) => { const m = s.match(/rgba?\(([^)]+)\)/); if (!m) return null; const p = m[1].split(/[ ,\/]+/).filter(Boolean).map(Number); return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 }; };
  const lum = (c) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }; return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b); };
  const cr = (a, b) => { const l1 = lum(a), l2 = lum(b); return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05); };
  const bgsOf = (el) => {
    let e = el;
    while (e) {
      const cs = getComputedStyle(e);
      if (cs.backgroundImage && cs.backgroundImage.includes("gradient")) {
        const cols = (cs.backgroundImage.match(/rgba?\([^)]+\)/g) || []).map(parse).filter((c) => c && c.a > 0.5);
        if (cols.length) return { cols, tag: (e.className || e.tagName).toString().slice(0, 30) };
      }
      const c = parse(cs.backgroundColor);
      if (c && c.a > 0.5) return { cols: [c], tag: (e.className || e.tagName).toString().slice(0, 30) };
      e = e.parentElement;
    }
    return { cols: [parse(getComputedStyle(document.body).backgroundColor)], tag: "body" };
  };
  const out = [];
  document.querySelectorAll("body *").forEach((el) => {
    if (!Array.from(el.childNodes).some((n) => n.nodeType === 3 && n.textContent.trim())) return;
    const r = el.getBoundingClientRect(); if (r.width === 0 || r.height === 0) return;
    const cs = getComputedStyle(el); if (cs.visibility === "hidden" || +cs.opacity === 0) return;
    if (el.closest("option")) return;
    const fg = parse(cs.color); if (!fg) return;
    const { cols, tag } = bgsOf(el);
    const worst = Math.min(...cols.map((b) => cr(fg, b)));
    if (worst < 4.5) out.push({ text: el.textContent.trim().slice(0, 40), tid: el.getAttribute("data-testid") || el.closest("[data-testid]")?.getAttribute("data-testid"), color: cs.color, bg: tag, ratio: +worst.toFixed(2), shadow: cs.textShadow !== "none" });
  });
  return { overflow: document.documentElement.scrollWidth, low: out.slice(0, 25), count: out.length };
}

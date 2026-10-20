# Iteration 13: per-theme contrast/visibility checks (pasted into browser_automation)
BASE = "https://fatek-mqtt.preview.emergentagent.com"
await page.set_viewport_size({"width": 390, "height": 844})
JS_CONTRAST = """(sel) => {
  const el = document.querySelector(sel); if (!el) return null;
  const parse = c => { const m = c.match(/[\\d.]+/g).map(Number); return m; };
  const lum = ([r,g,b]) => { const f = v => { v/=255; return v<=0.03928? v/12.92 : Math.pow((v+0.055)/1.055,2.4); }; return 0.2126*f(r)+0.7152*f(g)+0.0722*f(b); };
  let n = el, bg = null;
  while (n) { const b = getComputedStyle(n).backgroundColor; const p = parse(b); if (p.length<4 || p[3]>0.5) { if (!(p.length===4 && p[3]===0)) { bg = p; break; } } n = n.parentElement; }
  if (!bg) bg = parse(getComputedStyle(document.body).backgroundColor);
  const fg = parse(getComputedStyle(el).color);
  const L1 = lum(fg), L2 = lum(bg); const r = (Math.max(L1,L2)+0.05)/(Math.min(L1,L2)+0.05);
  return {fg: getComputedStyle(el).color, bg: bg.join(','), ratio: Math.round(r*100)/100, text: el.textContent.trim().slice(0,30)};
}"""
try:
    await page.fill('[data-testid="login-email"]', "admin@chlewnia.pl")
    await page.fill('[data-testid="login-password"]', "Wentylacja!2026")
    await page.click('[data-testid="login-submit"]')
    await page.wait_for_selector('[data-testid="bottom-nav"]', timeout=15000)
    await page.evaluate("localStorage.setItem('device','kowalski-a')")
    for theme in ["light", "green", "blue", "amber"]:
        r = await page.request.put(f"{BASE}/api/auth/preferences", data={"theme": theme})
        await page.reload()
        await page.wait_for_selector('[data-testid="bottom-nav"]', timeout=15000)
        await page.wait_for_timeout(1500)
        print(f"=== {theme} pref={r.status} applied={await page.evaluate('document.documentElement.dataset.theme')}")
        await page.click('[data-testid="nav-chambers"]')
        await page.wait_for_timeout(500)
        btn = page.locator('[data-testid="chamber-0-mode-manual"]')
        if await btn.count():
            await btn.click(); await page.wait_for_timeout(1500)
        print(" badge", await page.evaluate(JS_CONTRAST, '[data-testid="chamber-0-mode-badge"]'))
        print(" heating", await page.evaluate(JS_CONTRAST, '[data-testid="chamber-0-heating"]'))
        surf = await page.evaluate("""() => { const q=s=>{const e=document.querySelector(s); return e? getComputedStyle(e).backgroundColor : null};
           return {sensor:q('.sensor'), reg:q('.reg-cell'), nav:q('[data-testid=bottom-nav]'), input:q('.num-input'), sw: document.documentElement.scrollWidth}; }""")
        print(" surfaces", surf)
        await page.screenshot(path=f".screenshots/it13_{theme}_komory.jpg", quality=40, full_page=False)
        await page.click('[data-testid="nav-data"]'); await page.wait_for_timeout(2500)
        strokes = await page.evaluate("""() => [...document.querySelectorAll('[data-testid^=chart-] .recharts-line-curve, [data-testid^=daily-] .recharts-rectangle')].map(p => (p.closest('[data-testid]').dataset.testid)+':'+getComputedStyle(p)[p.classList.contains('recharts-rectangle')?'fill':'stroke']).filter((v,i,a)=>a.indexOf(v)===i)""")
        print(" chart colors", strokes, "sw", await page.evaluate("document.documentElement.scrollWidth"))
        await page.evaluate("window.scrollTo(0, 600)")
        await page.screenshot(path=f".screenshots/it13_{theme}_dane.jpg", quality=40, full_page=False)
        await page.click('[data-testid="nav-settings"]'); await page.wait_for_timeout(2000)
        print(" mocked banner", await page.evaluate(JS_CONTRAST, '[data-testid="alarm-mocked-banner"]'), "sw", await page.evaluate("document.documentElement.scrollWidth"))
        await page.locator('[data-testid="alarm-mocked-banner"]').scroll_into_view_if_needed()
        await page.screenshot(path=f".screenshots/it13_{theme}_settings.jpg", quality=40, full_page=False)
        await page.click('[data-testid="nav-chambers"]'); await page.wait_for_timeout(500)
        a = page.locator('[data-testid="chamber-0-mode-auto"]')
        if await a.count(): await a.click(); await page.wait_for_timeout(800)
    await page.request.put(f"{BASE}/api/auth/preferences", data={"theme": None})
    print("reset theme done")
except Exception as e:
    print("ERR", e)

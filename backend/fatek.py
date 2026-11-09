"""Native Fatek M-series MQTT format: {"d": {"<tag>": [v0, v1, ...]}, "error": [], "ts": "..."}.

Tag names = our field names (optionally with _x10/_x100/_x1000 = value divided by 10/100/1000).
Per-chamber tags hold one value per chamber (index = chamber id); plant tags hold one value.
Messages may carry only some tags – values are merged per device until a full state is known.
"""
import math
import re
import time

CH_TAGS = ("temp", "setpoint", "humidity", "co2", "curtain_left", "curtain_right", "chimney", "water_lpm", "water_total_l",
           "on", "heating", "mode", "manual_curtain_left", "manual_curtain_right", "manual_chimney")
REQUIRED = ("temp", "setpoint", "humidity", "co2", "curtain_left", "curtain_right", "chimney")
PLANT_TAGS = {"power_kw": "power_kw", "power_kwh": "power_kwh", "plant_water_lpm": "water_lpm", "plant_water_total_l": "water_total_l"}
SCALE_RX = re.compile(r"^(.*)_x(10|100|1000)$")
_cache: dict = {}
TTL_S = 60


def forget(device_id: str):
    _cache.pop(device_id, None)


def is_fatek(p) -> bool:
    return isinstance(p, dict) and isinstance(p.get("d"), dict) and "chambers" not in p


def _vals(v, div):
    v = v if isinstance(v, list) else [v]
    out = []
    for x in v:
        if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
            return None
        out.append(x / div)
    return out


def convert(p: dict, device_id: str, n: int):
    """Returns (standard_state, None) or (None, error message in Polish)."""
    now = time.time()
    cache = {k: v for k, v in _cache.get(device_id, {}).items() if now - v[1] < TTL_S}
    unknown, bad, short, fresh = [], [], [], {}
    for raw, v in p["d"].items():
        tag, div = str(raw).strip().lower(), 1
        m = SCALE_RX.match(tag)
        if m:
            tag, div = m.group(1), int(m.group(2))
        if tag not in CH_TAGS and tag not in PLANT_TAGS:
            unknown.append(str(raw))
            continue
        vals = _vals(v, div)
        if vals is None:
            bad.append(str(raw))
        elif tag in CH_TAGS and len(vals) < n:
            short.append(str(raw))
        else:
            fresh[tag] = (vals, now)
    if bad:
        return None, f"Fatek: tagi {', '.join(bad)} muszą zawierać liczby"
    if short:
        return None, f"Fatek: tag(i) {', '.join(short)} mają mniej wartości niż komór ({n}) – jedna wartość na komorę"
    if not fresh:
        return None, (f"Fatek: brak znanych tagów (otrzymane: {', '.join(unknown) or '–'}). Nazwij DataItem jak pola "
                      f"(np. temp_x10 = [komora0, komora1, …]).")
    cache.update(fresh)
    _cache[device_id] = cache
    cache = {k: v[0] for k, v in cache.items()}
    missing = [t for t in REQUIRED if t not in cache]
    if missing:
        hint = f" Nieznane tagi: {', '.join(unknown)}." if unknown else ""
        return None, (f"Fatek: brak tagów: {', '.join(missing)}.{hint} Nazwij DataItem jak pola "
                      f"(np. temp_x10 = [komora0, komora1, …]).")
    short = [t for t in CH_TAGS if t in cache and len(cache[t]) < n]
    if short:
        return None, f"Fatek: tag(i) {', '.join(short)} mają mniej wartości niż komór ({n}) – jedna wartość na komorę"
    chambers = []
    for i in range(n):
        ch = {"id": i, "on": bool(cache["on"][i]) if "on" in cache else True,
              "heating": bool(cache["heating"][i]) if "heating" in cache else False,
              "mode": "manual" if "mode" in cache and cache["mode"][i] else "auto"}
        for t in REQUIRED + ("water_lpm", "water_total_l"):
            if t in cache:
                ch[t] = cache[t][i]
        man = {t[7:]: cache[t][i] for t in ("manual_curtain_left", "manual_curtain_right", "manual_chimney") if t in cache}
        if man:
            ch["manual"] = man
        chambers.append(ch)
    plant = {dst: cache[src][0] for src, dst in PLANT_TAGS.items() if src in cache and cache[src]}
    return {"model": "Fatek M (format natywny)", "chambers": chambers, "plant": plant}, None

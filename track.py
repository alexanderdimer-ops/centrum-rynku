"""Samotestowanie strony: zapisuje przewidywania, sprawdza je po czasie i liczy skuteczność.

Wszystko trafia do track.json (gałąź "dane" na GitHubie, obok data.json):
- preds: przewidywania „cena będzie wyżej za 4 godziny / 1 dzień / tydzień / miesiąc” z podaną szansą,
- sims: wirtualne transakcje otwierane, gdy strona mówi „Możesz rozważyć wejście” (stop loss i cel z planu),
- picks: propozycje z zakładki „Teraz warto” (krótko / średnio / długo) i ich wynik,
- stats: liczniki zbierane od początku (nie kasują się przy czyszczeniu starych wpisów).
Na tej podstawie strona się koryguje: kalibruje szanse i zaostrza próg w „Teraz warto”, gdy propozycje słabo wychodzą.
"""
import json, datetime as dt

HZ = {"4h": dt.timedelta(hours=4), "1d": dt.timedelta(days=1), "1w": dt.timedelta(days=7), "1m": dt.timedelta(days=30)}
EVERY = {"4h": dt.timedelta(hours=4), "1d": dt.timedelta(hours=20), "1w": dt.timedelta(hours=20), "1m": dt.timedelta(days=6)}
PICK_HZ = {"short": dt.timedelta(days=1), "mid": dt.timedelta(days=7), "long": dt.timedelta(days=30)}
BINS = [(0, 45), (45, 50), (50, 55), (55, 60), (60, 101)]


def load(path="track.json"):
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return {"preds": [], "sims": [], "picks": [], "stats": {}}


def save(tr, path="track.json"):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(tr, f, ensure_ascii=False, separators=(",", ":"))


def _stat(tr, key):
    return tr["stats"].setdefault(key, {"n": 0, "hit": 0, "up": 0, "ret": 0.0, "bins": [[0, 0] for _ in BINS], "sym": {}})


def calibrate(tr, hz, p):
    """Korekta szansy na podstawie własnych, rozliczonych przewidywań (gdy jest ich dość w danym przedziale)."""
    s = tr["stats"].get("pred_" + hz)
    if not s or p is None:
        return p, None
    for b, (lo, hi) in enumerate(BINS):
        if lo <= p < hi:
            n, up = s["bins"][b]
            if n >= 30:
                live = 100 * up / n
                return round((p + live) / 2, 1), {"n": n, "live": round(live, 1)}
    return p, None


def pick_threshold(tr, horizon):
    """Próg „Teraz warto”: zaostrza się, gdy wcześniejsze propozycje wypadały słabo, łagodnieje, gdy dobrze."""
    base = 62 if horizon == "short" else 70
    s = tr["stats"].get("pick_" + horizon)
    if not s or s["n"] < 20:
        return base
    win = s["hit"] / s["n"]
    return int(round(base + max(-5, min(15, (0.55 - win) * 100))))


def update(tr, now, items, scan_items, picks_now):
    prices = {x["symbol"]: x["price"] for x in scan_items}
    prices.update({it["symbol"]: it["price"] for it in items})
    by_sym = {it["symbol"]: it for it in items}

    # 1. rozlicz przewidywania, którym minął czas
    for p in tr["preds"]:
        if p.get("res") is None and now >= dt.datetime.fromisoformat(p["due"]) and p["s"] in prices:
            out = prices[p["s"]]
            up = out > p["px"]
            p.update(res=out, up=up, ret=out / p["px"] - 1)
            s = _stat(tr, "pred_" + p["h"])
            s["n"] += 1; s["up"] += up; s["ret"] += p["ret"]
            s["hit"] += (p["p"] > 50) == up
            for b, (lo, hi) in enumerate(BINS):
                if lo <= p["p"] < hi:
                    s["bins"][b][0] += 1; s["bins"][b][1] += up
            sy = s["sym"].setdefault(p["s"], [0, 0]); sy[0] += 1; sy[1] += (p["p"] > 50) == up

    # 2. zapisz nowe przewidywania (tylko gdy rynek jest otwarty – świeża cena)
    last = {}
    for p in tr["preds"]:
        k = (p["s"], p["h"]); last[k] = max(last.get(k, ""), p["t"])
    for it in items:
        if not it.get("live_price"):
            continue
        probs = {"4h": (it.get("hours") or {}).get("p"), "1d": it.get("overall"), "1w": it.get("p_week"),
                 "1m": it.get("p_month")}
        for h, p in probs.items():
            if p is None or abs(p - 50) < 1:
                continue
            k = (it["symbol"], h)
            if k in last and now - dt.datetime.fromisoformat(last[k]) < EVERY[h]:
                continue
            rec = {"s": it["symbol"], "h": h, "t": now.isoformat(), "due": (now + HZ[h]).isoformat(),
                   "px": it["price"], "p": p, "dec": it["decision"]["key"]}
            if h in ("1d", "1w") and it.get("live_x"):
                rec["f"] = it["live_x"]  # cechy do nauki drugiego modelu na własnych wynikach
            tr["preds"].append(rec)

    # 3. wirtualne transakcje: wejście przy „Możesz rozważyć wejście”, wyjście na stopie, celu lub po 10 dniach
    open_syms = {x["s"] for x in tr["sims"] if x.get("end") is None}
    for x in tr["sims"]:
        if x.get("end") is not None or x["s"] not in by_sym:
            continue
        it = by_sym[x["s"]]; px = it["price"]
        lo, hi = min(x.get("lo", px), px), max(x.get("hi", px), px)
        O = it["ohlc"]; t0 = it["hist"]["t0"]; d0 = dt.date.fromisoformat(x["t"][:10]).toordinal()
        for k, dd in enumerate(O["dd"]):  # pełne świece dzienne po dniu wejścia
            if t0 + dd > d0:
                lo, hi = min(lo, O["l"][k]), max(hi, O["h"][k])
        x["lo"], x["hi"] = lo, hi
        risk = x["px"] - x["stop"]
        res = None
        if lo <= x["stop"]:
            res, ex = "stop", x["stop"]
        elif hi >= x["target"]:
            res, ex = "cel", x["target"]
        elif now - dt.datetime.fromisoformat(x["t"]) > dt.timedelta(days=14):
            res, ex = "czas", px
        if res:
            x.update(end=now.isoformat(), res=res, exit=ex, R=round((ex - x["px"]) / risk, 2) if risk > 0 else 0)
            s = _stat(tr, "sim"); s["n"] += 1; s["hit"] += x["R"] > 0; s["ret"] += x["R"]
    for it in items:
        if it["decision"]["key"] == "go" and it["symbol"] not in open_syms and it.get("live_price"):
            tr["sims"].append({"s": it["symbol"], "n": it["name"], "t": now.isoformat(), "px": it["price"],
                               "stop": it["plan"]["stop"], "target": it["plan"]["target"]})

    # 4. propozycje z „Teraz warto”: zapisz raz dziennie, rozlicz po horyzoncie
    for x in tr["picks"]:
        if x.get("res") is None and now >= dt.datetime.fromisoformat(x["due"]):
            if x["s"] in prices:
                x.update(res=prices[x["s"]], ret=prices[x["s"]] / x["px"] - 1)
                s = _stat(tr, "pick_" + x["h"]); s["n"] += 1; s["hit"] += x["ret"] > 0; s["ret"] += x["ret"]
            elif now - dt.datetime.fromisoformat(x["due"]) > dt.timedelta(days=3):
                x.update(res=0, ret=None)  # brak ceny – pomijamy
    lastp = {}
    for x in tr["picks"]:
        lastp[x["h"]] = max(lastp.get(x["h"], ""), x["t"])
    for h, lst in picks_now.items():
        if h in lastp and now - dt.datetime.fromisoformat(lastp[h]) < dt.timedelta(hours=20):
            continue
        for c in lst[:3]:
            tr["picks"].append({"s": c["symbol"], "n": c["name"], "h": h, "t": now.isoformat(),
                                "due": (now + PICK_HZ[h]).isoformat(), "px": c["price"], "score": c["score"]})

    # 5. porządki: trzymamy ostatnie wpisy (liczniki w stats zostają)
    cut = (now - dt.timedelta(days=45)).isoformat()
    tr["preds"] = [p for p in tr["preds"] if p.get("res") is None or p["t"] > cut][-6000:]
    tr["sims"] = [x for x in tr["sims"] if x.get("end") is None or x["t"] > cut][-300:]
    tr["picks"] = [x for x in tr["picks"] if x.get("res") is None or x["t"] > (now - dt.timedelta(days=90)).isoformat()][-400:]
    return tr


def summary(tr, names):
    """Zwięzłe podsumowanie do pokazania na stronie."""
    def st(key):
        s = tr["stats"].get(key)
        if not s or not s["n"]:
            return None
        return {"n": s["n"], "hit": round(100 * s["hit"] / s["n"], 1), "up": round(100 * s["up"] / s["n"], 1),
                "avg": s["ret"] / s["n"]}
    preds = {h: st("pred_" + h) for h in HZ}
    bins = {}
    for h in HZ:
        s = tr["stats"].get("pred_" + h)
        if s:
            bins[h] = [{"lo": lo, "hi": min(hi, 100), "n": b[0], "up": round(100 * b[1] / b[0], 1) if b[0] else None}
                       for (lo, hi), b in zip(BINS, s["bins"])]
    per_sym = {}
    for h in HZ:
        s = tr["stats"].get("pred_" + h)
        for sym, (n, hit) in (s or {}).get("sym", {}).items():
            a = per_sym.setdefault(sym, [0, 0]); a[0] += n; a[1] += hit
    sims = tr["sims"]
    closed = [x for x in sims if x.get("end")]
    eq, curve = 0.0, []
    for x in sorted(closed, key=lambda x: x["end"]):
        eq += x["R"]; curve.append({"t": x["end"], "eq": round(eq, 2)})
    pending = sum(p.get("res") is None for p in tr["preds"])
    recent = sorted([p for p in tr["preds"] if p.get("res") is not None], key=lambda p: p["due"])[-30:][::-1]
    return {"preds": preds, "bins": bins, "pending": pending,
            "sim": st("sim"), "sims_open": [x for x in sims if not x.get("end")][-20:],
            "sims_closed": closed[-30:][::-1], "curve": curve[-200:],
            "picks": {h: st("pick_" + h) for h in PICK_HZ},
            "picks_recent": [x for x in tr["picks"] if x.get("res") is not None and x.get("ret") is not None][-30:][::-1],
            "threshold": {h: pick_threshold(tr, h) for h in PICK_HZ},
            "per_sym": {s: {"n": a[0], "hit": round(100 * a[1] / a[0], 1), "name": names.get(s, s)}
                        for s, a in per_sym.items() if a[0] >= 5},
            "recent": [{"s": p["s"], "name": names.get(p["s"], p["s"]), "h": p["h"], "t": p["t"], "p": p["p"],
                        "up": p["up"], "ret": p["ret"]} for p in recent]}

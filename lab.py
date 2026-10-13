"""Laboratorium nauki: strona sama wymyśla i sprawdza nowe wersje swojego modelu.

Co godzinę (jeden eksperyment na raz) bierze kolejny przepis – horyzont (dzień / tydzień / miesiąc), zestaw cech,
siłę regularyzacji i długość okna nauki – i sprawdza go uczciwym testem kroczącym na historii ~60 instrumentów
(uczy się tylko na przeszłości, zgaduje przyszłość, nie wraca do tych samych momentów).
Zapamiętuje wyniki, wybiera najlepszy przepis dla każdego horyzontu i szuka „strefy 65%”:
progu pewności, powyżej którego model trafia w co najmniej 65% przypadków (przy min. 300 przypadkach).
Najlepszy przepis jest potem używany na żywo, a jego „pewne sygnały” są sprawdzane na bieżąco w track.py.
"""
import json, math, random, datetime as dt
import ml

FEATS = {
    "wszystkie cechy": list(range(17)),
    "tempo ruchu": [0, 1, 2, 3, 12, 13],
    "trend i średnie": [4, 5, 6, 10, 11, 13],
    "odbicia po skrajnościach": [0, 1, 4, 7, 10, 14, 15, 16],
    "bez świec": list(range(14)),
    "zmienność i obrót": [7, 8, 9, 10, 0, 1],
}
HZ = {"1d": 1, "1w": 5, "1m": 21}
LAMS = [5.0, 50.0, 300.0]
WINDOWS = [750, 1100, 2000]
THRESH = [0.02, 0.03, 0.04, 0.05, 0.06, 0.08, 0.10, 0.12, 0.15, 0.2]
MIN_SURE = 300


def all_configs():
    out = []
    for h in HZ:
        for f in FEATS:
            for lam in LAMS:
                for w in WINDOWS:
                    out.append({"h": h, "feats": f, "lam": lam, "window": w})
    return out


def cfg_id(c): return f"{c['h']}|{c['feats']}|{c['lam']}|{c['window']}"


def build_rows(prepped):
    rows = []
    for sym, P, days in prepped:
        c, n = P["c"], len(P["c"])
        for i in range(260, n - 22):
            x = ml.feat(P, i)
            if x is None:
                continue
            rows.append((days[i], sym, x, {h: c[i + k] > c[i] for h, k in HZ.items()},
                         {h: c[i + k] / c[i] - 1 for h, k in HZ.items()}))
    rows.sort(key=lambda r: r[0])
    return rows


def evaluate(rows, cfg, seed=11, step=63, max_rows=10000):
    """Test kroczący dla jednego przepisu. Zwraca trafność, przewagę nad „zawsze wzrost” i strefę pewności."""
    h, idx, k = cfg["h"], FEATS[cfg["feats"]], HZ[cfg["h"]]
    dates = sorted({r[0] for r in rows})
    if len(dates) < 700:
        return None
    rnd = random.Random(seed)
    blocks = [dates[i] for i in range(500, len(dates), step)]
    preds = []
    for b, b0 in enumerate(blocks):
        b1 = blocks[b + 1] if b + 1 < len(blocks) else None
        lim = dates[max(0, dates.index(b0) - k - 1)]
        train = [r for r in rows if r[0] < lim and (b0 - r[0]).days <= cfg["window"]]
        if len(train) < 500:
            continue
        if len(train) > max_rows:
            train = rnd.sample(train, max_rows)
        m = ml.fit([[r[2][j] for j in idx] for r in train], [1.0 if r[3][h] else 0.0 for r in train],
                   lam=cfg["lam"], iters=5)
        for r in rows:
            if r[0] >= b0 and (b1 is None or r[0] < b1):
                preds.append((ml.predict(m, [r[2][j] for j in idx]), r[3][h], r[4][h], r[0]))
    if len(preds) < 2000:
        return None
    n = len(preds)
    acc = sum((p > 0.5) == y for p, y, _, _ in preds) / n
    up = sum(y for _, y, _, _ in preds) / n
    majority = max(up, 1 - up)
    sure = None
    for t in THRESH:  # najmniejszy próg (największe pokrycie), przy którym trafność ≥ 65%
        sel = [(p, y) for p, y, _, _ in preds if abs(p - 0.5) >= t]
        if len(sel) < MIN_SURE:
            break
        a = sum((p > 0.5) == y for p, y in sel) / len(sel)
        if a >= 0.65 and sure is None:
            sure = {"thr": t, "acc": round(100 * a, 1), "n": len(sel), "coverage": round(100 * len(sel) / n, 1)}
    # najlepsza trafność w „najpewniejszej” grupie (nawet jeśli < 65%) – żeby pokazać postęp
    best_sel = None
    for t in THRESH:
        sel = [(p, y) for p, y, _, _ in preds if abs(p - 0.5) >= t]
        if len(sel) < MIN_SURE:
            break
        a = sum((p > 0.5) == y for p, y in sel) / len(sel)
        if not best_sel or a > best_sel["acc"] / 100:
            best_sel = {"thr": t, "acc": round(100 * a, 1), "n": len(sel), "coverage": round(100 * len(sel) / n, 1)}
    # stabilność: czy przewaga utrzymuje się w drugiej połowie okresu (ochrona przed przypadkiem)
    half = preds[n // 2:]
    acc2 = sum((p > 0.5) == y for p, y, _, _ in half) / len(half)
    return {"acc": round(100 * acc, 1), "majority": round(100 * majority, 1), "edge": round(100 * (acc - majority), 2),
            "n": n, "sure": sure, "best_sel": best_sel, "acc_recent": round(100 * acc2, 1),
            "period": [preds[0][3].isoformat(), preds[-1][3].isoformat()]}


def score(res):
    """Ranking przepisów: przewaga nad „zawsze wzrost”, premia za strefę 65% i stabilność."""
    if not res:
        return -99
    s = res["edge"]
    if res["sure"]:
        s += 2 + res["sure"]["coverage"] / 10
    s += min(0, res["acc_recent"] - res["majority"]) * 0.5
    return round(s, 2)


def describe(cfg):
    hz = {"1d": "na jutro", "1w": "na tydzień", "1m": "na miesiąc"}[cfg["h"]]
    lam = {5.0: "słabe", 50.0: "średnie", 300.0: "mocne"}[cfg["lam"]]
    return (f"przewidywanie {hz}, cechy: {cfg['feats']}, {lam} zabezpieczenie przed uczeniem na pamięć, "
            f"nauka na ostatnich ~{cfg['window'] // 365} latach")


def step(lab, prepped, now, budget=1):
    """Wykonuje kolejny eksperyment (lub kilka) i aktualizuje najlepsze przepisy."""
    lab.setdefault("experiments", []); lab.setdefault("progress", []); lab.setdefault("best", {})
    done = {e["id"] for e in lab["experiments"]}
    queue = [c for c in all_configs() if cfg_id(c) not in done]
    if not queue:  # wszystko sprawdzone – powtarzamy najstarsze na nowych danych
        queue = [e["cfg"] for e in sorted(lab["experiments"], key=lambda e: e["time"])[:budget]]
        lab["experiments"] = [e for e in lab["experiments"] if e["id"] not in {cfg_id(c) for c in queue}]
    rnd = random.Random(now.toordinal())
    # najpierw ważne przepisy (wszystkie cechy), potem reszta w losowej kolejności
    queue.sort(key=lambda c: (c["feats"] != "wszystkie cechy", rnd.random()))
    rows = build_rows(prepped)
    new = []
    for cfg in queue[:budget]:
        res = evaluate(rows, cfg)
        e = {"id": cfg_id(cfg), "cfg": cfg, "time": now.isoformat(), "res": res, "score": score(res), "text": describe(cfg)}
        lab["experiments"].append(e); new.append(e)
        b = lab["best"].get(cfg["h"])
        if res and (not b or e["score"] > b["score"]):
            lab["best"][cfg["h"]] = e
            lab.setdefault("log", []).append({"t": now.isoformat(), "text":
                f"Nowy najlepszy przepis {('na jutro', 'na tydzień', 'na miesiąc')[list(HZ).index(cfg['h'])]}: trafność {res['acc']}% "
                f"(zawsze „wzrost”: {res['majority']}%)" + (f", strefa pewności: {res['sure']['acc']}% w {res['sure']['coverage']}% przypadków"
                if res["sure"] else "") + "."})
    lab["progress"].append({"t": now.isoformat(), "n": len(lab["experiments"]),
                            **{h: {"acc": b["res"]["acc"], "edge": b["res"]["edge"],
                                   "sel": (b["res"]["best_sel"] or {}).get("acc")} for h, b in lab["best"].items() if b.get("res")}})
    lab["progress"] = lab["progress"][-500:]
    lab["log"] = lab.get("log", [])[-100:]
    return new


def train_live(lab, prepped, now):
    """Trenuje najlepsze przepisy na wszystkich danych do dziś – do użycia na żywo."""
    rows = build_rows(prepped)
    live = {}
    for h, b in lab.get("best", {}).items():
        cfg = b["cfg"]; idx = FEATS[cfg["feats"]]
        last = rows[-1][0]
        train = [r for r in rows if (last - r[0]).days <= cfg["window"] and (last - r[0]).days > HZ[h] * 1.5]
        if len(train) > 15000:
            train = random.Random(3).sample(train, 15000)
        m = ml.fit([[r[2][j] for j in idx] for r in train], [1.0 if r[3][h] else 0.0 for r in train], lam=cfg["lam"], iters=6)
        live[h] = {"m": m, "idx": idx, "sure": b["res"].get("sure"), "id": b["id"], "acc": b["res"]["acc"]}
    lab["live"] = live; lab["live_date"] = now.date().isoformat()


def predict_live(lab, x):
    """Przewidywania najlepszych przepisów + czy to „pewny sygnał” (w strefie 65%)."""
    out = {}
    for h, L in (lab.get("live") or {}).items():
        p = ml.predict(L["m"], [x[j] for j in L["idx"]])
        s = L.get("sure")
        out[h] = {"p": round(100 * p, 1), "sure": bool(s and abs(p - 0.5) >= s["thr"]),
                  "sure_acc": s["acc"] if s else None}
    return out

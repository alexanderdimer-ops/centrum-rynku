"""Uczenie maszynowe w czystym Pythonie (bez dodatkowych bibliotek).

Model: regresja logistyczna z regularyzacją (metoda Newtona/IRLS), wspólna dla wszystkich instrumentów.
Uczy się na ~5 latach historii, z czego ostatni rok jest odłożony do uczciwego testu (model go nie widzi
podczas nauki). Przewiduje szansę, że cena będzie wyżej za 1 sesję i za 5 sesji (tydzień).
Model jest trenowany od nowa raz dziennie, więc cały czas uczy się na najnowszych danych.
"""
import json, math, statistics as st, datetime as dt

VERSION = 3
HORIZONS = {"1d": 1, "1w": 5, "1m": 21}
TEST = 250   # ostatnie sesje każdego instrumentu odkładamy do testu
LABELS = [  # nazwa cechy po polsku: (gdy cecha wysoka, gdy niska)
    ("Wynik ostatniej sesji", "duży wzrost w ostatniej sesji", "duży spadek w ostatniej sesji"),
    ("Ruch w ostatnim tygodniu", "mocny tydzień", "słaby tydzień"),
    ("Ruch w ostatnim miesiącu", "mocny miesiąc", "słaby miesiąc"),
    ("Ruch w ostatnim kwartale", "mocny kwartał", "słaby kwartał"),
    ("Odległość od średniej 20 dni", "cena wysoko nad średnią 20 dni", "cena nisko pod średnią 20 dni"),
    ("Odległość od średniej 50 dni", "cena wysoko nad średnią 50 dni", "cena nisko pod średnią 50 dni"),
    ("Odległość od średniej 200 dni", "cena wysoko nad średnią 200 dni", "cena nisko pod średnią 200 dni"),
    ("RSI", "wysoki RSI (przegrzanie)", "niski RSI (wyprzedanie)"),
    ("Zmienność teraz vs zwykle", "nerwowy rynek (duże wahania)", "spokojny rynek"),
    ("Obrót vs zwykle", "duży obrót", "mały obrót"),
    ("Pozycja w zakresie 20 dni", "cena przy szczycie z 20 dni", "cena przy dołku z 20 dni"),
    ("Odległość od rocznego szczytu", "cena blisko rocznego szczytu", "cena daleko pod rocznym szczytem"),
    ("Rynek odniesienia – tydzień", "szeroki rynek mocny w tygodniu", "szeroki rynek słaby w tygodniu"),
    ("Rynek odniesienia – trend", "szeroki rynek w trendzie wzrostowym", "szeroki rynek w trendzie spadkowym"),
    ("Korpus ostatniej świecy", "silna świeca wzrostowa", "silna świeca spadkowa"),
    ("Górny cień świecy", "długi górny cień (odrzucenie wyższych cen)", "brak górnego cienia"),
    ("Dolny cień świecy", "długi dolny cień (odrzucenie niższych cen)", "brak dolnego cienia"),
]


def _roll(x, n):
    out, s = [None] * len(x), 0.0
    for k, v in enumerate(x):
        s += v
        if k >= n: s -= x[k - n]
        if k >= n - 1: out[k] = s / n
    return out


def prep(H, rc=None):
    """Przygotowuje szeregi pomocnicze dla jednego instrumentu (liczone raz, potem szybkie cechy)."""
    c, o, h, l = H["c"], H["o"], H["h"], H["l"]
    v = H.get("v") or [0] * len(c)
    n = len(c)
    r = [0.0] + [c[k] / c[k - 1] - 1 for k in range(1, n)]
    r2 = [x * x for x in r]
    m20, q20, m120, q120 = _roll(r, 20), _roll(r2, 20), _roll(r, 120), _roll(r2, 120)
    sd20 = [None if m20[k] is None else math.sqrt(max(q20[k] - m20[k] ** 2, 1e-10)) for k in range(n)]
    sd120 = [None if m120[k] is None else math.sqrt(max(q120[k] - m120[k] ** 2, 1e-10)) for k in range(n)]
    g = [0.0] + [max(c[k] - c[k - 1], 0) for k in range(1, n)]
    ls = [0.0] + [max(c[k - 1] - c[k], 0) for k in range(1, n)]
    G, L = _roll(g, 14), _roll(ls, 14)
    P = {"c": c, "o": o, "h": h, "l": l, "v": v, "r": r, "sd20": sd20, "sd120": sd120,
         "s20": _roll(c, 20), "s50": _roll(c, 50), "s200": _roll(c, 200), "vm": _roll(v, 20), "G": G, "L": L,
         "rc": rc, "rs20": _roll(rc, 20) if rc else None}
    if rc:
        rr = [0.0] + [rc[k] / rc[k - 1] - 1 for k in range(1, n)]
        mm, qq = _roll(rr, 60), _roll([x * x for x in rr], 60)
        P["rsd"] = [None if mm[k] is None else math.sqrt(max(qq[k] - mm[k] ** 2, 1e-10)) for k in range(n)]
    return P


def feat(P, i):
    c, h, l, o = P["c"], P["h"], P["l"], P["o"]
    if i < 260 or P["s200"][i] is None or P["sd120"][i] is None:
        return None
    sd = max(P["sd20"][i], 1e-4)
    rsi = 100 if P["L"][i] == 0 else 100 - 100 / (1 + P["G"][i] / P["L"][i])
    hi20, lo20 = max(h[i - 19:i + 1]), min(l[i - 19:i + 1])
    hi252 = max(h[i - 251:i + 1])
    rng = max(h[i] - l[i], 1e-12)
    vm = P["vm"][i]
    vol = math.log(P["v"][i] / vm) if vm and P["v"][i] else 0.0
    if P["rc"] and P["rsd"][i]:
        rc = P["rc"]; ref5 = (rc[i] / rc[i - 5] - 1) / (P["rsd"][i] * math.sqrt(5)); reft = 1.0 if rc[i] > P["rs20"][i] else -1.0
    else:
        ref5, reft = 0.0, 0.0
    f = [P["r"][i] / sd,
         (c[i] / c[i - 5] - 1) / (sd * math.sqrt(5)),
         (c[i] / c[i - 20] - 1) / (sd * math.sqrt(20)),
         (c[i] / c[i - 60] - 1) / (sd * math.sqrt(60)),
         (c[i] / P["s20"][i] - 1) / sd,
         (c[i] / P["s50"][i] - 1) / (sd * 3),
         (c[i] / P["s200"][i] - 1) / (sd * 8),
         (rsi - 50) / 50,
         P["sd20"][i] / P["sd120"][i] - 1,
         max(-3.0, min(3.0, vol)),
         (c[i] - lo20) / max(hi20 - lo20, 1e-12) - 0.5,
         (c[i] / hi252 - 1) / (sd * 16),
         max(-4.0, min(4.0, ref5)), reft,
         (c[i] - o[i]) / rng,
         (h[i] - max(o[i], c[i])) / rng,
         (min(o[i], c[i]) - l[i]) / rng]
    return [max(-6.0, min(6.0, x)) for x in f]


def _solve(A, b):
    n = len(b); M = [row[:] + [b[k]] for k, row in enumerate(A)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r_: abs(M[r_][col]))
        M[col], M[piv] = M[piv], M[col]
        if abs(M[col][col]) < 1e-12:
            continue
        for r_ in range(n):
            if r_ != col and M[r_][col]:
                f = M[r_][col] / M[col][col]
                M[r_] = [a - f * b_ for a, b_ in zip(M[r_], M[col])]
    return [M[k][n] / M[k][k] if abs(M[k][k]) > 1e-12 else 0.0 for k in range(n)]


def _sig(z): return 1 / (1 + math.exp(-max(-30, min(30, z))))


def fit(X, y, lam=5.0, iters=7):
    """Regresja logistyczna z karą za zbyt duże wagi (chroni przed „uczeniem się na pamięć”)."""
    d = len(X[0]) + 1
    mu = [st.fmean(col) for col in zip(*X)]
    sdv = [st.pstdev(col) or 1.0 for col in zip(*X)]
    Z = [[1.0] + [(a - m) / s for a, m, s in zip(x, mu, sdv)] for x in X]
    w = [0.0] * d
    for _ in range(iters):
        Hm = [[0.0] * d for _ in range(d)]; g = [0.0] * d
        for z, t in zip(Z, y):
            p = _sig(sum(a * b for a, b in zip(w, z))); r = p * (1 - p); e = p - t
            for a in range(d):
                za = z[a]; g[a] += e * za; ra = r * za; row = Hm[a]
                for b in range(a, d):
                    row[b] += ra * z[b]
        for a in range(d):
            for b in range(a):
                Hm[a][b] = Hm[b][a]
        for a in range(1, d):
            Hm[a][a] += lam; g[a] += lam * w[a]
        step = _solve(Hm, g)
        w = [a - b for a, b in zip(w, step)]
    return {"w": w, "mu": mu, "sd": sdv}


def predict(m, x):
    z = [1.0] + [(a - mu) / s for a, mu, s in zip(x, m["mu"], m["sd"])]
    return _sig(sum(a * b for a, b in zip(m["w"], z)))


def explain(m, x, k=3):
    """Które cechy najbardziej podniosły / obniżyły szansę w tej konkretnej sytuacji."""
    z = [(a - mu) / s for a, mu, s in zip(x, m["mu"], m["sd"])]
    contrib = sorted(((m["w"][j + 1] * z[j], j) for j in range(len(z))), key=lambda t: t[0])
    def txt(c_, j): return LABELS[j][1] if z[j] > 0 else LABELS[j][2]
    return {"plus": [txt(c_, j) for c_, j in contrib[::-1][:k] if c_ > 0.02],
            "minus": [txt(c_, j) for c_, j in contrib[:k] if c_ < -0.02]}


def lessons(m, k=5):
    """Czego model się nauczył – największe wagi przełożone na zdania."""
    out = []
    for j in sorted(range(len(LABELS)), key=lambda j: -abs(m["w"][j + 1]))[:k]:
        w = m["w"][j + 1]
        out.append(f"Gdy {LABELS[j][1]}, cena częściej {'rosła' if w > 0 else 'spadała'} w kolejnych dniach."
                   if abs(w) > 0.01 else "")
    return [x for x in out if x]


def _metrics(m, X, y, base):
    ps = [predict(m, x) for x in X]
    acc = sum((p > 0.5) == t for p, t in zip(ps, y)) / len(y)
    brier = sum((p - t) ** 2 for p, t in zip(ps, y)) / len(y)
    brier0 = sum((base - t) ** 2 for t in y) / len(y)
    strong = [(p, t) for p, t in zip(ps, y) if abs(p - 0.5) > 0.04]
    s_acc = sum((p > 0.5) == t for p, t in strong) / len(strong) if len(strong) > 30 else None
    majority = max(sum(y), len(y) - sum(y)) / len(y)
    return {"acc": round(acc * 100, 1), "majority": round(majority * 100, 1), "n": len(y),
            "skill": round((1 - brier / brier0) * 100, 2) if brier0 else 0,
            "strong_acc": None if s_acc is None else round(s_acc * 100, 1), "strong_n": len(strong)}


def train(prepped, today, old=None):
    """prepped: lista (symbol, P). Zwraca modele dla każdego horyzontu z wynikami uczciwego testu."""
    if old and old.get("date") == today and old.get("v") == VERSION:
        return old
    out = {"date": today, "v": VERSION}
    for name, hz in HORIZONS.items():
        Xtr, ytr, Xte, yte = [], [], [], []
        for _, P in prepped:
            n = len(P["c"])
            for i in range(260, n - hz):
                x = feat(P, i)
                if x is None:
                    continue
                t = 1.0 if P["c"][i + hz] > P["c"][i] else 0.0
                if i < n - hz - TEST - hz:
                    Xtr.append(x); ytr.append(t)
                elif i >= n - hz - TEST:
                    Xte.append(x); yte.append(t)
        if len(Xtr) < 500 or len(Xte) < 100:
            continue
        m_test = fit(Xtr, ytr)
        test = _metrics(m_test, Xte, yte, sum(ytr) / len(ytr))
        full = fit(Xtr + Xte, ytr + yte)  # model do bieżących przewidywań: wszystkie dane
        out[name] = dict(full, test=test, n_train=len(Xtr) + len(Xte), lessons=lessons(full))
    return out


def blend_weight(test):
    """Ile ufać modelowi: zależy od wyniku na odłożonych danych (0 = wcale, maks. 0,7)."""
    if not test:
        return 0.0
    edge = (test["acc"] - max(50.0, test["majority"])) / 100
    return round(max(0.0, min(0.7, 0.2 + edge * 10)) if test["skill"] > 0 else 0.0, 2)


LIVE_LABELS = [x[0] for x in LABELS] + ["Nastrój newsów (7 dni)", "Potencjał krótko", "Potencjał średnio",
                                        "Potencjał długo", "Cena docelowa analityków", "Pozycje funduszy (COT)", "Ocena strony"]


def train_live(tr, old=None, min_n=300):
    """Drugi model uczony na własnych, rozliczonych przewidywaniach strony – z cechami, których nie ma
    w starej historii cen (newsy, potencjał, analitycy, COT, ocena strony). Działa, gdy uzbiera się dość danych."""
    out = {"summary": {}}
    for h in ("1d", "1w"):
        rows = sorted((p for p in tr.get("preds", []) if p.get("h") == h and p.get("res") is not None and p.get("f")),
                      key=lambda p: p["t"])
        out["summary"][h] = {"n": len(rows), "need": min_n}
        if len(rows) < min_n:
            continue
        X = [p["f"] for p in rows]; y = [1.0 if p["up"] else 0.0 for p in rows]
        cut = int(len(rows) * 0.7)
        m_test = fit(X[:cut], y[:cut], lam=20.0)
        test = _metrics(m_test, X[cut:], y[cut:], sum(y[:cut]) / cut)
        full = fit(X, y, lam=20.0)
        out[h] = dict(full, test=test)
        out["summary"][h].update(test=test, weight=blend_weight(test))
    return out

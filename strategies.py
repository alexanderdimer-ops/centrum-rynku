"""Samodzielne wyszukiwanie strategii (reguł) dla każdego instrumentu.

Strona sama tworzy setki prostych hipotez, np.:
  „w piątki od otwarcia do zamknięcia cena rośnie”, „po dwóch spadkowych sesjach następna jest wzrostowa”,
  „gdy pierwsza godzina handlu jest wzrostowa, to do końca dnia cena dalej rośnie”.
Każdą sprawdza uczciwie w trzech krokach na danych z różnych okresów:
  1) odkrycie (najstarsze 60% danych), 2) potwierdzenie (kolejne 20%), 3) test (najnowsze 20%, nieużywane wcześniej).
Reguła trafia na listę tylko, gdy przejdzie 1) i 2). Wynik 3) pokazujemy uczciwie, a potem reguła jest
śledzona na żywo (track.py) – jeśli przestaje działać, zostaje odrzucona.
Wiele hipotez naraz = ryzyko przypadkowych „odkryć”, dlatego progi są ostre (min. liczba przypadków, test statystyczny).
"""
import math, statistics as st, datetime as dt

WD = ["w poniedziałki", "we wtorki", "w środy", "w czwartki", "w piątki", "w soboty", "w niedziele"]
WD1 = ["poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela"]
TARGETS = {"intra": "od otwarcia do zamknięcia tej samej sesji",
           "next": "na następnej sesji (od zamknięcia do zamknięcia)",
           "week": "w ciągu tygodnia (5 sesji)",
           "rest": "od końca pierwszej godziny do zamknięcia sesji"}
MIN_DISC, MIN_VAL = 30, 10


def _sma(c, i, n): return sum(c[i - n + 1:i + 1]) / n

def _rsi(c, i, n=14):
    g = sum(max(c[k] - c[k - 1], 0) for k in range(i - n + 1, i + 1))
    l = sum(max(c[k - 1] - c[k], 0) for k in range(i - n + 1, i + 1))
    return 100 if l == 0 else 100 - 100 / (1 + g / l)


def conditions(H, rc, j):
    """Warunki znane na koniec sesji j (wszystko, co wiadomo przed następną decyzją)."""
    c, h, l = H["c"], H["h"], H["l"]
    r = c[j] / c[j - 1] - 1
    sd = st.pstdev([c[k] / c[k - 1] - 1 for k in range(j - 19, j + 1)]) or 1e-4
    rs = _rsi(c, j)
    lo20, hi20 = min(l[j - 19:j + 1]), max(h[j - 19:j + 1])
    pos = (c[j] - lo20) / max(hi20 - lo20, 1e-12)
    out = {
        "prev_up": (r > 0, "poprzednia sesja była wzrostowa"),
        "prev_down": (r < 0, "poprzednia sesja była spadkowa"),
        "two_down": (r < 0 and c[j - 1] < c[j - 2], "dwie ostatnie sesje były spadkowe"),
        "two_up": (r > 0 and c[j - 1] > c[j - 2], "dwie ostatnie sesje były wzrostowe"),
        "three_down": (r < 0 and c[j - 1] < c[j - 2] and c[j - 2] < c[j - 3], "trzy ostatnie sesje były spadkowe"),
        "big_up": (r > 1.5 * sd, "poprzednia sesja miała duży wzrost"),
        "big_down": (r < -1.5 * sd, "poprzednia sesja miała duży spadek"),
        "rsi_low": (rs < 30, "RSI poniżej 30 (wyprzedanie)"),
        "rsi_high": (rs > 70, "RSI powyżej 70 (przegrzanie)"),
        "above50": (c[j] > _sma(c, j, 50), "cena nad średnią z 50 dni"),
        "below50": (c[j] < _sma(c, j, 50), "cena pod średnią z 50 dni"),
        "above200": (c[j] > _sma(c, j, 200), "cena nad średnią z 200 dni"),
        "below200": (c[j] < _sma(c, j, 200), "cena pod średnią z 200 dni"),
        "near_low": (pos < 0.15, "cena przy dołku z 20 sesji"),
        "near_high": (pos > 0.85, "cena przy szczycie z 20 sesji"),
    }
    if rc and rc[j - 1]:
        rr = rc[j] / rc[j - 1] - 1
        out["ref_up"] = (rr > 0, "szeroki rynek wzrósł na poprzedniej sesji")
        out["ref_down"] = (rr < 0, "szeroki rynek spadł na poprzedniej sesji")
    return out


def _z(hits, n, p0=0.5):
    return (hits - n * p0) / math.sqrt(n * p0 * (1 - p0)) if n else 0


def _samples(H, rc, hourly):
    """Lista obserwacji: (indeks, typ celu, słownik warunków, wynik True/False)."""
    c, o, d = H["c"], H["o"], H["d"]
    n = len(c)
    rows = []
    for i in range(205, n):
        j = i - 1
        cond = conditions(H, rc, j)
        wd = d[i].weekday()
        sd = st.pstdev([c[k] / c[k - 1] - 1 for k in range(j - 19, j + 1)]) or 1e-4
        gap = o[i] / c[j] - 1
        base = {k: v[0] for k, v in cond.items()}
        base["wd"] = wd
        base["gap_up"] = gap > 0.3 * sd
        base["gap_down"] = gap < -0.3 * sd
        base["mstart"] = d[i].month != d[j].month
        base["mend"] = i + 1 < n and d[i + 1].month != d[i].month
        if abs(c[i] - o[i]) > 1e-12:  # od otwarcia do zamknięcia sesji i
            rows.append((i, "intra", base, c[i] > o[i]))
        # na następną sesję / tydzień: decyzja po zamknięciu sesji i
        if i + 1 < n and i >= 206:
            cond2 = {k: v[0] for k, v in conditions(H, rc, i).items()}
            cond2["wd"] = d[i + 1].weekday()
            cond2["mstart"] = d[i + 1].month != d[i].month
            cond2["mend"] = i + 2 < n and d[i + 2].month != d[i + 1].month
            if c[i + 1] != c[i]:
                rows.append((i, "next", cond2, c[i + 1] > c[i]))
            if i + 5 < n and c[i + 5] != c[i]:
                rows.append((i, "week", dict(cond2, wd=d[i].weekday()), c[i + 5] > c[i]))
    if hourly:  # pierwsza godzina handlu → reszta dnia
        idx = {day: k for k, day in enumerate(d)}
        for day, (o1, c1, close, wd) in hourly.items():
            if day not in idx or abs(close - c1) < 1e-12 or abs(c1 - o1) < 1e-12:
                continue
            k = idx[day]
            if k < 21: continue
            sd = st.pstdev([c[q] / c[q - 1] - 1 for q in range(k - 20, k)]) or 1e-4
            fh = c1 / o1 - 1
            gap = o1 / c[k - 1] - 1
            rows.append((k, "rest", {"fh_up": fh > 0, "fh_down": fh < 0, "fh_strong_up": fh > 0.5 * sd,
                                      "fh_strong_down": fh < -0.5 * sd, "wd": wd, "gap_up": gap > 0.3 * sd,
                                      "gap_down": gap < -0.3 * sd}, close > c1))
    return rows


EXTRA_TXT = {"gap_up": "sesja otworzyła się luką w górę", "gap_down": "sesja otworzyła się luką w dół",
             "mstart": "pierwsza sesja miesiąca", "mend": "ostatnia sesja miesiąca",
             "fh_up": "pierwsza godzina była wzrostowa", "fh_down": "pierwsza godzina była spadkowa",
             "fh_strong_up": "pierwsza godzina mocno wzrostowa", "fh_strong_down": "pierwsza godzina mocno spadkowa"}


WD_NEXT = ["gdy następna sesja to poniedziałek", "gdy następna sesja to wtorek", "gdy następna sesja to środa",
           "gdy następna sesja to czwartek", "gdy następna sesja to piątek", "gdy następna sesja to sobota",
           "gdy następna sesja to niedziela"]
WD_BUY = ["przy zakupie na zamknięciu w poniedziałek", "przy zakupie na zamknięciu we wtorek",
          "przy zakupie na zamknięciu w środę", "przy zakupie na zamknięciu w czwartek",
          "przy zakupie na zamknięciu w piątek", "przy zakupie w sobotę", "przy zakupie w niedzielę"]


def describe_rule(key, typ, labels):
    parts = []
    for k in key:
        if k.startswith("wd="):
            w = int(k[3:])
            parts.append(WD_NEXT[w] if typ == "next" else WD_BUY[w] if typ == "week" else WD[w])
        else:
            parts.append("gdy " + (EXTRA_TXT.get(k) or labels.get(k, k)))
    return ", ".join(parts)


def discover(H, rc, hourly=None):
    rows = _samples(H, rc, hourly)
    if len(rows) < 300:
        return {"rules": [], "weekday": {}, "tested": 0}
    labels = {k: v[1] for k, v in conditions(H, rc, len(H["c"]) - 1).items()}
    by_t = {}
    for r in rows:
        by_t.setdefault(r[1], []).append(r)
    rules, tested = [], 0
    weekday = {}
    for typ, R in by_t.items():
        R.sort(key=lambda x: x[0])
        n = len(R)
        a, b = int(n * 0.6), int(n * 0.8)
        seg = (R[:a], R[a:b], R[b:])
        base = [sum(x[3] for x in S) / max(1, len(S)) for S in seg]
        # tabela dni tygodnia (do weryfikacji „mitów”, np. „w piątki rośnie”)
        if typ in ("intra", "next", "rest"):
            wtab = {}
            for w in range(7):
                sel = [x[3] for x in R if x[2]["wd"] == w]
                if len(sel) >= 20:
                    wtab[w] = {"n": len(sel), "up": round(100 * sum(sel) / len(sel), 1),
                               "recent_up": round(100 * sum(sel[-50:]) / len(sel[-50:]), 1)}
            weekday[typ] = wtab
        keys = sorted({k for x in R for k, v in x[2].items() if k != "wd" and isinstance(v, bool)})
        cands = [(k,) for k in keys] + [("wd=%d" % w,) for w in range(7)]
        if typ in ("intra", "next", "rest"):
            cands += [("wd=%d" % w, k) for w in range(7) for k in keys]
        for cand in cands:
            def match(x):
                for k in cand:
                    if k.startswith("wd="):
                        if x[2]["wd"] != int(k[3:]): return False
                    elif not x[2].get(k): return False
                return True
            stats = []
            for S in seg:
                sel = [x[3] for x in S if match(x)]
                stats.append((len(sel), sum(sel)))
            (n1, u1), (n2, u2), (n3, u3) = stats
            if n1 < MIN_DISC:
                continue
            tested += 1
            up = u1 / n1 >= 0.5
            h1, h2, h3 = (u1, u2, u3) if up else (n1 - u1, n2 - u2, n3 - u3)
            acc1 = h1 / n1
            b1 = base[0] if up else 1 - base[0]
            if acc1 < 0.6 or _z(h1, n1) < 2.6 or acc1 < b1 + 0.04:
                continue  # odkrycie: trafność ≥ 60%, istotna statystycznie i lepsza od „zawsze w tę stronę”
            if n2 < MIN_VAL or h2 / n2 < 0.55:
                continue  # potwierdzenie na późniejszych danych
            total_n, total_h = n1 + n2 + n3, h1 + h2 + h3
            rules.append({"id": typ + ":" + "+".join(cand), "type": typ, "key": list(cand), "dir": "up" if up else "down",
                          "text": describe_rule(cand, typ, labels), "target": TARGETS[typ],
                          "disc": [n1, round(100 * acc1, 1)], "val": [n2, round(100 * h2 / n2, 1)],
                          "test": [n3, round(100 * h3 / n3, 1) if n3 else None],
                          "all": [total_n, round(100 * total_h / total_n, 1)],
                          "base": round(100 * (base[2] if up else 1 - base[2]), 1),
                          "status": ("ok" if n3 >= 8 and h3 / n3 >= 0.55 else "fail" if n3 >= 8 and h3 / n3 < 0.5 else "weak")})
    # najlepsze najpierw: wynik testu (dane nieużyte przy odkryciu), potem liczba przypadków
    rules.sort(key=lambda r: (-(r["test"][1] or 0) if r["test"][0] >= 5 else 0, -r["all"][0]))
    return {"rules": rules[:25], "weekday": weekday, "tested": tested}


def hourly_days(get_json, chart_url, sym):
    """Pierwsza godzina i zamknięcie dla każdego dnia z ~2 lat danych godzinowych."""
    d = get_json(chart_url(sym, "730d", "60m"), ttl=43200)["chart"]["result"][0]
    q = d["indicators"]["quote"][0]
    days = {}
    for t, o, c in zip(d.get("timestamp") or [], q["open"], q["close"]):
        if c is None or o is None: continue
        day = dt.datetime.fromtimestamp(t, dt.timezone.utc).date()
        days.setdefault(day, []).append((t, o, c))
    out = {}
    for day, bars in days.items():
        bars.sort()
        if len(bars) >= 4:
            out[day] = (bars[0][1], bars[0][2], bars[-1][2], day.weekday())
    return out


def triggered(rules, H, rc, first_hour=None, session_live=False):
    """Które reguły działają teraz. session_live: dzisiejsza sesja trwa (ostatnia świeca jest niepełna)."""
    c, o, d = H["c"], H["o"], H["d"]
    n = len(c)
    out = []
    today_in_data = session_live
    j_done = n - 2 if today_in_data else n - 1  # ostatnia zakończona sesja
    cond = {k: v[0] for k, v in conditions(H, rc, j_done).items()}
    sd = st.pstdev([c[k] / c[k - 1] - 1 for k in range(j_done - 19, j_done + 1)]) or 1e-4
    for r in rules:
        ctx = dict(cond)
        if r["type"] == "intra":
            if not today_in_data: continue  # reguła na dzisiejszą sesję – dopiero gdy znamy otwarcie
            ctx["wd"] = d[-1].weekday(); gap = o[-1] / c[j_done] - 1
            ctx["gap_up"], ctx["gap_down"] = gap > 0.3 * sd, gap < -0.3 * sd
            ctx["mstart"] = d[-1].month != d[j_done].month; ctx["mend"] = False
            when, entry = "dziś", o[-1]
        elif r["type"] == "rest":
            if not first_hour: continue
            o1, c1 = first_hour
            fh = c1 / o1 - 1; gap = o1 / c[j_done] - 1
            ctx = {"fh_up": fh > 0, "fh_down": fh < 0, "fh_strong_up": fh > 0.5 * sd, "fh_strong_down": fh < -0.5 * sd,
                   "wd": d[-1].weekday(), "gap_up": gap > 0.3 * sd, "gap_down": gap < -0.3 * sd}
            when, entry = "dziś (po pierwszej godzinie)", c1
        else:
            if today_in_data: continue  # na następną sesję – liczymy po zamknięciu dzisiejszej
            nxt = d[-1] + dt.timedelta(days=1)
            while nxt.weekday() > 4: nxt += dt.timedelta(days=1)
            ctx["wd"] = nxt.weekday() if r["type"] == "next" else d[-1].weekday()
            ctx["mstart"] = nxt.month != d[-1].month; ctx["mend"] = False
            when, entry = ("na następnej sesji" if r["type"] == "next" else "w ciągu tygodnia"), c[-1]
        ok = all((ctx.get("wd") == int(k[3:])) if k.startswith("wd=") else bool(ctx.get(k)) for k in r["key"])
        if ok:
            out.append({"id": r["id"], "type": r["type"], "dir": r["dir"], "text": r["text"], "target": r["target"],
                        "when": when, "entry": entry, "acc": r["test"][1] if r["test"][0] >= 5 else r["all"][1],
                        "n": r["all"][0]})
    return out

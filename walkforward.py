"""„Gra w przewidywanie” na historii (test kroczący, walk-forward).

Strona cofa się w czasie i idzie do przodu, kwartał po kwartale:
  1) uczy się TYLKO na danych sprzed danego momentu (nie widzi przyszłości),
  2) przewiduje wzrost/spadek na kolejny kwartał dla wszystkich instrumentów (jutro i za tydzień),
  3) sprawdza, co naprawdę się stało, dopisuje te dane do nauki i przesuwa się dalej.
Nigdy nie wraca do tych samych momentów, żeby „poprawić wynik” – to byłoby uczenie się odpowiedzi na pamięć.
Wynik: uczciwa skuteczność w procentach, krzywa nauki (czy z czasem jest lepiej) i momenty do gry dla użytkownika.
"""
import random, statistics as st
import ml

STEP = 63          # co ile sesji model uczy się od nowa (ok. kwartał)
WINDOW_DAYS = 1100 # uczy się na ostatnich ~3 latach przed danym momentem
MAX_ROWS = 12000   # ograniczenie, żeby test trwał krótko


def _tech_signal(P, i):
    """Warunki wzrostu z zakładki „Decyzja” (bez danych z przyszłości)."""
    c, h = P["c"], P["h"]
    rsi = 100 if P["L"][i] == 0 else 100 - 100 / (1 + P["G"][i] / P["L"][i])
    ok = [c[i] > P["s50"][i], c[i] > P["s20"][i], 50 <= rsi <= 70, c[i] > max(h[i - 20:i])]
    if P["rc"]:
        ok.append(P["rc"][i] > P["rs20"][i])
    return sum(ok) >= len(ok) - 1


def run(prepped, own, seed=7):
    """prepped: lista (symbol, P, daty). own: symbole z listy użytkownika (dla nich zapisujemy momenty do gry)."""
    rows = []
    for sym, P, days in prepped:
        c, n = P["c"], len(P["c"])
        for i in range(260, n - 20):
            x = ml.feat(P, i)
            if x is None or c[i + 1] == c[i] or c[i + 5] == c[i]:
                continue
            rows.append((days[i], sym, i, x, c[i + 1] > c[i], c[i + 5] > c[i], c[i + 5] / c[i] - 1, c[i + 20] / c[i] - 1,
                         _tech_signal(P, i)))
    rows.sort(key=lambda r: r[0])
    dates = sorted({r[0] for r in rows})
    if len(dates) < 700:
        return None
    start = dates[500]  # pierwsze ~2 lata tylko do nauki
    blocks = [d for k, d in enumerate(dates) if d >= start and (k - 500) % STEP == 0]
    rnd = random.Random(seed)
    preds = []
    for b, b0 in enumerate(blocks):
        b1 = blocks[b + 1] if b + 1 < len(blocks) else None
        lim = dates[max(0, dates.index(b0) - 6)]  # przerwa, żeby wynik tygodniowy nie „przeciekł” do nauki
        train = [r for r in rows if r[0] < lim and (b0 - r[0]).days <= WINDOW_DAYS]
        if len(train) > MAX_ROWS:
            train = rnd.sample(train, MAX_ROWS)
        X = [r[3] for r in train]
        m1 = ml.fit(X, [1.0 if r[4] else 0.0 for r in train], lam=50.0, iters=5)
        m5 = ml.fit(X, [1.0 if r[5] else 0.0 for r in train], lam=50.0, iters=5)
        for r in rows:
            if r[0] >= b0 and (b1 is None or r[0] < b1):
                preds.append((r, ml.predict(m1, r[3]), ml.predict(m5, r[3])))
    return summarize(preds, own, rnd)


def _acc(pairs):
    return round(100 * sum(p == y for p, y in pairs) / len(pairs), 1) if pairs else None


def summarize(preds, own, rnd):
    def block(sel):
        if not sel:
            return None
        return {"n": len(sel),
                "acc_1d": _acc([(p1 > 0.5, r[4]) for r, p1, _ in sel]),
                "acc_1w": _acc([(p5 > 0.5, r[5]) for r, _, p5 in sel]),
                "up_1d": round(100 * sum(r[4] for r, _, _ in sel) / len(sel), 1),
                "up_1w": round(100 * sum(r[5] for r, _, _ in sel) / len(sel), 1)}
    out = {"all": block(preds)}
    # pewne przewidywania: 10% najbardziej zdecydowanych
    srt = sorted(preds, key=lambda t: -abs(t[2] - 0.5))
    top = srt[:max(1, len(srt) // 10)]
    out["confident_1w"] = {"n": len(top), "acc": _acc([(p5 > 0.5, r[5]) for r, _, p5 in top])}
    # sygnały strony z zakładki „Decyzja”: gdy warunki wzrostu były spełnione
    sig = [t for t in preds if t[0][8]]
    out["signals"] = {"n": len(sig), "acc_1w": _acc([(True, r[5]) for r, _, _ in sig]),
                      "avg_1w": round(100 * st.fmean(r[6] for r, _, _ in sig), 2) if sig else None,
                      "avg_all": round(100 * st.fmean(r[6] for r, _, _ in preds), 2)}
    # połączenie: model + warunki (wejście tylko, gdy oba mówią „wzrost”)
    both = [t for t in sig if t[2] > 0.55]
    out["combo"] = {"n": len(both), "acc_1w": _acc([(True, r[5]) for r, _, _ in both]),
                    "avg_1w": round(100 * st.fmean(r[6] for r, _, _ in both), 2) if both else None}
    # krzywa nauki: wynik w kolejnych półroczach (czy z czasem i większą ilością danych jest lepiej)
    halves = {}
    for t in preds:
        d = t[0][0]; halves.setdefault(f"{d.year} {'I' if d.month <= 6 else 'II'} półrocze", []).append(t)
    out["curve"] = [dict(period=k, **block(v)) for k, v in sorted(halves.items(), key=lambda kv: (kv[0][:4], kv[0][5:]))]
    # według instrumentu
    per = {}
    for t in preds:
        per.setdefault(t[0][1], []).append(t)
    out["per_sym"] = {s: block(v) for s, v in per.items() if s in own}
    # momenty do gry dla użytkownika (instrumenty z listy)
    game = []
    for s, v in per.items():
        if s not in own:
            continue
        for r, p1, p5 in rnd.sample(v, min(40, len(v))):
            game.append({"s": s, "d": r[0].isoformat(), "p": round(p5 * 100, 1), "up": r[5], "ret5": round(r[6], 4),
                         "ret20": round(r[7], 4), "sig": r[8]})
    rnd.shuffle(game)
    out["game"] = game[:400]
    out["period"] = [preds[0][0][0].isoformat(), preds[-1][0][0].isoformat()] if preds else None
    return out

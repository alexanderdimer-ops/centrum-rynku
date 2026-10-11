"""Pobiera ceny i newsy, sam je analizuje i zapisuje wynik do data.json.

Wszystko z darmowych źródeł bez kluczy API:
- ceny dzienne z 5 lat: Yahoo Finance (instrumenty + rynki odniesienia),
- newsy: Google News RSS (świat po angielsku i Polska) + Bankier.pl RSS.
"""
import json, math, re, sys, statistics as st, urllib.request, urllib.parse, datetime as dt
import email.utils
import xml.etree.ElementTree as ET
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")

UA = {"User-Agent": "Mozilla/5.0"}
NOW = dt.datetime.now(dt.timezone.utc)
W = 500   # ile sesji wstecz biorą metody statystyczne (ok. 2 lata)
BT = 250  # ile ostatnich sesji sprawdza test skuteczności (ok. 1 rok)

BANKIER = ["https://www.bankier.pl/rss/wiadomosci.xml", "https://www.bankier.pl/rss/gielda.xml",
           "https://www.bankier.pl/rss/firma.xml", "https://www.bankier.pl/rss/espi.xml",
           "https://www.bankier.pl/rss/waluty.xml"]
POS = ["wzrost", "wzrosł", "rośnie", "rosną", "zysk", "rekord", "odbici", "dywidend", "poprawa", "przejęci",
       "umocni", "zwyżk", "drożej", "podwyżk", "rekomendacj kupuj",
       "surge", "soar", "rall", "jump", "gain", "rise", "rising", "record", "beat", "upgrade", "bullish",
       "boost", "strong", "growth", "rebound", "recover", "outperform", "higher", "climb", "advance"]
NEG = ["spadek", "spadk", "spada", "spadł", "strata", "strat", "obaw", "kryzys", "przecen", "cięci", "kara",
       "pozew", "wyprzedaż", "załamani", "osłabi", "taniej", "ryzyk", "zwolnie",
       "fall", "drop", "plunge", "slump", "declin", "loss", "miss", "downgrade", "bearish", "weak", "fear",
       "crash", "tumble", "lawsuit", "probe", "sell-off", "selloff", "slide", "lower", "recession", "warn",
       "sink", "slip", "concern", "risk"]
STOP = set("""the and for with from that this will are was its has have after over into amid as at by on in of to
a an is be it or not new says said how why what when who more than could would can may just about price prices stock stocks
shares share today week year years market markets news update latest live vs per amid ahead first his her their our
you your out off up down all also near high low here there they them were been being had does did percent analysts
oraz jest się nie dla przez jak już ale czy też tak pod nad przy jego jej ich które który która tego tym jako może
będzie są był była było bardzo tylko roku dziś cena ceny kurs akcje akcji spółka spółki rynek rynku proc
january february march april june july august september october november december monday tuesday wednesday
thursday friday saturday sunday stycznia lutego marca kwietnia maja czerwca lipca sierpnia września października
listopada grudnia poniedziałek wtorek środa czwartek piątek sobota niedziela""".split())
REF_NAMES = {"ETFBW20TR.WA": "WIG20", "^IXIC": "Nasdaq", "DX-Y.NYB": "indeks dolara", "^GSPC": "S&P 500",
             "^VIX": "VIX (indeks strachu)"}
PULSE = [("^GSPC", "S&P 500"), ("^IXIC", "Nasdaq"), ("ETFBW20TR.WA", "WIG20 (ETF)"),
         ("^VIX", "VIX – indeks strachu"), ("PLN=X", "USD/PLN"), ("DX-Y.NYB", "Indeks dolara")]


# ---------- pomocnicze ----------
def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read()

def phi(x): return 0.5 * (1 + math.erf(x / math.sqrt(2)))
def clamp(p): return round(max(5, min(95, p)), 1)
def mean(x): return sum(x) / len(x)

def fp(x):
    """Cena po polsku: spacja tysięcy, przecinek dziesiętny."""
    d = 0 if abs(x) >= 1000 else 2 if abs(x) >= 2 else 4
    return f"{x:,.{d}f}".replace(",", " ").replace(".", ",")

def fpc(x):
    """Zmiana procentowa ze znakiem, x jako ułamek."""
    return f"{x * 100:+.1f}%".replace(".", ",")

def pct1(x):
    """Procent bez znaku, x jako ułamek."""
    return f"{x * 100:.1f}%".replace(".", ",")

def verdict(p):
    return ("good", "Sprzyjające warunki") if p >= 58 else ("mid", "Neutralnie – czekaj na sygnał") if p >= 46 \
        else ("bad", "Niekorzystne warunki")


# ---------- ceny ----------
_cache = {}
def history(sym):
    if sym in _cache:
        return _cache[sym]
    d = json.loads(get("https://query1.finance.yahoo.com/v8/finance/chart/"
                       f"{urllib.parse.quote(sym)}?range=5y&interval=1d"))["chart"]["result"][0]
    q = d["indicators"]["quote"][0]
    by_day, vol = {}, {}
    for t, h, l, c, v in zip(d["timestamp"], q["high"], q["low"], q["close"], q["volume"]):
        if c is not None:  # Yahoo czasem dubluje ostatni dzień: zostaje najnowszy wpis
            day = dt.datetime.fromtimestamp(t, dt.timezone.utc).date()
            by_day[day], vol[day] = (h or c, l or c, c), v or 0
    days = sorted(by_day)
    # Yahoo potrafi "zamrozić" ceny dzienne (np. akcje GPW): ta sama cena i zerowy obrót.
    # Wtedy ostatnie dni odbudowujemy z danych godzinowych, które są aktualne.
    k = len(days) - 1
    while k > 0 and vol[days[k]] == 0 and by_day[days[k]][2] == by_day[days[k - 1]][2]:
        k -= 1
    if k < len(days) - 1:
        hd = json.loads(get("https://query1.finance.yahoo.com/v8/finance/chart/"
                            f"{urllib.parse.quote(sym)}?range=1mo&interval=60m"))["chart"]["result"][0]
        hq, agg = hd["indicators"]["quote"][0], {}
        for t, h, l, c in zip(hd["timestamp"], hq["high"], hq["low"], hq["close"]):
            if c is not None:
                day = dt.datetime.fromtimestamp(t, dt.timezone.utc).date()
                a = agg.setdefault(day, [h or c, l or c, c])
                a[0], a[1], a[2] = max(a[0], h or c), min(a[1], l or c), c
        for day in days[k + 1:]:
            if day not in agg:
                del by_day[day]
        for day, (h, l, c) in agg.items():
            if day > days[k]:
                by_day[day] = (h, l, c)
        print("Naprawiono zamrożone ceny dzienne:", sym)
        days = sorted(by_day)
    out = {"d": days, "h": [by_day[x][0] for x in days], "l": [by_day[x][1] for x in days],
           "c": [by_day[x][2] for x in days], "cur": d["meta"].get("currency", "")}
    _cache[sym] = out
    return out

def rets(c): return [0.0] + [c[k] / c[k - 1] - 1 for k in range(1, len(c))]
def sma(c, i, n): return mean(c[i - n + 1:i + 1])

def rsi(c, i, n=14):
    g = sum(max(c[k] - c[k - 1], 0) for k in range(i - n + 1, i + 1))
    l = sum(max(c[k - 1] - c[k], 0) for k in range(i - n + 1, i + 1))
    return 100 if l == 0 else 100 - 100 / (1 + g / l)

def atr(h, l, c, i, n=14):
    return mean([max(h[k] - l[k], abs(h[k] - c[k - 1]), abs(l[k] - c[k - 1])) for k in range(i - n + 1, i + 1)])

def align(days, ref):
    """Cena rynku odniesienia na każdy dzień instrumentu (ostatnia znana)."""
    out, j, last = [], 0, None
    for d in days:
        while j < len(ref["d"]) and ref["d"][j] <= d:
            last = ref["c"][j]; j += 1
        out.append(last)
    first = next((x for x in out if x is not None), None)
    return [first if x is None else x for x in out]

def perf(days, c, delta):
    target = days[-1] - dt.timedelta(days=delta)
    k = max((k for k in range(len(days)) if days[k] <= target), default=None)
    return None if k is None else c[-1] / c[k] - 1


# ---------- metody (każda liczy szansę wzrostu następnej sesji z danych do dnia i) ----------
def m_hist(r, i):
    s = r[i] > 0
    nxt = [r[k + 1] > 0 for k in range(max(1, i - W), i) if (r[k] > 0) == s]
    return (100 * sum(nxt) / len(nxt), len(nxt)) if nxt else (None, 0)

def m_season(r, days, i, wd):
    same = [r[k] > 0 for k in range(max(1, i - W + 1), i + 1) if days[k].weekday() == wd]
    return (100 * sum(same) / len(same), len(same)) if same else (None, 0)

def m_trend(c, i):
    rs = rsi(c, i)
    p = 50 + (8 if c[i] > sma(c, i, 20) else -8) + (7 if c[i] > sma(c, i, 50) else -7) \
        + (8 if rs < 30 else -8 if rs > 70 else (rs - 50) * 0.2)
    return p, rs

def m_vol(r, i):
    mu, sd = mean(r[i - 19:i + 1]), st.stdev(r[i - 59:i + 1])
    return None if sd == 0 else 50 + (100 * phi(mu / sd) - 50) * 0.5

def m_ref(r, rr, rc, i):
    try:
        corr = st.correlation(r[i - 59:i + 1], rr[i - 59:i + 1])
    except Exception:
        return None, 0
    score = 0.5 * (1 if rc[i] > sma(rc, i, 20) else -1) + 0.5 * (1 if rc[i] > rc[i - 5] else -1)
    return 50 + 12 * corr * score, corr

def methods_at(S, i, wd):
    out = {"hist": m_hist(S["r"], i)[0], "season": m_season(S["r"], S["d"], i, wd)[0],
           "trend": m_trend(S["c"], i)[0], "vol": m_vol(S["r"], i)}
    out["ref"] = m_ref(S["r"], S["rr"], S["rc"], i)[0] if S["rc"] else None
    return out

BT_KEYS = ["hist", "season", "trend", "vol", "ref"]

def wavg(ps, w):
    ok = [(ps[k], w.get(k, 1)) for k in ps if ps[k] is not None]
    return sum(p * x for p, x in ok) / sum(x for _, x in ok)

def accuracy(preds, outcome):
    pairs = [(p, o) for p, o in zip(preds, outcome) if p is not None and abs(p - 50) > 1e-9]
    return (sum((p > 50) == o for p, o in pairs) / len(pairs), len(pairs)) if pairs else (None, 0)

def to_weight(acc): return 1.0 if acc is None else max(0.3, min(1.8, 1 + 8 * (acc - 0.5)))

def backtest(S):
    """Sprawdza na historii, jak często każda metoda trafiała kierunek następnej sesji."""
    n = len(S["c"])
    start = max(61, n - 1 - 2 * BT)
    preds = {k: [] for k in BT_KEYS}; outcome = []
    for i in range(start, n - 1):
        ps = methods_at(S, i, S["d"][i + 1].weekday())
        for k in BT_KEYS:
            preds[k].append(ps[k])
        outcome.append(S["r"][i + 1] > 0)
    split = max(0, len(outcome) - BT)
    acc = {k: accuracy(preds[k][split:], outcome[split:]) for k in BT_KEYS}
    # wagi do oceny paska ogólnego liczone na wcześniejszym okresie (uczciwy test, bez zaglądania w przyszłość)
    old_w = {k: to_weight(accuracy(preds[k][:split], outcome[:split])[0]) for k in BT_KEYS} if split > 60 \
        else {k: 1.0 for k in BT_KEYS}
    overall = [wavg({k: preds[k][j] for k in BT_KEYS}, old_w) for j in range(split, len(outcome))]
    return {"acc": acc, "overall": accuracy(overall, outcome[split:]), "up_share": mean(outcome[split:]),
            "w": {k: to_weight(acc[k][0]) for k in BT_KEYS}}

def analogs(c, h_list):
    """Co działo się dalej w przeszłości, gdy sytuacja była podobna (trend + RSI)."""
    def state(i):
        rs = rsi(c, i)
        return c[i] > sma(c, i, 50), 0 if rs < 30 else 1 if rs < 50 else 2 if rs < 70 else 3
    n, now = len(c), state(len(c) - 1)
    states = [state(i) for i in range(60, n)]
    out = []
    for label, hzn in h_list:
        fw = sorted(c[i + hzn] / c[i] - 1 for i in range(60, n - hzn) if states[i - 60] == now)
        if len(fw) >= 15:
            out.append({"label": label, "n": len(fw), "up": sum(x > 0 for x in fw) / len(fw),
                        "med": fw[len(fw) // 2], "q1": fw[len(fw) // 4], "q3": fw[3 * len(fw) // 4]})
    return out, now


# ---------- newsy ----------
def parse_date(s):
    try:
        d = email.utils.parsedate_to_datetime(s)
        return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
    except Exception:
        return None

def rss(url, desc=True):
    items = []
    for it in ET.fromstring(get(url)).iter("item"):
        title, src = (it.findtext("title") or "").strip(), (it.findtext("source") or "").strip()
        if src and title.endswith(" - " + src):
            title = title[:-len(src) - 3]
        items.append({"title": title, "link": it.findtext("link"), "source": src or "Bankier.pl",
                      "date": parse_date(it.findtext("pubDate") or ""),
                      "desc": re.sub(r"<[^>]+>", " ", it.findtext("description") or "") if desc else ""})
    return items

def tone(text):
    p = sum(bool(re.search(r"\b" + re.escape(w), text)) for w in POS)
    n = sum(bool(re.search(r"\b" + re.escape(w), text)) for w in NEG)
    return (p - n) / max(1, p + n)

def google(q, lang):
    loc = "hl=en-US&gl=US&ceid=US:en" if lang == "en" else "hl=pl&gl=PL&ceid=PL:pl"
    return rss(f"https://news.google.com/rss/search?q={urllib.parse.quote(q + ' when:14d')}&{loc}", desc=False)

def instrument_news(ins, bankier):
    raw = []
    for lang, key in (("en", "news_en"), ("pl", "news_pl")):
        if ins.get(key):
            try:
                raw += [dict(x, lang=lang) for x in google(ins[key], lang)]
            except Exception as e:
                print("Google News pominięty:", ins[key], e)
    raw += [dict(x, lang="pl") for x in bankier
            if any(k in (x["title"] + " " + x["desc"]).lower() for k in ins["keywords"])]
    seen, out = set(), []
    for x in sorted((x for x in raw if x["date"]), key=lambda x: x["date"], reverse=True):
        key = re.sub(r"\W+", "", x["title"].lower())[:60]
        age = (NOW - x["date"]).total_seconds() / 86400
        if key in seen or not -1 < age <= 14:
            continue
        seen.add(key)
        out.append({"title": x["title"], "link": x["link"], "source": x["source"], "date": x["date"].isoformat(),
                    "age": age, "lang": x["lang"], "tone": round(tone((x["title"] + " " + x["desc"]).lower()), 2)})
    return out

def news_period(items, ins):
    if not items:
        return {"count": 0, "text": "Brak wiadomości w tym okresie.", "items": []}
    pos = sum(x["tone"] > 0.2 for x in items); neg = sum(x["tone"] < -0.2 for x in items)
    avg = mean([x["tone"] for x in items])
    own = " ".join([ins["name"], ins.get("news_en", ""), ins.get("news_pl", "")] + ins["keywords"]).lower()
    skip = STOP | set(re.findall(r"\w+", own))
    words = Counter()
    for x in items:
        words.update({w for w in re.findall(r"[a-ząćęłńóśźż]{4,}", x["title"].lower()) if w not in skip})
    top = [w for w, k in words.most_common(6) if k >= 2][:5]
    mood = "przeważają dobre wiadomości" if avg > 0.15 else "przeważają złe wiadomości" if avg < -0.15 \
        else "wydźwięk jest mieszany lub neutralny"
    text = f"{len(items)} wiadomości: {pos} pozytywnych, {neg} negatywnych, {len(items) - pos - neg} neutralnych – {mood}."
    if top:
        text += " Najczęstsze tematy: " + ", ".join(top) + "."
    return {"count": len(items), "pos": pos, "neg": neg, "tone": round(avg, 2), "text": text,
            "items": [{k: x[k] for k in ("title", "link", "source", "date", "lang", "tone")} for x in items[:10]]}


# ---------- opisy w prostych słowach ----------
def describe(ins, S, lv, pf, rs, ref_info, week, bt, overall):
    c = S["c"][-1]; t = []
    a50, a200 = c > lv["sma50"], lv["sma200"] is not None and c > lv["sma200"]
    if lv["sma200"] is None:
        t.append(f"Cena jest {'powyżej' if a50 else 'poniżej'} średniej z 50 dni – trend jest "
                 f"{'wzrostowy' if a50 else 'spadkowy'}.")
    elif a50 and a200:
        t.append("Trend jest wzrostowy: cena jest powyżej średnich z 50 i 200 dni.")
    elif not a50 and not a200:
        t.append("Trend jest spadkowy: cena jest poniżej średnich z 50 i 200 dni.")
    else:
        t.append(f"Trend jest mieszany: cena jest {'powyżej' if a50 else 'poniżej'} średniej z 50 dni, "
                 f"ale {'powyżej' if a200 else 'poniżej'} średniej z 200 dni.")
    parts = [f"{lab} {fpc(v)}" for lab, v in (("w tydzień", pf.get("1T")), ("w miesiąc", pf.get("1M")),
                                               ("w rok", pf.get("1R"))) if v is not None]
    if parts:
        t.append("Zmiana ceny: " + ", ".join(parts) + ".")
    if rs > 70:
        t.append(f"RSI wynosi {rs:.0f}, czyli rynek jest „przegrzany” – po tak szybkich wzrostach często "
                 "przychodzi chwilowa korekta (spadek).")
    elif rs < 30:
        t.append(f"RSI wynosi {rs:.0f}, czyli rynek jest „wyprzedany” – po mocnych spadkach często zdarza się "
                 "odbicie, ale nie ma gwarancji.")
    else:
        t.append(f"RSI wynosi {rs:.0f} – {'kupujący mają lekką przewagę' if rs >= 50 else 'sprzedający mają lekką przewagę'}, "
                 "bez skrajności.")
    ratio = lv["sd20"] / lv["sd250"] if lv["sd250"] else 1
    if ratio > 1.3:
        t.append(f"Ostatnio cena skacze mocniej niż zwykle (typowy ruch dzienny ±{pct1(lv['sd20'])}) – "
                 "większe ryzyko, ale i większe okazje.")
    elif ratio < 0.75:
        t.append(f"Jest spokojniej niż zwykle (typowy ruch dzienny ±{pct1(lv['sd20'])}) – takie okresy "
                 "często kończą się większym ruchem w którąś stronę.")
    else:
        t.append(f"Wahania są typowe dla tego instrumentu: zwykle ±{pct1(lv['sd20'])} dziennie.")
    if c / lv["hi52"] - 1 > -0.03:
        t.append(f"Cena jest blisko rocznego szczytu ({fp(lv['hi52'])}).")
    elif c / lv["lo52"] - 1 < 0.05:
        t.append(f"Cena jest blisko rocznego dołka ({fp(lv['lo52'])}).")
    else:
        t.append(f"Do rocznego szczytu brakuje {abs(c / lv['hi52'] - 1) * 100:.0f}%, "
                 f"a od rocznego dołka cena jest wyżej o {(c / lv['lo52'] - 1) * 100:.0f}%.")
    if week["count"]:
        t.append("Newsy z ostatniego tygodnia: " + week["text"][0].lower() + week["text"][1:])
    if ref_info:
        name, corr, up = ref_info
        rel = "zwykle porusza się razem z" if corr > 0.3 else "zwykle porusza się odwrotnie niż" if corr < -0.3 \
            else "tylko słabo zależy od"
        t.append(f"{ins['name']} {rel} {name}, który teraz {'rośnie' if up else 'słabnie'}.")
    if bt["overall"][0] is not None:
        t.append(f"Uczciwie: w ostatnim roku pasek ogólny trafiał kierunek następnej sesji w "
                 f"{bt['overall'][0] * 100:.0f}% przypadków (50% to rzut monetą).")
    return t

def make_plan(c, lv, rs, overall, vkey, ref_p, ref_name):
    R, S_, s20, s50, a = lv["R"], lv["S"], lv["sma20"], lv["sma50"], lv["atr"]
    checks = [{"text": f"Cena powyżej średniej z 50 dni ({fp(s50)}) – trend w górę", "ok": c > s50},
              {"text": f"Cena powyżej średniej z 20 dni ({fp(s20)}) – krótki trend w górę", "ok": c > s20},
              {"text": f"RSI między 50 a 70 (teraz {rs:.0f}) – przewaga kupujących bez przegrzania", "ok": 50 <= rs <= 70},
              {"text": f"Cena powyżej oporu {fp(R)} (najwyższa cena z 20 sesji) – wybicie", "ok": c > R}]
    if ref_p is not None:
        checks.append({"text": f"Rynek odniesienia ({ref_name}) sprzyja", "ok": ref_p > 50})
    checks.append({"text": "Pasek ogólny co najmniej 58%", "ok": overall >= 58})
    met = sum(x["ok"] for x in checks)
    triggers = []
    if c <= R:
        triggers.append(f"Wybicie w górę: cena zamknie dzień powyżej {fp(R)} (najwyższa cena z ostatnich 20 sesji). "
                        "To znak, że kupujący przejmują kontrolę.")
    if c < s20:
        triggers.append(f"Powrót nad średnią: cena zamknie dzień powyżej {fp(s20)} (średnia z 20 dni).")
    else:
        triggers.append(f"Spokojny powrót do średniej: cena cofnie się w okolice {fp(s20)} i odbije w górę – "
                        "to często tańszy i bezpieczniejszy moment wejścia niż kupowanie po dużym wzroście.")
    if rs < 50:
        triggers.append(f"RSI wzrośnie powyżej 50 (teraz {rs:.0f}) – wzrosty zaczną przeważać nad spadkami.")
    if rs > 70:
        triggers.append(f"RSI spadnie poniżej 70 (teraz {rs:.0f}) – teraz rynek jest przegrzany, nie warto gonić ceny.")
    triggers.append("Pasek ogólny wzrośnie do 58% lub więcej – wtedy strona sama pokaże „Sprzyjające warunki”.")
    stop, target = c - 2 * a, c + 3 * a
    if vkey == "good":
        head = f"Warunki sprzyjają – spełnione {met} z {len(checks)} warunków. Jeśli chcesz wejść, zrób to z planem:"
        steps = ["Zdecyduj, ile maksymalnie możesz stracić na tej transakcji – zwykle 1–2% pieniędzy na koncie. "
                 "Nigdy nie wchodź całym kapitałem.",
                 f"Ustaw stop loss (zlecenie, które samo zamknie pozycję, gdy cena spadnie) w okolicy {fp(stop)}. "
                 "To ok. 2 typowe dzienne wahania (2×ATR) poniżej obecnej ceny.",
                 f"Możliwy cel zysku: około {fp(target)} – zysk 1,5 raza większy niż ryzyko. Gdy cena tam dojdzie, "
                 "zamknij część pozycji albo przesuń stop loss wyżej.",
                 "Przejrzyj newsy poniżej. Jeśli w najbliższych dniach są ważne wydarzenia (wyniki spółki, decyzja "
                 "banku centralnego), rozważ poczekanie na nie."]
        warn = f"Jeśli cena zamknie dzień poniżej {fp(S_)} (najniższa cena z 20 sesji), sygnał przestaje działać."
    elif vkey == "mid":
        head = (f"Spełnione {met} z {len(checks)} warunków wzrostu – sygnały nie dają wyraźnej przewagi. "
                "Najlepiej poczekać, aż pojawi się przynajmniej jeden z tych sygnałów:")
        steps = triggers
        warn = (f"Sygnał ostrzegawczy: jeśli cena zamknie dzień poniżej {fp(S_)} (najniższa cena z 20 sesji), "
                "trend słabnie – wtedy lepiej nie wchodzić.")
    else:
        head = (f"Teraz przeważają sygnały spadkowe – spełnione {met} z {len(checks)} warunków. Nie kupuj na siłę. "
                "Sytuacja poprawi się, gdy:")
        steps = triggers + ["Granie na spadek (krótka pozycja na CFD) jest możliwe, ale ryzykowniejsze – "
                            "dla początkującego lepsza jest cierpliwość."]
        warn = (f"Cena jest już poniżej ostatniego wsparcia {fp(S_)} – spadki mogą trwać dalej." if c < S_
                else f"Jeśli cena spadnie poniżej {fp(S_)} (najniższa cena z 20 sesji), spadki mogą przyspieszyć.")
    return {"head": head, "steps": steps, "checks": checks, "met": met, "warn": warn,
            "stop": stop, "target": target}


# ---------- analiza jednego instrumentu ----------
def analyze(ins, bankier):
    H = history(ins["symbol"])
    S = {"d": H["d"], "c": H["c"], "r": rets(H["c"]), "rc": None, "rr": None}
    c, n, days, crypto = H["c"], len(H["c"]), H["d"], ins["group"] == "Krypto"
    ref_sym = ins.get("ref")
    if ref_sym:
        try:
            S["rc"] = align(days, history(ref_sym)); S["rr"] = rets(S["rc"])
        except Exception as e:
            print("Brak rynku odniesienia", ref_sym, e)
    i = n - 1
    nxt = days[-1] + dt.timedelta(days=1)
    while not crypto and nxt.weekday() > 4:
        nxt += dt.timedelta(days=1)

    bt = backtest(S)
    hist_p, hist_n = m_hist(S["r"], i)
    sea_p, sea_n = m_season(S["r"], days, i, nxt.weekday())
    tr_p, rs = m_trend(c, i)
    vol_p = m_vol(S["r"], i)
    ref_p, corr = m_ref(S["r"], S["rr"], S["rc"], i) if S["rc"] else (None, 0)

    news = instrument_news(ins, bankier)
    week = news_period([x for x in news if x["age"] <= 7], ins)
    prev = news_period([x for x in news if x["age"] > 7], ins)
    news_p = None if not week["count"] else 50 + week["tone"] * 20

    WD = ["poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela"]
    ref_name = REF_NAMES.get(ref_sym, ref_sym)
    acc = bt["acc"]
    rows = [("hist", "Historia: po takiej samej sesji", hist_p, f"{hist_n} podobnych sesji z ok. 2 lat"),
            ("season", "Sezonowość: dzień tygodnia", sea_p, f"następna sesja: {WD[nxt.weekday()]}, {sea_n} takich dni w historii"),
            ("trend", "Trend i momentum", tr_p, f"RSI {rs:.0f}, cena vs średnie z 20 i 50 dni"),
            ("vol", "Model zmienności", vol_p, "średni ruch z 20 dni vs wahania z 60 dni"),
            ("ref", "Otoczenie rynku", ref_p,
             f"{ref_name}: korelacja {corr:+.2f}".replace(".", ",") if ref_p is not None else "brak danych"),
            ("news", "Nastrój newsów (7 dni)", news_p,
             f"{week['count']} wiadomości PL i ze świata" if week["count"] else "brak newsów z ostatniego tygodnia")]
    methods, ps, w = [], {}, dict(bt["w"], news=0.8)
    for key, name, p, note in rows:
        a = acc.get(key, (None, 0))
        methods.append({"key": key, "name": name, "p": None if p is None else clamp(p), "note": note,
                        "acc": None if a[0] is None else round(a[0] * 100, 1), "w": round(w[key], 2)})
        ps[key] = None if p is None else clamp(p)
    overall = clamp(wavg(ps, w))
    vkey, vtext = verdict(overall)

    lv = {"sma20": sma(c, i, 20), "sma50": sma(c, i, 50), "sma200": sma(c, i, 200) if n >= 200 else None,
          "atr": atr(H["h"], H["l"], c, i), "R": max(H["h"][i - 20:i]), "S": min(H["l"][i - 20:i]),
          "sd20": st.stdev(S["r"][-20:]), "sd60": st.stdev(S["r"][-60:]), "sd250": st.stdev(S["r"][-250:])}
    yr = [k for k in range(n) if days[k] > days[-1] - dt.timedelta(days=365)]
    lv["hi52"], lv["lo52"] = max(H["h"][k] for k in yr), min(H["l"][k] for k in yr)

    ytd_k = max((k for k in range(n) if days[k] < dt.date(days[-1].year, 1, 1)), default=None)
    pf = {"1T": perf(days, c, 7), "1M": perf(days, c, 30), "3M": perf(days, c, 91), "6M": perf(days, c, 182),
          "1R": perf(days, c, 365), "5L": c[-1] / c[0] - 1}
    pf["YTD"] = None if ytd_k is None else c[-1] / c[ytd_k] - 1
    change = c[-1] / c[-2] - 1

    ref_info = None
    if S["rc"] and ref_p is not None:
        ref_info = (ref_name, corr, S["rc"][-1] > sma(S["rc"], i, 20))

    wk, mo = (7, 30) if crypto else (5, 21)
    sd = lv["sd60"]
    ranges = [{"label": lab, "lo": c[-1] * math.exp(-sd * math.sqrt(h)), "hi": c[-1] * math.exp(sd * math.sqrt(h))}
              for lab, h in (("Następna sesja", 1), ("Za tydzień", wk), ("Za miesiąc", mo))]
    an, (an_above, an_b) = analogs(c, [("tydzień", wk), ("miesiąc", mo)])
    an_desc = (f"cena {'powyżej' if an_above else 'poniżej'} średniej z 50 dni i RSI "
               + ["poniżej 30", "30–50", "50–70", "powyżej 70"][an_b])

    t0 = days[0].toordinal()
    return {"symbol": ins["symbol"], "name": ins["name"], "group": ins["group"], "currency": H["cur"],
            "price": c[-1], "change": change * 100, "date": days[-1].isoformat(),
            "overall": overall, "vkey": vkey, "verdict": vtext, "methods": methods,
            "bt": {"overall": None if bt["overall"][0] is None else round(bt["overall"][0] * 100, 1),
                   "days": bt["overall"][1], "up_share": round(bt["up_share"] * 100, 1)},
            "summary": describe(ins, S, lv, pf, rs, ref_info, week, bt, overall),
            "plan": make_plan(c[-1], lv, rs, overall, vkey, ref_p, ref_name),
            "levels": {k: v for k, v in lv.items()}, "rsi": rs, "perf": pf,
            "today_vs_typical": abs(change) / lv["sd60"] if lv["sd60"] else None,
            "forecast": {"ranges": ranges, "analogs": an, "analog_state": an_desc},
            "news": {"week": week, "prev": prev},
            "hist": {"t0": t0, "dd": [d.toordinal() - t0 for d in days], "c": [float(f"{x:.6g}") for x in c]}}


def pulse():
    out = []
    for sym, label in PULSE:
        try:
            H = history(sym); c = H["c"]
            ch, m1 = c[-1] / c[-2] - 1, perf(H["d"], c, 30)
            if sym == "^VIX":
                note = "Spokój na rynkach" if c[-1] < 15 else "Normalna nerwowość" if c[-1] < 25 \
                    else "Strach – duże wahania"
            elif sym == "PLN=X":
                note = "Ile złotych za 1 dolara. Rośnie = dolar drożeje"
            elif sym == "DX-Y.NYB":
                note = "Siła dolara. Silny dolar zwykle ciąży złotu i srebru"
            else:
                note = f"{'Rośnie' if m1 > 0 else 'Spada'} w ostatnim miesiącu"
            out.append({"symbol": sym, "name": label, "price": c[-1], "change": ch * 100,
                        "m1": None if m1 is None else m1 * 100, "note": note})
        except Exception as e:
            print("Puls rynku – pominięto", sym, e)
    return out


if __name__ == "__main__":
    bankier = []
    for f in BANKIER:
        try:
            bankier += rss(f)
        except Exception as e:
            print("RSS pominięty:", f, e)
    items = []
    for ins in json.load(open("instruments.json", encoding="utf-8")):
        try:
            items.append(analyze(ins, bankier))
        except Exception as e:
            print("Pominięto", ins["symbol"], repr(e))
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump({"updated": NOW.isoformat(), "pulse": pulse(), "items": items}, f, ensure_ascii=False,
                  separators=(",", ":"))
    print("Zapisano", len(items), "instrumentów")

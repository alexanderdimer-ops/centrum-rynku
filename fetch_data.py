"""Pobiera ceny, kalendarz i newsy, sam je analizuje i zapisuje wynik do data.json.

Wszystko z darmowych źródeł bez kluczy API:
- ceny dzienne z 5 lat i ceny z dzisiejszej sesji: Yahoo Finance,
- kalendarz: ForexFactory (makro), Nasdaq/Zacks (wyniki spółek USA), Bankier.pl (spółki GPW),
- newsy: Google News RSS (świat po angielsku i Polska) + Bankier.pl RSS (w tym komunikaty ESPI).
Opcjonalnie wysyła powiadomienia na telefon przez ntfy.sh (sekret NTFY_TOPIC w GitHubie).
"""
import json, math, os, re, sys, statistics as st, urllib.request, urllib.parse, datetime as dt
import email.utils
import xml.etree.ElementTree as ET
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
      "Accept": "application/json, text/plain, */*"}
NOW = dt.datetime.now(dt.timezone.utc)
TODAY_PL = (NOW + dt.timedelta(hours=2)).date()   # dzień w Polsce (wystarczająco dokładnie)
W = 500   # ile sesji wstecz biorą metody statystyczne (ok. 2 lata)
BT = 250  # ile ostatnich sesji sprawdza test skuteczności (ok. 1 rok)
SITE = "https://alexanderdimer-ops.github.io/centrum-rynku/"

BANKIER = ["https://www.bankier.pl/rss/wiadomosci.xml", "https://www.bankier.pl/rss/gielda.xml",
           "https://www.bankier.pl/rss/firma.xml", "https://www.bankier.pl/rss/espi.xml",
           "https://www.bankier.pl/rss/waluty.xml"]

# Słownik tonu nagłówków. Najpierw całe frazy (żeby "record low" nie liczyło się jako dobra wiadomość).
PHRASES_POS = ["record high", "all-time high", "rekordowo wysok", "najwyżej od", "highest since", "beats estimates",
               "rekomendacja kupuj", "podwyższa rekomendacj", "raises guidance", "podnosi prognoz"]
PHRASES_NEG = ["record low", "all-time low", "najniżej od", "lowest since", "misses estimates", "cuts guidance",
               "obniża prognoz", "obniża rekomendacj", "profit warning"]
POS = ["wzrost", "wzrosł", "rośnie", "rosną", "zysk", "odbici", "dywidend", "poprawa", "przejęci", "umocni",
       "zwyżk", "drożej", "podwyżk", "surge", "soar", "rall", "jump", "gain", "rise", "rising", "beat", "upgrade",
       "bullish", "boost", "strong", "growth", "rebound", "recover", "outperform", "higher", "climb", "advance"]
NEG = ["spadek", "spadk", "spada", "spadł", "strata", "strat", "obaw", "kryzys", "przecen", "cięci", "kara",
       "pozew", "wyprzedaż", "załamani", "osłabi", "taniej", "zwolnie", "fall", "drop", "plunge", "slump",
       "declin", "loss", "miss", "downgrade", "bearish", "weak", "fear", "crash", "tumble", "lawsuit", "probe",
       "sell-off", "selloff", "slide", "lower", "recession", "warn", "sink", "slip", "concern"]
STOP = set("""the and for with from that this will are was its has have after over into amid as at by on in of to
a an is be it or not new says said how why what when who more than could would can may just about price prices stock stocks
shares share today week year years market markets news update latest live vs per amid ahead first his her their our
you your out off up down all also near high low here there they them were been being had does did percent analysts
oraz jest się nie dla przez jak już ale czy też tak pod nad przy jego jej ich które który która tego tym jako może
będzie są był była było bardzo tylko roku dziś cena ceny kurs akcje akcji spółka spółki rynek rynku proc
january february march april june july august september october november december monday tuesday wednesday
thursday friday saturday sunday stycznia lutego marca kwietnia maja czerwca lipca sierpnia września października
listopada grudnia poniedziałek wtorek środa czwartek piątek sobota niedziela""".split())

# Wiarygodność źródeł: 0 = oficjalne (komunikaty spółek, banki centralne), 1 = najbardziej wiarygodne
# agencje i redakcje finansowe, 2 = dobre serwisy uzupełniające, 3 = pozostałe (najmniejsza waga).
SOURCE_TIERS = [
    (0, ["espi", "gpw.pl", "federal reserve", "federalreserve", "nbp", "sec.gov", "ecb.europa"]),
    (1, ["reuters", "bloomberg", "cnbc", "wall street journal", "wsj", "financial times", "ft.com", "marketwatch",
         "associated press", "ap news", "barron", "yahoo finance", "morningstar", "kitco", "coindesk", "nasdaq",
         "pap", "bankier", "parkiet", "puls biznesu", "pb.pl", "rzeczpospolita", "rp.pl", "isbnews", "stockwatch"]),
    (2, ["investing.com", "benzinga", "barchart", "seeking alpha", "fortune", "business insider", "forbes",
         "the block", "cointelegraph", "money.pl", "interia", "wnp", "forsal", "fxmag", "xtb", "marketscreener",
         "zacks", "tipranks", "theblock", "axios", "the economist", "bbc", "cnn", "fxstreet", "dailyfx",
         "oilprice", "mining.com", "decrypt", "strefainwestorow", "biznesradar", "comparic", "obserwator finansowy"]),
]
TIER_W = {0: 1.3, 1: 1.0, 2: 0.6, 3: 0.3}
TIER_NAME = {0: "oficjalne", 1: "wiarygodne", 2: "uzupełniające", 3: "inne"}

REF_NAMES = {"ETFBW20TR.WA": "WIG20", "^IXIC": "Nasdaq", "DX-Y.NYB": "indeks dolara", "^GSPC": "S&P 500",
             "^VIX": "VIX (indeks strachu)"}
PULSE = [("^GSPC", "S&P 500"), ("^IXIC", "Nasdaq"), ("ETFBW20TR.WA", "WIG20 (ETF)"),
         ("^VIX", "VIX – indeks strachu"), ("PLN=X", "USD/PLN"), ("DX-Y.NYB", "Indeks dolara")]

COUNTRY = {"USD": "USA", "EUR": "Strefa euro", "CNY": "Chiny", "GBP": "Wielka Brytania", "JPY": "Japonia",
           "PLN": "Polska", "CAD": "Kanada", "AUD": "Australia", "CHF": "Szwajcaria", "NZD": "Nowa Zelandia"}
MACRO_PL = [("Non-Farm Employment Change", "Raport z rynku pracy (NFP) – liczba nowych miejsc pracy"),
            ("Unemployment Claims", "Wnioski o zasiłek dla bezrobotnych"), ("Unemployment Rate", "Stopa bezrobocia"),
            ("Core CPI", "Inflacja bazowa CPI"), ("CPI", "Inflacja CPI"),
            ("Core PPI", "Inflacja bazowa producentów PPI"), ("Core Retail Sales", "Sprzedaż detaliczna bez samochodów"),
            ("Core PCE", "Inflacja bazowa PCE (ulubiona miara inflacji Fed)"), ("PPI", "Inflacja producentów PPI"),
            ("Federal Funds Rate", "Decyzja Fed w sprawie stóp procentowych"),
            ("FOMC Statement", "Komunikat Fed po posiedzeniu"), ("FOMC Press Conference", "Konferencja prezesa Fed"),
            ("FOMC Meeting Minutes", "Protokół z posiedzenia Fed"), ("Fed Chair", "Wystąpienie prezesa Fed"),
            ("Main Refinancing Rate", "Decyzja EBC w sprawie stóp procentowych"),
            ("Monetary Policy Statement", "Komunikat banku centralnego"), ("ECB Press Conference", "Konferencja EBC"),
            ("ECB President", "Wystąpienie prezes EBC"), ("Retail Sales", "Sprzedaż detaliczna"),
            ("GDP", "PKB – wzrost gospodarczy"), ("ISM Manufacturing PMI", "Indeks ISM dla przemysłu"),
            ("ISM Services PMI", "Indeks ISM dla usług"), ("Manufacturing PMI", "PMI przemysłu"),
            ("Services PMI", "PMI usług"), ("JOLTS", "Liczba wakatów (JOLTS)"),
            ("Crude Oil Inventories", "Zapasy ropy naftowej w USA"),
            ("Consumer Sentiment", "Nastroje konsumentów"), ("Consumer Confidence", "Zaufanie konsumentów"),
            ("Bank Holiday", "Święto bankowe – mniejsza płynność, część rynków zamknięta"),
            ("Trade Balance", "Bilans handlowy"), ("Average Hourly Earnings", "Wzrost płac"),
            ("Industrial Production", "Produkcja przemysłowa"), ("Building Permits", "Pozwolenia na budowę"),
            ("ZEW", "Nastroje w gospodarce (ZEW)"), ("Ifo", "Nastroje w niemieckim biznesie (Ifo)"),
            ("Philly Fed Manufacturing", "Koniunktura w przemyśle (Fed z Filadelfii)"),
            ("Empire State Manufacturing", "Koniunktura w przemyśle (Nowy Jork)"),
            ("Durable Goods", "Zamówienia na dobra trwałe"), ("Pending Home Sales", "Sprzedaż domów w toku"),
            ("New Home Sales", "Sprzedaż nowych domów"), ("Existing Home Sales", "Sprzedaż domów z rynku wtórnego"),
            ("Flash", "Wstępny odczyt"), ("Employment Change", "Zmiana zatrudnienia")]
PERIOD = {"m/m": " (miesiąc do miesiąca)", "y/y": " (rok do roku)", "q/q": " (kwartał do kwartału)"}


# ---------- pomocnicze ----------
def get(url, timeout=30):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read()

def get_json(url): return json.loads(get(url))
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

def tier_of(source):
    s = (source or "").lower()
    for t, names in SOURCE_TIERS:
        if any(n in s for n in names):
            return t
    return 3


# ---------- ceny ----------
def chart_url(sym, rng, interval):
    return f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?range={rng}&interval={interval}"

_cache = {}
def history(sym):
    if sym in _cache:
        return _cache[sym]
    d = get_json(chart_url(sym, "5y", "1d"))["chart"]["result"][0]
    q = d["indicators"]["quote"][0]
    by_day, vol = {}, {}
    for t, o, h, l, c, v in zip(d["timestamp"], q["open"], q["high"], q["low"], q["close"], q["volume"]):
        if c is not None:  # Yahoo czasem dubluje ostatni dzień: zostaje najnowszy wpis
            day = dt.datetime.fromtimestamp(t, dt.timezone.utc).date()
            by_day[day], vol[day] = (o or c, h or c, l or c, c), v or 0
    days = sorted(by_day)
    # Yahoo potrafi "zamrozić" ceny dzienne (np. akcje GPW): ta sama cena i zerowy obrót.
    # Wtedy ostatnie dni odbudowujemy z danych godzinowych, które są aktualne.
    k = len(days) - 1
    while k > 0 and vol[days[k]] == 0 and by_day[days[k]][3] == by_day[days[k - 1]][3]:
        k -= 1
    if k < len(days) - 1:
        hd = get_json(chart_url(sym, "1mo", "60m"))["chart"]["result"][0]
        hq, agg = hd["indicators"]["quote"][0], {}
        for t, o, h, l, c in zip(hd["timestamp"], hq["open"], hq["high"], hq["low"], hq["close"]):
            if c is not None:
                day = dt.datetime.fromtimestamp(t, dt.timezone.utc).date()
                a = agg.setdefault(day, [o or c, h or c, l or c, c])
                a[1], a[2], a[3] = max(a[1], h or c), min(a[2], l or c), c
        for day in days[k + 1:]:
            if day not in agg:
                del by_day[day]
        for day, bar in agg.items():
            if day > days[k]:
                by_day[day] = tuple(bar)
        print("Naprawiono zamrożone ceny dzienne:", sym)
        days = sorted(by_day)
    out = {"d": days, "o": [by_day[x][0] for x in days], "h": [by_day[x][1] for x in days],
           "l": [by_day[x][2] for x in days], "c": [by_day[x][3] for x in days], "cur": d["meta"].get("currency", "")}
    _cache[sym] = out
    return out

def intraday(sym):
    """Ceny z ostatniej sesji co 5 minut (do wykresu „Dziś”)."""
    d = get_json(chart_url(sym, "1d", "5m"))["chart"]["result"][0]
    pts = [(t, c) for t, c in zip(d.get("timestamp") or [], d["indicators"]["quote"][0]["close"]) if c is not None]
    if len(pts) < 2:
        return None
    step = max(1, len(pts) // 160)
    pts = pts[::step] + ([pts[-1]] if (len(pts) - 1) % step else [])
    return {"t": [t for t, _ in pts], "c": [float(f"{c:.6g}") for _, c in pts],
            "prev": d["meta"].get("chartPreviousClose")}

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
    """Sprawdza na historii, jak często każda metoda trafiała kierunek następnej sesji,
    i mierzy, na ile wynik paska ogólnego naprawdę przekłada się na wzrosty (kalibracja)."""
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
    out = outcome[split:]
    # kalibracja: o ile realnie zmienia się szansa wzrostu, gdy pasek ogólny odchyla się od 50%
    x = [(p - 50) / 100 for p in overall]; y = [float(o) for o in out]
    mx, my = mean(x), mean(y)
    vx = sum((a - mx) ** 2 for a in x)
    k_cal = 0.0 if vx == 0 else max(0.0, min(1.0, sum((a - mx) * (b - my) for a, b in zip(x, y)) / vx))
    base = mean([float(v > 0) for v in S["r"][-W:]])
    return {"acc": acc, "overall": accuracy(overall, out), "up_share": mean(out), "k": k_cal, "base": base,
            "w": {k: to_weight(acc[k][0]) for k in BT_KEYS}}

def rsi_bucket(x): return 0 if x < 30 else 1 if x < 50 else 2 if x < 70 else 3

def analogs(c, h_list):
    """Co działo się dalej w przeszłości, gdy sytuacja była podobna (trend + RSI)."""
    def state(i): return c[i] > sma(c, i, 50), rsi_bucket(rsi(c, i))
    n, now = len(c), state(len(c) - 1)
    states = [state(i) for i in range(60, n)]
    out = []
    for label, hzn in h_list:
        allfw = [c[i + hzn] / c[i] - 1 for i in range(60, n - hzn)]
        fw = sorted(c[i + hzn] / c[i] - 1 for i in range(60, n - hzn) if states[i - 60] == now)
        if len(fw) >= 15:
            base = mean([float(x > 0) for x in allfw])
            up = sum(x > 0 for x in fw) / len(fw)
            out.append({"label": label, "n": len(fw), "up": up, "base": base,
                        "p": (up * len(fw) + base * 30) / (len(fw) + 30),  # ostrożnie: ściągnięte do średniej
                        "med": fw[len(fw) // 2], "q1": fw[len(fw) // 4], "q3": fw[3 * len(fw) // 4]})
    return out, now

def setup_history(S, hzn):
    """Jak zachowywała się cena w ciągu tygodnia, gdy warunki wzrostu były spełnione (lub nie)."""
    c, h, l, n = S["c"], S["h"], S["l"], len(S["c"])
    good, bad, every = [], [], []
    for i in range(60, n - hzn):
        ok = [c[i] > sma(c, i, 50), c[i] > sma(c, i, 20), 50 <= rsi(c, i) <= 70, c[i] > max(h[i - 20:i])]
        if S["rc"]:
            p, _ = m_ref(S["r"], S["rr"], S["rc"], i)
            ok.append(p is not None and p > 50)
        fw = c[i + hzn] / c[i] - 1
        every.append(fw)
        met = sum(ok)
        (good if met >= len(ok) - 1 else bad if met <= 1 else []).append(fw)
    def stat(x): return None if len(x) < 20 else {"n": len(x), "up": sum(v > 0 for v in x) / len(x), "avg": mean(x)}
    return {"good": stat(good), "bad": stat(bad), "all": stat(every)}


# ---------- kalendarz ----------
def macro_title(title, cur):
    pl = next((p for k, p in MACRO_PL if k.lower() in title.lower()), title)
    if title.startswith("German") and pl != title:
        pl = "Niemcy: " + pl[0].lower() + pl[1:]
    pl += next((v for k, v in PERIOD.items() if title.endswith(k)), "")
    return f"{COUNTRY.get(cur, cur)}: {pl}"

def macro_events(instruments, prev_cal):
    old = [e for e in prev_cal if e["kind"] == "makro" and dt.datetime.fromisoformat(e["date"]) > NOW - dt.timedelta(days=1)]
    # ForexFactory prosi o rzadkie pobieranie: raz na godzinę, w pozostałych przebiegach używamy zapisanych danych
    if old and NOW.minute >= 15:
        return old
    try:
        data = get_json("https://nfs.faireconomy.media/ff_calendar_thisweek.json")
    except Exception as e:
        print("Kalendarz makro: używam zapisanych danych,", e); return old
    out = []
    for e in data:
        cur, title, imp = e.get("country"), e.get("title", ""), e.get("impact")
        when = dt.datetime.fromisoformat(e["date"])
        if when < NOW - dt.timedelta(days=1):
            continue
        if "crude oil" in title.lower():
            syms = [i["symbol"] for i in instruments if i.get("oil")]
        elif imp in ("High", "Medium") or (imp == "Holiday" and cur == "USD"):
            syms = [i["symbol"] for i in instruments if cur in i.get("macro", [])
                    and (imp != "Medium" or cur == "USD")]
        else:
            syms = []
        if not syms:
            continue
        out.append({"date": when.astimezone(dt.timezone.utc).isoformat(), "time": True, "kind": "makro",
                    "impact": {"High": "high", "Medium": "mid"}.get(imp, "low"), "title": macro_title(title, cur),
                    "orig": title, "forecast": e.get("forecast") or "", "previous": e.get("previous") or "",
                    "symbols": syms, "source": "ForexFactory"})
    return out

def bankier_events(ins):
    s = get(f"https://www.bankier.pl/gielda/notowania/akcje/{ins['bankier']}/kalendarium").decode("utf-8", "ignore")
    out = []
    for m in re.finditer(r'data-timestamp="(\d+)"(.*?)(?=data-timestamp="|$)', s, re.S):
        day = dt.datetime.fromtimestamp(int(m.group(1)) + 4 * 3600, dt.timezone.utc).date()  # północ w Polsce
        if not TODAY_PL - dt.timedelta(days=1) <= day <= TODAY_PL + dt.timedelta(days=90):
            continue
        for ev in re.finditer(r'm-quotes-calendar-list__info">([^<]*)</div>.*?<span class="value">([^<]*)</span>',
                              m.group(2), re.S):
            info, badge = ev.group(1).strip(), ev.group(2).strip()
            kind = {"Wyniki spółek": "wyniki", "Dywidendy": "dywidenda", "WZA": "wza"}.get(badge, "inne")
            title = {"wyniki": "Wyniki finansowe", "dywidenda": "Dywidenda", "wza": "Walne zgromadzenie"}.get(kind, badge)
            out.append({"date": day.isoformat(), "time": False, "kind": kind,
                        "impact": "high" if kind == "wyniki" else "mid" if kind == "dywidenda" else "low",
                        "title": f"{ins['name']}: {title}", "desc": info, "symbols": [ins["symbol"]],
                        "source": "Bankier.pl"})
    return out

def nasdaq_earnings(ins):
    txt = get_json(f"https://api.nasdaq.com/api/analyst/{ins['symbol']}/earnings-date")["data"]["reportText"] or ""
    m = re.search(r"on\s+(\d{2})/(\d{2})/(\d{4})\s*(after market close|before market open)?", txt)
    if not m:
        return []
    day = dt.date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
    if not TODAY_PL - dt.timedelta(days=1) <= day <= TODAY_PL + dt.timedelta(days=90):
        return []
    when = {"after market close": "po zamknięciu sesji w USA", "before market open": "przed otwarciem sesji w USA"}
    desc = when.get(m.group(4) or "", "godzina nieznana")
    eps = re.search(r"consensus EPS forecast for the quarter is \$(\d+(?:\.\d+)?)", txt)
    if eps:
        desc += f"; prognoza analityków: {eps.group(1).replace('.', ',')} $ zysku na akcję"
    if "expected*" in txt:
        desc += " (data szacowana)"
    return [{"date": day.isoformat(), "time": False, "kind": "wyniki", "impact": "high",
             "title": f"{ins['name']}: wyniki kwartalne", "desc": desc, "symbols": [ins["symbol"]],
             "source": "Nasdaq / Zacks"}]

def event_day(e):
    return (dt.datetime.fromisoformat(e["date"]) + dt.timedelta(hours=2)).date() if e["time"] \
        else dt.date.fromisoformat(e["date"])

def calendar(instruments, prev_cal):
    ev = macro_events(instruments, prev_cal)
    for ins in instruments:
        try:
            if ins.get("bankier"):
                ev += bankier_events(ins)
            if ins.get("earnings"):
                ev += nasdaq_earnings(ins)
        except Exception as e:
            print("Kalendarz spółki pominięty:", ins["symbol"], e)
    seen, out = set(), []
    for e in sorted(ev, key=lambda e: e["date"]):
        key = (e["date"], e.get("orig", e["title"]), e.get("desc", ""))
        if key not in seen:
            seen.add(key); e["days"] = (event_day(e) - TODAY_PL).days; out.append(e)
    return out


# ---------- newsy ----------
def parse_date(s):
    try:
        d = email.utils.parsedate_to_datetime(s)
        return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
    except Exception:
        return None

def rss(url, desc=True, source=None):
    items = []
    for it in ET.fromstring(get(url)).iter("item"):
        title, src = (it.findtext("title") or "").strip(), (it.findtext("source") or "").strip()
        if src and title.endswith(" - " + src):
            title = title[:-len(src) - 3]
        items.append({"title": title, "link": it.findtext("link"), "source": source or src or "Bankier.pl",
                      "date": parse_date(it.findtext("pubDate") or ""),
                      "desc": re.sub(r"<[^>]+>", " ", it.findtext("description") or "") if desc else ""})
    return items

def tone(text):
    p = sum(f in text for f in PHRASES_POS); n = sum(f in text for f in PHRASES_NEG)
    p += sum(bool(re.search(r"\b" + re.escape(w), text)) for w in POS)
    n += sum(bool(re.search(r"\b" + re.escape(w), text)) for w in NEG)
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
                    "age": age, "lang": x["lang"], "tier": tier_of(x["source"]),
                    "tone": round(tone((x["title"] + " " + x["desc"]).lower()), 2)})
    return out

def news_period(items, ins):
    if not items:
        return {"count": 0, "text": "Brak wiadomości w tym okresie.", "items": [], "tone": 0}
    pos = sum(x["tone"] > 0.2 for x in items); neg = sum(x["tone"] < -0.2 for x in items)
    wsum = sum(TIER_W[x["tier"]] for x in items)
    avg = sum(x["tone"] * TIER_W[x["tier"]] for x in items) / wsum  # ważone wiarygodnością źródła
    good = sum(x["tier"] <= 1 for x in items)
    own = " ".join([ins["name"], ins.get("news_en", ""), ins.get("news_pl", "")] + ins["keywords"]).lower()
    skip = STOP | set(re.findall(r"\w+", own))
    words = Counter()
    for x in items:
        words.update({w for w in re.findall(r"[a-ząćęłńóśźż]{4,}", x["title"].lower()) if w not in skip})
    top = [w for w, k in words.most_common(6) if k >= 2][:5]
    mood = "przeważają dobre wiadomości" if avg > 0.15 else "przeważają złe wiadomości" if avg < -0.15 \
        else "wydźwięk jest mieszany lub neutralny"
    text = (f"{len(items)} wiadomości ({good} z najbardziej wiarygodnych źródeł): {pos} pozytywnych, {neg} negatywnych, "
            f"{len(items) - pos - neg} neutralnych – {mood}.")
    if top:
        text += " Najczęstsze tematy: " + ", ".join(top) + "."
    shown = sorted(items, key=lambda x: (min(x["tier"], 2), x["age"]))[:10]  # najpierw wiarygodne, potem najnowsze
    return {"count": len(items), "good": good, "pos": pos, "neg": neg, "tone": round(avg, 2), "text": text,
            "items": [{k: x[k] for k in ("title", "link", "source", "date", "lang", "tone", "tier")} for x in shown]}


# ---------- ryzyko ----------
def risk_profile(H, S, crypto, events_soon, vix):
    c, o, r = H["c"], H["o"], S["r"]
    yr = r[-252:]
    sd60 = st.stdev(r[-60:])
    ann = sd60 * math.sqrt(365 if crypto else 252)
    peak, mdd = c[-252], 0.0
    for x in c[-252:]:
        peak = max(peak, x); mdd = min(mdd, x / peak - 1)
    gaps = [abs(o[k] / c[k - 1] - 1) for k in range(len(c) - 251, len(c)) if o[k] and c[k - 1]]
    var95 = sorted(yr)[int(len(yr) * 0.05)]
    lvl = 1 if ann < 0.15 else 2 if ann < 0.35 else 3 if ann < 0.60 else 4
    why = [f"Zmienność roczna {pct1(ann)} – " + ["niska", "umiarkowana", "wysoka", "bardzo wysoka"][lvl - 1] + "."]
    if events_soon:
        lvl += 1; why.append("Tuż przed ważnym wydarzeniem: " + "; ".join(e["title"] for e in events_soon[:2]) + ".")
    if vix and vix > 25:
        lvl += 1; why.append(f"Na rynkach panuje strach (VIX {vix:.0f}) – ceny skaczą mocniej niż zwykle.")
    if gaps and max(gaps) > 3 * sd60:
        why.append(f"Zdarzają się duże skoki ceny między sesjami (największy w roku: {pct1(max(gaps))}) – "
                   "stop loss nie chroni przed takim skokiem.")
    lvl = min(lvl, 4)
    return {"level": lvl, "label": ["Niskie", "Umiarkowane", "Wysokie", "Bardzo wysokie"][lvl - 1], "why": why,
            "ann": ann, "sd": sd60, "worst": min(yr), "best": max(yr), "mdd": mdd, "var95": var95,
            "gap_max": max(gaps) if gaps else 0, "gap_avg": mean(gaps) if gaps else 0}


# ---------- opisy w prostych słowach ----------
def describe(ins, lv, pf, rs, ref_info, week, bt, risk, setups):
    c = lv["price"]; t = []
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
    t.append(f"Ryzyko: {risk['label'].lower()}. W najgorszym dniu ostatniego roku cena spadła o "
             f"{pct1(-risk['worst'])}, a największy spadek od szczytu wyniósł {pct1(-risk['mdd'])}.")
    if week["count"]:
        t.append("Newsy z ostatniego tygodnia: " + week["text"][0].lower() + week["text"][1:])
    if ref_info:
        name, corr, up = ref_info
        rel = "zwykle porusza się razem z" if corr > 0.3 else "zwykle porusza się odwrotnie niż" if corr < -0.3 \
            else "tylko słabo zależy od"
        t.append(f"{ins['name']} {rel} {name}, który teraz {'rośnie' if up else 'słabnie'}.")
    g, a = setups.get("good"), setups.get("all")
    if g and a:
        t.append(f"Historia tego instrumentu: gdy warunki wzrostu były spełnione, cena po tygodniu była wyżej w "
                 f"{g['up'] * 100:.0f}% przypadków (zwykle: {a['up'] * 100:.0f}%).")
    if bt["overall"][0] is not None:
        t.append(f"Uczciwie: w ostatnim roku pasek ogólny trafiał kierunek następnej sesji w "
                 f"{bt['overall'][0] * 100:.0f}% przypadków (50% to rzut monetą).")
    return t

def make_plan(c, lv, rs, p_up, vkey, ref_p, ref_name, short_ok):
    R, S_, s20, s50, a = lv["R"], lv["S"], lv["sma20"], lv["sma50"], lv["atr"]
    checks = [{"text": f"Cena powyżej średniej z 50 dni ({fp(s50)}) – trend w górę", "ok": c > s50},
              {"text": f"Cena powyżej średniej z 20 dni ({fp(s20)}) – krótki trend w górę", "ok": c > s20},
              {"text": f"RSI między 50 a 70 (teraz {rs:.0f}) – przewaga kupujących bez przegrzania", "ok": 50 <= rs <= 70},
              {"text": f"Cena powyżej oporu {fp(R)} (najwyższa cena z 20 sesji) – wybicie", "ok": c > R}]
    if ref_p is not None:
        checks.append({"text": f"Rynek odniesienia ({ref_name}) sprzyja", "ok": ref_p > 50})
    checks.append({"text": f"Szansa wzrostu powyżej 50% (teraz {p_up:.0f}%)".replace(".", ","), "ok": p_up > 50})
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
    if c < s50:
        triggers.append(f"Powrót nad średnią z 50 dni ({fp(s50)}) – dopiero wtedy trend średnioterminowy zmieni się na wzrostowy.")
    if rs < 50:
        triggers.append(f"RSI wzrośnie powyżej 50 (teraz {rs:.0f}) – wzrosty zaczną przeważać nad spadkami.")
    if rs > 70:
        triggers.append(f"RSI spadnie poniżej 70 (teraz {rs:.0f}) – teraz rynek jest przegrzany, nie warto gonić ceny.")
    stop, target = c - 2 * a, c + 3 * a
    if vkey == "good":
        head = f"Spełnione {met} z {len(checks)} warunków wzrostu. Jeśli chcesz wejść, zrób to z planem:"
        steps = ["Policz wielkość pozycji w zakładce „Ryzyko i kalkulator” – ryzykuj najwyżej 1–2% pieniędzy na koncie.",
                 f"Ustaw stop loss (zlecenie, które samo zamknie pozycję, gdy cena spadnie) w okolicy {fp(stop)}. "
                 "To ok. 2 typowe dzienne wahania (2×ATR) poniżej obecnej ceny.",
                 f"Możliwy cel zysku: około {fp(target)} – zysk 1,5 raza większy niż ryzyko. Gdy cena tam dojdzie, "
                 "zamknij część pozycji albo przesuń stop loss wyżej.",
                 "Sprawdź zakładkę „Newsy i wydarzenia” – przed wynikami spółki lub decyzją banku centralnego lepiej poczekać."]
        warn = f"Jeśli cena zamknie dzień poniżej {fp(S_)} (najniższa cena z 20 sesji), sygnał przestaje działać."
    elif vkey == "mid":
        head = (f"Spełnione {met} z {len(checks)} warunków wzrostu – sygnały nie dają wyraźnej przewagi. "
                "Najlepiej poczekać, aż pojawi się przynajmniej jeden z tych sygnałów:")
        steps = triggers
        warn = (f"Sygnał ostrzegawczy: jeśli cena zamknie dzień poniżej {fp(S_)} (najniższa cena z 20 sesji), "
                "trend słabnie – wtedy lepiej nie wchodzić.")
    else:
        head = (f"Spełnione tylko {met} z {len(checks)} warunków wzrostu – przeważają sygnały spadkowe. "
                "Nie kupuj na siłę. Sytuacja poprawi się, gdy:")
        steps = triggers + ["Granie na spadek (krótka pozycja na CFD) jest możliwe, ale ryzykowniejsze – "
                            "dla początkującego lepsza jest cierpliwość." if short_ok else
                            "Na tym instrumencie nie zarobisz na spadkach bez CFD – najlepiej poczekać."]
        warn = (f"Cena jest już poniżej ostatniego wsparcia {fp(S_)} – spadki mogą trwać dalej." if c < S_
                else f"Jeśli cena spadnie poniżej {fp(S_)} (najniższa cena z 20 sesji), spadki mogą przyspieszyć.")
    return {"head": head, "steps": steps, "checks": checks, "met": met, "warn": warn,
            "stop": stop, "target": target}

def decide(vkey, plan, events_soon, risk, setups):
    reasons = []
    if vkey == "good":
        key, title = "go", "Możesz rozważyć wejście"
        reasons.append(f"Spełnione {plan['met']} z {len(plan['checks'])} warunków wzrostu.")
        g, a = setups.get("good"), setups.get("all")
        if g and a and g["up"] < a["up"] - 0.02:
            reasons.append("Uwaga: na tym instrumencie takie warunki w przeszłości nie dawały przewagi – "
                           "traktuj sygnał ostrożnie i wejdź mniejszą pozycją.")
        if events_soon:
            key, title = "wait", "Poczekaj – ważne wydarzenie"
            reasons.append("Wkrótce: " + events_soon[0]["title"] + ". Wynik może mocno poruszyć ceną w dowolną stronę.")
        if risk["level"] >= 4:
            key, title = "wait", "Poczekaj – bardzo wysokie ryzyko"
            reasons.append("Ryzyko jest bardzo wysokie – jeśli wchodzisz, to mniejszą pozycją.")
    elif vkey == "mid":
        key, title = "wait", "Poczekaj na sygnał"
        reasons.append(f"Spełnione {plan['met']} z {len(plan['checks'])} warunków – brak wyraźnej przewagi.")
        if events_soon:
            reasons.append("Wkrótce: " + events_soon[0]["title"] + ".")
    else:
        key, title = "no", "Nie wchodź teraz"
        reasons.append(f"Spełnione tylko {plan['met']} z {len(plan['checks'])} warunków wzrostu.")
    return {"key": key, "title": title, "reasons": reasons}


# ---------- analiza jednego instrumentu ----------
def analyze(ins, bankier, cal, vix):
    H = history(ins["symbol"])
    S = {"d": H["d"], "c": H["c"], "h": H["h"], "l": H["l"], "r": rets(H["c"]), "rc": None, "rr": None}
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
             f"{week['count']} wiadomości, ważone wiarygodnością źródeł" if week["count"] else "brak newsów z ostatniego tygodnia")]
    methods, ps, w = [], {}, dict(bt["w"], news=0.8)
    for key, name, p, note in rows:
        a = acc.get(key, (None, 0))
        methods.append({"key": key, "name": name, "p": None if p is None else clamp(p), "note": note,
                        "acc": None if a[0] is None else round(a[0] * 100, 1), "w": round(w[key], 2)})
        ps[key] = None if p is None else clamp(p)
    raw = wavg(ps, w)
    # Kalibracja: pokazujemy tyle, ile wynik paska realnie znaczył w historii (zwykle niewiele),
    # dookoła naturalnej częstości wzrostów tego instrumentu.
    p_up = 100 * bt["base"] + bt["k"] * (raw - 50)
    if vix and vix > 25:
        p_up = 50 + (p_up - 50) * 0.7
    p_up = clamp(p_up)

    lv = {"price": c[-1], "sma20": sma(c, i, 20), "sma50": sma(c, i, 50), "sma200": sma(c, i, 200) if n >= 200 else None,
          "atr": atr(H["h"], H["l"], c, i), "R": max(H["h"][i - 20:i]), "S": min(H["l"][i - 20:i]),
          "sd20": st.stdev(S["r"][-20:]), "sd60": st.stdev(S["r"][-60:]), "sd250": st.stdev(S["r"][-250:])}
    yr = [k for k in range(n) if days[k] > days[-1] - dt.timedelta(days=365)]
    lv["hi52"], lv["lo52"] = max(H["h"][k] for k in yr), min(H["l"][k] for k in yr)

    ytd_k = max((k for k in range(n) if days[k] < dt.date(days[-1].year, 1, 1)), default=None)
    pf = {"1T": perf(days, c, 7), "1M": perf(days, c, 30), "3M": perf(days, c, 91), "6M": perf(days, c, 182),
          "1R": perf(days, c, 365), "5L": c[-1] / c[0] - 1}
    pf["YTD"] = None if ytd_k is None else c[-1] / c[ytd_k] - 1
    change = c[-1] / c[-2] - 1

    my_events = [e for e in cal if ins["symbol"] in e["symbols"]]
    # wydarzenia, przed którymi lepiej nie otwierać pozycji: wyniki spółki (3 dni) i ważne dane makro (do jutra)
    soon = [e for e in my_events if (e["kind"] == "wyniki" and 0 <= e["days"] <= 3)
            or (e["kind"] == "makro" and e["impact"] == "high" and 0 <= e["days"] <= 1)]
    risk = risk_profile(H, S, crypto, soon, vix)

    wk, mo = (7, 30) if crypto else (5, 21)
    sd = lv["sd60"]
    ranges = [{"label": lab, "lo": c[-1] * math.exp(-sd * math.sqrt(h)), "hi": c[-1] * math.exp(sd * math.sqrt(h))}
              for lab, h in (("Następna sesja", 1), ("Za tydzień", wk), ("Za miesiąc", mo))]
    an, (an_above, an_b) = analogs(c, [("tydzień", wk), ("miesiąc", mo)])
    an_desc = (f"cena {'powyżej' if an_above else 'poniżej'} średniej z 50 dni i RSI "
               + ["poniżej 30", "30–50", "50–70", "powyżej 70"][an_b])
    p_week = next((a["p"] * 100 for a in an if a["label"] == "tydzień"), None)
    setups = setup_history(S, wk)

    plan = make_plan(c[-1], lv, rs, p_up, None, ref_p, ref_name, True)
    total = len(plan["checks"])
    vkey = "good" if plan["met"] >= total - 1 and p_up >= 50 else "bad" if plan["met"] <= 1 or p_up < 45 else "mid"
    plan = make_plan(c[-1], lv, rs, p_up, vkey, ref_p, ref_name, True)
    vtext = {"good": "Sprzyjające warunki", "mid": "Neutralnie – czekaj na sygnał", "bad": "Niekorzystne warunki"}[vkey]
    decision = decide(vkey, plan, soon, risk, setups)

    ref_info = (ref_name, corr, S["rc"][-1] > sma(S["rc"], i, 20)) if S["rc"] and ref_p is not None else None

    intra = None
    try:
        intra = intraday(ins["symbol"])
    except Exception as e:
        print("Brak danych z dzisiejszej sesji:", ins["symbol"], e)

    t0 = days[0].toordinal()
    return {"symbol": ins["symbol"], "name": ins["name"], "group": ins["group"], "currency": H["cur"],
            "price": c[-1], "change": change * 100, "date": days[-1].isoformat(),
            "overall": p_up, "raw": round(raw, 1), "p_week": None if p_week is None else round(p_week, 1),
            "vkey": vkey, "verdict": vtext, "decision": decision, "risk": risk, "methods": methods,
            "bt": {"overall": None if bt["overall"][0] is None else round(bt["overall"][0] * 100, 1),
                   "days": bt["overall"][1], "up_share": round(bt["up_share"] * 100, 1),
                   "k": round(bt["k"], 2), "base": round(bt["base"] * 100, 1)},
            "setups": setups,
            "summary": describe(ins, lv, pf, rs, ref_info, week, bt, risk, setups),
            "plan": plan, "levels": lv, "rsi": rs, "perf": pf,
            "today_vs_typical": abs(change) / lv["sd60"] if lv["sd60"] else None,
            "forecast": {"ranges": ranges, "analogs": an, "analog_state": an_desc},
            "news": {"week": week, "prev": prev},
            "cfd": {"lev": ins.get("lev", 5), "spread": ins.get("spread", 0.1), "lot": ins.get("lot"),
                    "unit": ins.get("unit", "szt.")},
            "intra": intra,
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


def notify(items, prev):
    """Powiadomienia na telefon (aplikacja ntfy), jeśli w GitHubie ustawiono sekret NTFY_TOPIC."""
    topic = os.environ.get("NTFY_TOPIC")
    if not topic or not prev:
        return
    old = {i["symbol"]: i for i in prev.get("items", [])}
    for it in items:
        p = old.get(it["symbol"])
        if not p or "decision" not in p:
            continue
        msgs = []
        if p["decision"]["key"] != it["decision"]["key"]:
            msgs.append(f"Nowa ocena: {it['decision']['title']} (było: {p['decision']['title']}).")
        R, S_ = p["levels"]["R"], p["levels"]["S"]
        if p["price"] <= R < it["price"]:
            msgs.append(f"Wybicie w górę: cena {fp(it['price'])} przebiła opór {fp(R)}.")
        if p["price"] >= S_ > it["price"]:
            msgs.append(f"Uwaga: cena {fp(it['price'])} spadła poniżej wsparcia {fp(S_)}.")
        if msgs:
            body = json.dumps({"topic": topic, "title": f"{it['name']} – Centrum rynku", "message": " ".join(msgs),
                               "click": SITE + "#i=" + urllib.parse.quote(it["symbol"])}).encode()
            try:
                urllib.request.urlopen(urllib.request.Request("https://ntfy.sh/", data=body,
                                                              headers={"Content-Type": "application/json"}), timeout=15)
                print("Wysłano powiadomienie:", it["symbol"])
            except Exception as e:
                print("Powiadomienie nieudane:", e)


if __name__ == "__main__":
    try:
        prev = json.load(open("data.json", encoding="utf-8"))
    except Exception:
        prev = None
    instruments = json.load(open("instruments.json", encoding="utf-8"))
    bankier = []
    for f in BANKIER:
        try:
            bankier += rss(f, source="ESPI – komunikat spółki" if "espi" in f else "Bankier.pl")
        except Exception as e:
            print("RSS pominięty:", f, e)
    cal = calendar(instruments, (prev or {}).get("calendar", []))
    try:
        vix = history("^VIX")["c"][-1]
    except Exception:
        vix = None
    items = []
    for ins in instruments:
        try:
            items.append(analyze(ins, bankier, cal, vix))
        except Exception as e:
            print("Pominięto", ins["symbol"], repr(e))
    fx = {"PLN": 1.0}
    for cur, sym in (("USD", "PLN=X"), ("EUR", "EURPLN=X")):
        try:
            fx[cur] = history(sym)["c"][-1]
        except Exception as e:
            print("Brak kursu", cur, e)
    names = {i["symbol"]: i["name"] for i in instruments}
    for e in cal:
        e["names"] = [names[s] for s in e["symbols"] if s in names]
    notify(items, prev)
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump({"updated": NOW.isoformat(), "pulse": pulse(), "fx": fx, "calendar": cal, "items": items},
                  f, ensure_ascii=False, separators=(",", ":"))
    print("Zapisano", len(items), "instrumentów,", len(cal), "wydarzeń w kalendarzu")

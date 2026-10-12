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
       "bullish", "boost", "strong", "growth", "rebound", "recover", "outperform", "climb", "advance", "highest"]
NEG = ["spadek", "spadk", "spada", "spadł", "strata", "strat", "obaw", "kryzys", "przecen", "cięci", "kara",
       "pozew", "wyprzedaż", "załamani", "osłabi", "taniej", "zwolnie", "fall", "drop", "plunge", "slump",
       "declin", "loss", "miss", "downgrade", "bearish", "weak", "fear", "crash", "tumble", "lawsuit", "probe",
       "sell-off", "selloff", "slide", "recession", "warn", "sink", "slip", "concern", "pull back", "pullback",
       "retreat", "bleed", "lowest"]
STOP = set("""the and for with from that this will are was its has have after over into amid as at by on in of to
a an is be it or not new says said how why what when who more than could would can may just about price prices stock stocks
shares share today week year years market markets news update latest live vs per amid ahead first his her their our
you your out off up down all also near high low here there they them were been being had does did percent analysts
oraz jest się nie dla przez jak już ale czy też tak pod nad przy jego jej ich które który która tego tym jako może
będzie są był była było bardzo tylko roku dziś cena ceny kurs akcje akcji spółka spółki rynek rynku proc
january february march april june july august september october november december monday tuesday wednesday
thursday friday saturday sunday stycznia lutego marca kwietnia maja czerwca lipca sierpnia września października
listopada grudnia poniedziałek wtorek środa czwartek piątek sobota niedziela dzisiaj nadal uncję uncji
forecast prognoza ounce another again still""".split())

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
MACRO_HINT = [
    (("CPI", "PPI", "PCE"), "Wyższa inflacja niż prognoza oddala obniżki stóp – zwykle silniejszy dolar, słabsze złoto i akcje. Niższa – odwrotnie."),
    (("Non-Farm", "Employment Change", "Average Hourly"), "Więcej miejsc pracy / szybszy wzrost płac niż prognoza – silniejszy dolar, zwykle słabsze złoto; mniej – odwrotnie."),
    (("Unemployment",), "Wyższe bezrobocie niż prognoza – słabsza gospodarka, większa szansa na obniżki stóp: zwykle dobre dla złota, słabszy dolar."),
    (("Federal Funds", "FOMC", "Fed Chair", "Main Refinancing", "Monetary Policy", "ECB"), "Decyzja lub sygnały o stopach: obniżki zwykle pomagają akcjom, złotu i krypto; podwyżki lub „twardy” ton – szkodzą."),
    (("Retail Sales", "GDP", "PMI", "ISM", "Philly", "Empire", "Durable", "Industrial", "Sentiment", "Confidence", "ZEW", "Ifo"), "Lepszy odczyt niż prognoza = silniejsza gospodarka: zwykle dobre dla akcji i ropy, silniejszy dolar. Gorszy – odwrotnie."),
    (("Crude Oil",), "Większy wzrost zapasów niż prognoza = słabszy popyt: zwykle spadek ceny ropy. Spadek zapasów – wzrost ceny."),
    (("Bank Holiday",), "Mniejsza płynność – ruchy cen mogą być nietypowe."),
]
EVENT_HINT = {"wyniki": "Wyniki lepsze od prognoz analityków zwykle podnoszą cenę, gorsze – obniżają. Ruch bywa duży (5–10%) i nagły.",
              "dywidenda": "W dniu odcięcia dywidendy cena akcji spada mniej więcej o jej wartość – to normalne, posiadacz dostaje gotówkę.",
              "wza": "Walne zgromadzenie zwykle ma mały wpływ, chyba że decyduje o dywidendzie lub dużych zmianach w spółce."}
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
def history(sym, rng="5y"):
    if (sym, rng) in _cache:
        return _cache[(sym, rng)]
    if rng != "5y" and (sym, "5y") in _cache:
        return _cache[(sym, "5y")]
    d = get_json(chart_url(sym, rng, "1d"))["chart"]["result"][0]
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
        hq, agg, hv = hd["indicators"]["quote"][0], {}, {}
        for t, o, h, l, c, v in zip(hd["timestamp"], hq["open"], hq["high"], hq["low"], hq["close"], hq["volume"]):
            if c is not None:
                day = dt.datetime.fromtimestamp(t, dt.timezone.utc).date()
                a = agg.setdefault(day, [o or c, h or c, l or c, c])
                a[1], a[2], a[3] = max(a[1], h or c), min(a[2], l or c), c
                hv[day] = hv.get(day, 0) + (v or 0)
        for day in days[k + 1:]:
            if day not in agg:
                del by_day[day]
        for day, bar in agg.items():
            if day > days[k]:
                by_day[day] = tuple(bar)
                vol[day] = hv.get(day, 0)
        print("Naprawiono zamrożone ceny dzienne:", sym)
        days = sorted(by_day)
    out = {"d": days, "o": [by_day[x][0] for x in days], "h": [by_day[x][1] for x in days],
           "l": [by_day[x][2] for x in days], "c": [by_day[x][3] for x in days], "v": [vol.get(x, 0) for x in days],
           "cur": d["meta"].get("currency", ""), "name": d["meta"].get("longName") or d["meta"].get("shortName") or sym,
           "type": d["meta"].get("instrumentType", "")}
    _cache[(sym, rng)] = out
    return out

def intraday(sym):
    """Ceny z ostatniej sesji co 5 minut (do wykresu „Dziś”)."""
    d = get_json(chart_url(sym, "1d", "5m"))["chart"]["result"][0]
    q = d["indicators"]["quote"][0]
    pts = [(t, c) for t, c in zip(d.get("timestamp") or [], q["close"]) if c is not None]
    if len(pts) < 2:
        return None
    bars = [(t, o or c, h or c, l or c, c) for t, o, h, l, c in
            zip(d["timestamp"], q["open"], q["high"], q["low"], q["close"]) if c is not None]
    cnd = {"t": [], "o": [], "h": [], "l": [], "c": []}
    for k in range(0, len(bars), 3):  # 3 × 5 minut = świeca 15-minutowa
        g = bars[k:k + 3]
        for key, val in (("t", g[0][0]), ("o", g[0][1]), ("h", max(x[2] for x in g)), ("l", min(x[3] for x in g)),
                         ("c", g[-1][4])):
            cnd[key].append(val if key == "t" else float(f"{val:.6g}"))
    step = max(1, len(pts) // 160)
    pts = pts[::step] + ([pts[-1]] if (len(pts) - 1) % step else [])
    return {"t": [t for t, _ in pts], "c": [float(f"{c:.6g}") for _, c in pts],
            "prev": d["meta"].get("chartPreviousClose"), "cnd": cnd}

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
        hint = next((t for keys, t in MACRO_HINT if any(k.lower() in title.lower() for k in keys)), "")
        out.append({"date": when.astimezone(dt.timezone.utc).isoformat(), "time": True, "kind": "makro", "hint": hint,
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
        if not e.get("hint"):
            e["hint"] = (next((t for keys, t in MACRO_HINT if any(k.lower() in e.get("orig", "").lower() for k in keys)), "")
                         if e["kind"] == "makro" else EVENT_HINT.get(e["kind"], ""))
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
    kind = market_kind(ins["symbol"], ins["group"])
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
        text = (x["title"] + " " + x["desc"]).lower()
        d_, why = interpret(text, kind)
        out.append({"title": x["title"], "link": x["link"], "source": x["source"], "date": x["date"].isoformat(),
                    "age": age, "lang": x["lang"], "tier": tier_of(x["source"]),
                    "tone": round(tone(text), 2), "dir": d_, "why": why})
    return out

def news_period(items, ins):
    if not items:
        return {"count": 0, "text": "Brak wiadomości w tym okresie.", "items": [], "tone": 0}
    pos = sum(x["tone"] > 0.2 for x in items); neg = sum(x["tone"] < -0.2 for x in items)
    wsum = sum(TIER_W[x["tier"]] for x in items)
    val = lambda x: {"up": 0.6, "down": -0.6}.get(x.get("dir"), 0) * 0.5 + x["tone"] * 0.5
    avg = sum(val(x) * TIER_W[x["tier"]] for x in items) / wsum  # ważone wiarygodnością źródła
    pos = sum(x.get("dir") == "up" for x in items); neg = sum(x.get("dir") == "down" for x in items)
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
            "items": [{k: x[k] for k in ("title", "link", "source", "date", "lang", "tone", "tier", "dir", "why")} for x in shown]}


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


# ---------- świece japońskie ----------
PATTERN_DIR = {"hammer": "up", "inv_hammer": "up", "bull_engulf": "up", "bull_harami": "up", "piercing": "up",
               "morning_star": "up", "three_soldiers": "up", "bull_marubozu": "up",
               "hanging_man": "down", "shooting_star": "down", "bear_engulf": "down", "bear_harami": "down",
               "dark_cloud": "down", "evening_star": "down", "three_crows": "down", "bear_marubozu": "down",
               "doji": "neutral"}

def patterns_at(o, h, l, c, i):
    """Formacje świecowe kończące się na świecy i (bez zaglądania w przyszłość)."""
    if i < 12:
        return []
    def body(k): return abs(c[k] - o[k])
    def rng(k): return max(h[k] - l[k], 1e-12)
    def up(k): return c[k] > o[k]
    def upper(k): return h[k] - max(o[k], c[k])
    def lower(k): return min(o[k], c[k]) - l[k]
    avg_body = mean([body(k) for k in range(i - 10, i)]) or 1e-12
    down_tr = c[i - 1] < sma(c, i - 1, 10)
    up_tr = c[i - 1] > sma(c, i - 1, 10)
    out = []
    b, r = body(i), rng(i)
    if b <= 0.1 * r and r > 0.5 * avg_body:
        out.append("doji")
    if lower(i) >= 2 * b and upper(i) <= 0.25 * r and b > 0.05 * r:
        out.append("hammer" if down_tr else "hanging_man" if up_tr else None)
    if upper(i) >= 2 * b and lower(i) <= 0.25 * r and b > 0.05 * r:
        out.append("inv_hammer" if down_tr else "shooting_star" if up_tr else None)
    if b >= 0.85 * r and b > 1.5 * avg_body:
        out.append("bull_marubozu" if up(i) else "bear_marubozu")
    p = i - 1
    if not up(p) and up(i) and o[i] <= c[p] and c[i] >= o[p] and b > body(p) and down_tr:
        out.append("bull_engulf")
    if up(p) and not up(i) and o[i] >= c[p] and c[i] <= o[p] and b > body(p) and up_tr:
        out.append("bear_engulf")
    if body(p) > avg_body and b < 0.5 * body(p) and max(o[i], c[i]) <= max(o[p], c[p]) and min(o[i], c[i]) >= min(o[p], c[p]):
        if not up(p) and up(i) and down_tr:
            out.append("bull_harami")
        if up(p) and not up(i) and up_tr:
            out.append("bear_harami")
    mid = (o[p] + c[p]) / 2
    if not up(p) and body(p) > avg_body and up(i) and o[i] < c[p] and mid < c[i] < o[p]:
        out.append("piercing")
    if up(p) and body(p) > avg_body and not up(i) and o[i] > c[p] and o[p] < c[i] < mid:
        out.append("dark_cloud")
    a = i - 2
    if body(a) > avg_body and body(p) < 0.4 * body(a):
        if not up(a) and up(i) and c[i] > (o[a] + c[a]) / 2 and down_tr:
            out.append("morning_star")
        if up(a) and not up(i) and c[i] < (o[a] + c[a]) / 2 and up_tr:
            out.append("evening_star")
    three = [i - 2, i - 1, i]
    if all(up(k) and body(k) > 0.6 * rng(k) for k in three) and c[i - 2] < c[i - 1] < c[i]:
        out.append("three_soldiers")
    if all(not up(k) and body(k) > 0.6 * rng(k) for k in three) and c[i - 2] > c[i - 1] > c[i]:
        out.append("three_crows")
    return [x for x in out if x]

def candle_patterns(H, hzn=3, keep=260):
    """Formacje z ostatniego roku + jak działały na tym instrumencie w 5 lat (po 3 sesjach)."""
    o, h, l, c = H["o"], H["h"], H["l"], H["c"]
    n = len(c)
    stats, recent = {}, []
    base = [c[i + hzn] > c[i] for i in range(12, n - hzn)]
    for i in range(12, n):
        for key in patterns_at(o, h, l, c, i):
            if i >= n - keep:
                recent.append({"i": i - (n - keep), "key": key})
            if i < n - hzn:
                s_ = stats.setdefault(key, [0, 0, 0.0])
                s_[0] += 1; s_[1] += c[i + hzn] > c[i]; s_[2] += c[i + hzn] / c[i] - 1
    out_stats = {k: {"n": v[0], "up": v[1] / v[0], "avg": v[2] / v[0]} for k, v in stats.items() if v[0] >= 5}
    return recent, out_stats, (mean([float(x) for x in base]) if base else 0.5)


# ---------- szansa w najbliższych godzinach ----------
def hourly_chance(sym, hz=4):
    """Szansa, że za ok. 4 godziny handlu cena będzie wyżej – z historii świec godzinowych (6 miesięcy)."""
    d = get_json(chart_url(sym, "6mo", "60m"))["chart"]["result"][0]
    c = [x for x in d["indicators"]["quote"][0]["close"] if x is not None]
    n = len(c)
    if n < 200:
        return None
    def state(i): return (c[i] > c[i - 1], c[i] > sma(c, i, 20), rsi_bucket(rsi(c, i)))
    states = {i: state(i) for i in range(21, n)}
    split = int(n * 0.7)
    def table(lo, hi):
        t = {}
        for i in range(lo, hi - hz):
            x = t.setdefault(states[i], [0, 0]); x[0] += c[i + hz] > c[i]; x[1] += 1
        return t
    def prob(t, st_, base):
        u, m = t.get(st_, [0, 0]); return (u + base * 20) / (m + 20)
    base_tr = mean([float(c[i + hz] > c[i]) for i in range(21, split - hz)])
    tr = table(21, split)
    hits = [(prob(tr, states[i], base_tr) > 0.5) == (c[i + hz] > c[i]) for i in range(split, n - hz)
            if abs(prob(tr, states[i], base_tr) - 0.5) > 0.005]
    full = table(21, n)
    base = mean([float(c[i + hz] > c[i]) for i in range(21, n - hz)])
    p = prob(full, states[n - 1], base)
    return {"p": round(p * 100, 1), "acc": round(100 * mean([float(x) for x in hits]), 1) if len(hits) > 30 else None,
            "n": full.get(states[n - 1], [0, 0])[1], "base": round(base * 100, 1),
            "trend": "rośnie" if states[n - 1][1] else "spada"}


# ---------- co news oznacza dla ceny ----------
R_RATE_CUT = r"rate cuts?|cuts? (interest )?rates|obniżk\w* stóp|obniż\w* stopy|dovish"
R_RATE_HIKE = r"rate hikes?|hikes? (interest )?rates|raises? rates|podwyżk\w* stóp|podniesie stopy|hawkish"
NEWS_RULES = [  # (wzorzec, dla jakich rynków, kierunek, wyjaśnienie)
    (r"beats? (estimates|expectations|forecasts)|tops estimates|lepsze od oczekiwań|powyżej oczekiwań|above expectations",
     "stocks", "up", "Wyniki lepsze od oczekiwań zwykle podnoszą cenę akcji."),
    (r"miss(es)? (estimates|expectations)|gorsze od oczekiwań|poniżej oczekiwań|below expectations|falls short",
     "stocks", "down", "Wyniki gorsze od oczekiwań zwykle obniżają cenę akcji."),
    (r"upgrade|podwyższ\w* rekomendac|raises? (its |price )?target|podnosi cenę docelową", "stocks", "up",
     "Analitycy podnieśli ocenę lub cenę docelową – to często przyciąga kupujących."),
    (r"downgrade|obniż\w* rekomendac|cuts? (its |price )?target|lowers? (its |price )?target|obniża cenę docelową",
     "stocks", "down", "Analitycy obniżyli ocenę – część inwestorów sprzedaje."),
    (r"raises? (guidance|outlook|forecast)|podnosi prognoz", "stocks", "up",
     "Spółka podniosła prognozy – rynek zwykle nagradza lepsze perspektywy."),
    (r"(cuts?|lowers?) (guidance|outlook|forecast)|obniża prognoz|profit warning", "stocks", "down",
     "Spółka obniżyła prognozy – to zwykle mocno ciąży cenie."),
    (r"buyback|skup\w* akcji", "stocks", "up", "Skup akcji własnych zmniejsza liczbę akcji na rynku i wspiera cenę."),
    (r"lawsuit|probe|investigation|antitrust|pozew|śledztw|\bkar[aęy]\b|fined?\b", "stocks crypto", "down",
     "Problemy prawne zwiększają niepewność i zwykle ciążą cenie."),
    (r"dividend|dywidend", "stocks", "up", "Dywidenda przyciąga inwestorów (w dniu odcięcia cena spada o jej wartość)."),
    (R_RATE_CUT, "stocks metals crypto", "up", "Niższe stopy procentowe to tańszy pieniądz – zwykle pomaga akcjom, złotu i krypto."),
    (R_RATE_HIKE, "stocks metals crypto", "down", "Wyższe stopy procentowe zwykle szkodzą akcjom, złotu i krypto."),
    (r"inflation (cools|eases|slows|falls)|inflacja (spada|hamuje|niższa|zwalnia)", "stocks metals crypto", "up",
     "Słabnąca inflacja zwiększa szansę na obniżki stóp."),
    (r"inflation (heats|hotter|rises|jumps|accelerates)|hot(ter)? cpi|inflacja (rośnie|przyspiesza|wyższa)",
     "stocks crypto", "down", "Rosnąca inflacja oddala obniżki stóp – zwykle szkodzi akcjom."),
    (r"strong(er)? dollar|dollar (rises|gains|strengthens|jumps|climbs)|dolar (zyskuje|umacnia|rośnie|drożeje)",
     "metals", "down", "Silny dolar zwykle ciąży złotu i srebru (są wyceniane w dolarach)."),
    (r"weak(er)? dollar|dollar (falls|slips|weakens|drops|slides)|dolar (traci|słabnie|tanieje)", "metals", "up",
     "Słabszy dolar zwykle pomaga złotu i srebru."),
    (r"safe.haven|bezpieczn\w* przystan|geopolit|\bwar\b|wojn|conflict|konflikt|tensions|napięci", "metals", "up",
     "Niepokój na świecie zwiększa popyt na złoto i srebro jako „bezpieczną przystań”."),
    (r"central banks? (buy|buying|purchases|add)|banki centralne kupują|zakupy banków centralnych", "metals", "up",
     "Zakupy banków centralnych to duży, stały popyt na złoto."),
    (r"opec\+? (cut|cuts|reduce|curbs)|output cuts?|production cuts?|cięci\w* wydobyci|ogranicz\w* wydobyci", "oil", "up",
     "Mniejsze wydobycie oznacza mniej ropy na rynku – zwykle wyższa cena."),
    (r"opec\+? (raise|raises|increase|boost|hike)|output (hike|increase|boost)|zwiększ\w* wydobyci", "oil", "down",
     "Większe wydobycie oznacza więcej ropy na rynku – zwykle niższa cena."),
    (r"inventor(y|ies) (build|rise|jump|climb)|crude stocks rise|wzrost zapasów", "oil", "down",
     "Rosnące zapasy ropy oznaczają słabszy popyt – zwykle niższa cena."),
    (r"inventor(y|ies) (draw|fall|drop|decline)|spadek zapasów", "oil", "up",
     "Spadające zapasy oznaczają silny popyt – zwykle wyższa cena ropy."),
    (r"sanction|sankcj|supply disruption|attack|atak|blockade|blokad", "oil", "up",
     "Zakłócenia dostaw zmniejszają podaż ropy – zwykle cena rośnie."),
    (r"recession|recesj|slowdown|spowolni", "stocks oil crypto", "down",
     "Obawy o spowolnienie gospodarki zwykle szkodzą akcjom i ropie."),
    (r"recession|recesj|slowdown|spowolni", "metals", "up", "Obawy o recesję zwykle zwiększają popyt na złoto."),
    (r"tariffs?|\bcł[aoey]\b|trade war|wojn\w* handlow", "stocks oil crypto", "down",
     "Cła zwiększają koszty i niepewność – zwykle szkodzą akcjom."),
    (r"yields? (rise|rises|climb|jump|surge|higher|spike)|higher (bond )?yields|rentownoś\w* (rosną|rośnie)", "stocks metals crypto", "down",
     "Rosnące rentowności obligacji przyciągają pieniądze – zwykle szkodzi akcjom i złotu."),
    (r"yields? (fall|falls|drop|ease|decline|lower)|lower (bond )?yields|rentownoś\w* (spadają|spada)", "stocks metals crypto", "up",
     "Spadające rentowności obligacji zwykle pomagają akcjom i złotu."),
    (r"etfs? (bleed|outflows?)", "crypto", "down", "Odpływ pieniędzy z funduszy ETF oznacza sprzedających."),
    (r"etf (inflows?|approval|approved)|napływ\w* do (funduszy|etf)", "crypto", "up",
     "Napływ pieniędzy do funduszy ETF oznacza nowych kupujących."),
    (r"etf outflows?|odpływ\w* z (funduszy|etf)", "crypto", "down", "Odpływ pieniędzy z funduszy ETF oznacza sprzedających."),
    (r"\bhack|exploit|włamani|kradzież", "crypto", "down", "Włamania i kradzieże podważają zaufanie do kryptowalut."),
    (r"record high|all-time high|rekordow\w* wysok|najwyżej w historii|historyczn\w* szczyt", "stocks metals crypto oil", "up",
     "Cena na rekordach – trend jest silny, choć rośnie ryzyko chwilowej korekty."),
]
TONE_WHY = {"up": "W nagłówku przeważają pozytywne słowa (np. wzrost, zysk, odbicie).",
            "down": "W nagłówku przeważają negatywne słowa (np. spadek, strata, obawy).",
            "neutral": "Nagłówek nie wskazuje wyraźnie kierunku ceny."}

def market_kind(symbol, group):
    if symbol in ("GC=F", "SI=F", "PL=F", "PA=F", "HG=F"):
        return "metals"
    if symbol in ("CL=F", "BZ=F", "NG=F"):
        return "oil"
    return "crypto" if group == "Krypto" else "stocks"

def interpret(text, kind):
    for pat, kinds, d, why in NEWS_RULES:
        if kind in kinds.split() and re.search(pat, text):
            return d, why
    t = tone(text)
    d = "up" if t > 0.2 else "down" if t < -0.2 else "neutral"
    return d, TONE_WHY[d]


# ---------- potencjał: czy coś ma teraz największy potencjał ----------
def potential(H, rc, setups, news_tone, soon_days, risk_lvl, p_hours, pats):
    c, h, l, v = H["c"], H["h"], H["l"], H.get("v") or []
    i = len(c) - 1
    score, plus, minus = 42.0, [], []
    s20, s50, rs, R = sma(c, i, 20), sma(c, i, 50), rsi(c, i), max(h[i - 20:i])
    if c[i] > s50:
        score += 8; plus.append("Trend średnioterminowy w górę (cena nad średnią z 50 dni).")
    else:
        score -= 8; minus.append("Cena pod średnią z 50 dni – trend średnioterminowy w dół.")
    score += 6 if c[i] > s20 else -6
    if s20 > s50 and c[i] > s20:
        score += 4; plus.append("Krótki trend jest silniejszy od średniego – ruch w górę przyspiesza.")
    if c[i] > R:
        score += 10; plus.append(f"Wybicie: cena zamknęła się nad szczytem z 20 sesji ({fp(R)}).")
    elif c[i] >= R * 0.98:
        score += 4; plus.append(f"Cena tuż pod oporem {fp(R)} – możliwe wybicie.")
    if 50 <= rs <= 70:
        score += 6; plus.append(f"RSI {rs:.0f}: kupujący mają przewagę, rynek nie jest przegrzany.")
    elif rs > 75:
        score -= 8; minus.append(f"RSI {rs:.0f}: rynek przegrzany – łatwo o korektę.")
    elif rs < 30:
        score -= 2; minus.append(f"RSI {rs:.0f}: silne spadki – możliwe odbicie, ale to łapanie spadającego noża.")
    if len(v) > 21 and v[i] and mean(v[i - 20:i]) > 0:
        ratio = v[i] / mean(v[i - 20:i])
        if ratio > 1.5 and c[i] > c[i - 1]:
            score += 6; plus.append(f"Obrót {ratio:.1f}× większy niż zwykle przy wzroście – duże zainteresowanie kupujących.".replace(".", ",", 1))
        elif ratio > 1.5 and c[i] < c[i - 1]:
            score -= 6; minus.append(f"Obrót {ratio:.1f}× większy niż zwykle przy spadku – ktoś mocno sprzedaje.".replace(".", ",", 1))
    if rc and i >= 21 and rc[i - 21]:
        rel = (c[i] / c[i - 21] - 1) - (rc[i] / rc[i - 21] - 1)
        if rel > 0.03:
            score += 5; plus.append(f"W ostatnim miesiącu silniejszy od rynku o {rel * 100:.0f} pkt proc.")
        elif rel < -0.05:
            score -= 4; minus.append(f"W ostatnim miesiącu słabszy od rynku o {abs(rel) * 100:.0f} pkt proc.")
    g, a = (setups or {}).get("good"), (setups or {}).get("all")
    if g and a and c[i] > s50 and c[i] > s20:
        edge = (g["up"] - a["up"]) * 100
        score += max(-8, min(8, edge))
        if edge > 3:
            plus.append(f"Na tym instrumencie takie warunki w przeszłości działały: po tygodniu wyżej w {g['up'] * 100:.0f}% (zwykle {a['up'] * 100:.0f}%).")
        elif edge < -3:
            minus.append(f"Na tym instrumencie takie warunki w przeszłości nie działały ({g['up'] * 100:.0f}% vs zwykle {a['up'] * 100:.0f}%).")
    if news_tone is not None and abs(news_tone) > 0.1:
        score += news_tone * 10
        (plus if news_tone > 0 else minus).append("Wiadomości z ostatnich dni są " + ("pozytywne." if news_tone > 0 else "negatywne."))
    for pt in pats:
        d = PATTERN_DIR.get(pt, "neutral")
        if d != "neutral":
            score += 4 if d == "up" else -4
    if p_hours is not None:
        score += 3 if p_hours > 55 else -3 if p_hours < 45 else 0
    sd = st.stdev([c[k] / c[k - 1] - 1 for k in range(i - 59, i + 1)])
    day = c[i] / c[i - 1] - 1
    if sd and day > 3 * sd:
        score -= 12; minus.append(f"Dziś już mocno urosło ({fpc(day)}, zwykle ±{pct1(sd)}) – kupowanie po takim skoku "
                                  "to „gonienie ceny”; często lepiej poczekać na uspokojenie lub cofnięcie.")
    elif sd and day < -3 * sd:
        score -= 6; minus.append(f"Dziś gwałtowny spadek ({fpc(day)}) – poczekaj, aż sytuacja się wyjaśni.")
    if soon_days is not None:
        score -= 12; minus.append(f"Wyniki spółki {('dziś' if soon_days == 0 else 'jutro' if soon_days == 1 else f'za {soon_days} dni')} – cena może nagle skoczyć w dowolną stronę.")
    if risk_lvl >= 4:
        score -= 15; minus.append("Bardzo wysoka zmienność – łatwo o dużą stratę, nie dla początkujących.")
    elif risk_lvl == 3:
        score -= 5
    return round(max(0, min(100, score))), plus, minus

def vol_level(ann): return 1 if ann < 0.15 else 2 if ann < 0.35 else 3 if ann < 0.60 else 4
RISK_LABEL = ["Niskie", "Umiarkowane", "Wysokie", "Bardzo wysokie"]


# ---------- skaner rynku (spoza listy) ----------
UNIVERSE = ["PKN.WA", "PKO.WA", "PZU.WA", "PEO.WA", "KGH.WA", "CDR.WA", "LPP.WA", "DNP.WA", "ALE.WA", "SPL.WA",
            "MBK.WA", "CPS.WA", "OPL.WA", "PGE.WA", "TPE.WA", "JSW.WA", "KTY.WA", "KRU.WA", "ALR.WA", "BDX.WA",
            "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AVGO", "JPM", "V", "LLY", "XOM", "WMT",
            "AMD", "NFLX", "COST", "ORCL", "PLTR", "INTC", "BA", "DIS", "KO", "UNH", "MU", "CRM",
            "GC=F", "SI=F", "CL=F", "BZ=F", "NG=F", "HG=F", "PL=F",
            "BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "BNB-USD", "^GSPC", "^NDX", "^GDAXI"]

def group_of(sym, typ=""):
    if sym.endswith(".WA"): return "Akcje GPW"
    if sym.endswith("=F"): return "Surowce"
    if sym.endswith("-USD") or typ == "CRYPTOCURRENCY": return "Krypto"
    if sym.startswith("^") or typ == "INDEX": return "Indeksy"
    if typ == "ETF": return "ETF"
    return "Akcje USA" if "." not in sym else "Akcje – świat"

def ref_for(sym, group):
    if group == "Akcje GPW": return "ETFBW20TR.WA"
    if group == "Krypto": return "^IXIC"
    if sym in ("GC=F", "SI=F", "PL=F", "HG=F"): return "DX-Y.NYB"
    return "^GSPC" if sym != "^GSPC" else "^VIX"

def market_movers():
    syms = []
    for url in ("https://query1.finance.yahoo.com/v1/finance/trending/US?count=20",
                "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?scrIds=day_gainers&count=15",
                "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?scrIds=most_actives&count=15"):
        try:
            for q in get_json(url)["finance"]["result"][0]["quotes"]:
                if q.get("marketCap", 1e12) >= 2e9 and q.get("regularMarketPrice", 10) >= 5:
                    syms.append(q["symbol"])
        except Exception as e:
            print("Lista popularnych pominięta:", e)
    return syms

def scan(prev_scan, own):
    if prev_scan and NOW.minute >= 15 and dt.datetime.fromisoformat(prev_scan["time"]) > NOW - dt.timedelta(hours=2):
        return prev_scan  # skaner działa raz na godzinę
    syms = list(dict.fromkeys(UNIVERSE + market_movers()))
    out = []
    for sym in syms:
        try:
            H = history(sym, "2y")
            c, n = H["c"], len(H["c"])
            if n < 150 or c[-1] <= 0:
                continue
            group = group_of(sym, H["type"])
            if group in ("Akcje USA", "Akcje – świat") and mean([a * b for a, b in zip(c[-20:], H["v"][-20:])]) < 5e6:
                continue
            rs_ = ref_for(sym, group)
            rc = align(H["d"], history(rs_, "2y")) if rs_ else None
            S = {"d": H["d"], "c": c, "h": H["h"], "l": H["l"], "r": rets(c), "rc": rc, "rr": rets(rc) if rc else None}
            crypto = group == "Krypto"
            sd = st.stdev(S["r"][-60:]); ann = sd * math.sqrt(365 if crypto else 252)
            setups = setup_history(S, 7 if crypto else 5)
            pats = patterns_at(H["o"], H["h"], H["l"], c, n - 1) + patterns_at(H["o"], H["h"], H["l"], c, n - 2)
            score, plus, minus = potential(H, rc, setups, None, None, vol_level(ann), None, pats)
            a = atr(H["h"], H["l"], c, n - 1)
            out.append({"symbol": sym, "name": H["name"], "group": group, "currency": H["cur"], "price": c[-1],
                        "change": (c[-1] / c[-2] - 1) * 100, "score": score, "plus": plus, "minus": minus,
                        "risk": vol_level(ann), "risk_label": RISK_LABEL[vol_level(ann) - 1], "ann": ann,
                        "stop": c[-1] - 2 * a, "target": c[-1] + 3 * a, "own": sym in own, "pats": pats,
                        "spark": [float(f"{x:.6g}") for x in c[-30:]]})
        except Exception as e:
            print("Skaner pominął", sym, e)
    out.sort(key=lambda x: -x["score"])
    for x in out[:10]:  # dla najciekawszych: newsy i daty wyników
        kind = market_kind(x["symbol"], x["group"])
        try:
            q = x["name"].split(",")[0].replace(" Inc.", "").replace(" Corporation", "")
            news = [n for n in google(q + (" stock" if kind == "stocks" else ""), "en") if n["date"] and
                    (NOW - n["date"]).days <= 4][:30]
            for n in news:
                n["tier"] = tier_of(n["source"])
            news.sort(key=lambda n: (n["tier"], NOW - n["date"]))
            x["news"] = []
            for n in news[:3]:
                d_, why = interpret(n["title"].lower(), kind)
                x["news"].append({"title": n["title"], "link": n["link"], "source": n["source"], "tier": n["tier"],
                                  "date": n["date"].isoformat(), "dir": d_, "why": why})
            tn = [tone(n["title"].lower()) for n in news[:15]]
            if tn:
                adj = mean(tn) * 10
                x["score"] = round(max(0, min(100, x["score"] + adj)))
                if abs(adj) > 1:
                    (x["plus"] if adj > 0 else x["minus"]).append(
                        "Wiadomości z ostatnich dni są " + ("pozytywne." if adj > 0 else "negatywne."))
        except Exception as e:
            print("Newsy skanera pominięte:", x["symbol"], e)
        if x["group"] == "Akcje USA":
            try:
                ev = nasdaq_earnings({"symbol": x["symbol"], "name": x["name"]})
                if ev:
                    days = (dt.date.fromisoformat(ev[0]["date"]) - TODAY_PL).days
                    x["earnings_days"] = days
                    if 0 <= days <= 3:
                        x["score"] = max(0, x["score"] - 12)
                        x["minus"].append(f"Wyniki spółki za {days} dni – ryzyko nagłego skoku ceny.")
            except Exception:
                pass
    out.sort(key=lambda x: -x["score"])
    return {"time": NOW.isoformat(), "items": out}


# ---------- najważniejsze wiadomości ze świata ----------
WORLD_Q = [("stock market today", "en", "stocks"), ("Federal Reserve interest rates", "en", "stocks"),
           ("oil prices", "en", "oil"), ("gold prices", "en", "metals"), ("bitcoin price", "en", "crypto"),
           ("giełda GPW WIG20", "pl", "stocks")]

def world_news(prev_world, instruments):
    if prev_world and NOW.minute >= 15 and dt.datetime.fromisoformat(prev_world["time"]) > NOW - dt.timedelta(hours=2):
        return prev_world
    seen, out = set(), []
    for q, lang, kind in WORLD_Q:
        try:
            for n in google(q, lang):
                if not n["date"] or (NOW - n["date"]).total_seconds() > 2 * 86400:
                    continue
                t = tier_of(n["source"])
                key = re.sub(r"\W+", "", n["title"].lower())[:50]
                if t > 1 or key in seen:
                    continue
                seen.add(key)
                text = n["title"].lower()
                d_, why = interpret(text, kind)
                hits = [i["name"] for i in instruments if any(k in text for k in i["keywords"])]
                out.append({"title": n["title"], "link": n["link"], "source": n["source"], "tier": t, "lang": lang,
                            "date": n["date"].isoformat(), "dir": d_, "why": why, "kind": kind, "names": hits[:4]})
        except Exception as e:
            print("Wiadomości ze świata pominięte:", q, e)
    out.sort(key=lambda x: x["date"], reverse=True)
    return {"time": NOW.isoformat(), "items": out[:14]}


# ---------- zmiany od ostatniej aktualizacji ----------
def detect_changes(items, prev):
    old = {i["symbol"]: i for i in (prev or {}).get("items", [])}
    keep = [c for c in (prev or {}).get("changes", [])
            if dt.datetime.fromisoformat(c["time"]) > NOW - dt.timedelta(days=3)]
    keys = {(c["symbol"], c["kind"], c["time"][:10]) for c in keep}
    new = []
    def add(it, kind, d, text):
        k = (it["symbol"], kind, NOW.isoformat()[:10])
        if k not in keys:
            keys.add(k)
            new.append({"symbol": it["symbol"], "name": it["name"], "kind": kind, "dir": d, "text": text,
                        "time": NOW.isoformat()})
    rank = {"no": 0, "wait": 1, "go": 2}
    for it in items:
        p = old.get(it["symbol"])
        if not p or "decision" not in p:
            continue
        a, b = p["decision"]["key"], it["decision"]["key"]
        if a != b:
            up_ = rank[b] > rank[a]
            add(it, "decision", "up" if up_ else "down",
                f"Ocena zmieniła się: „{p['decision']['title']}” → „{it['decision']['title']}”."
                + ("" if up_ else " Jeśli planowałeś wejście – wstrzymaj się."))
        R, S_ = p["levels"]["R"], p["levels"]["S"]
        if p["price"] <= R < it["price"]:
            add(it, "breakout", "up", f"Wybicie w górę: cena {fp(it['price'])} przebiła opór {fp(R)}.")
        if p["price"] >= S_ > it["price"]:
            add(it, "breakdown", "down", f"Cena {fp(it['price'])} spadła poniżej wsparcia {fp(S_)} – sygnał ostrzegawczy.")
        sd = it["levels"]["sd60"]
        if sd and abs(it["change"]) / 100 > 2.5 * sd:
            add(it, "move", "up" if it["change"] > 0 else "down",
                f"Nietypowo duży ruch dziś: {fpc(it['change'] / 100)} (zwykle ±{pct1(sd)}).")
    return (new + keep)[:40], new


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
    hours = None
    try:
        hours = hourly_chance(ins["symbol"])
    except Exception as e:
        print("Brak danych godzinowych:", ins["symbol"], e)
    pats, pstats, pbase = candle_patterns(H)
    last_pats = [x["key"] for x in pats if x["i"] >= 258]  # formacje z 2 ostatnich świec
    earn = next((e["days"] for e in my_events if e["kind"] == "wyniki" and 0 <= e["days"] <= 3), None)
    pot, plus, minus = potential(H, S["rc"], setups, week["tone"] if week["count"] else None, earn, risk["level"],
                                 hours["p"] if hours else None, last_pats)
    K = 260

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
            "intra": intra, "hours": hours,
            "potential": {"score": pot, "plus": plus, "minus": minus},
            "ohlc": {"o": [float(f"{x:.6g}") for x in H["o"][-K:]], "h": [float(f"{x:.6g}") for x in H["h"][-K:]],
                     "l": [float(f"{x:.6g}") for x in H["l"][-K:]], "c": [float(f"{x:.6g}") for x in c[-K:]],
                     "dd": [d.toordinal() - t0 for d in days[-K:]]},
            "patterns": pats, "pattern_stats": pstats, "pattern_base": pbase,
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


def notify(items, new_changes):
    """Powiadomienia na telefon (aplikacja ntfy), jeśli w GitHubie ustawiono sekret NTFY_TOPIC."""
    topic = os.environ.get("NTFY_TOPIC")
    if not topic or not new_changes:
        return
    for ch in new_changes:
        body = json.dumps({"topic": topic, "title": f"{ch['name']} – Centrum rynku", "message": ch["text"],
                           "tags": ["chart_with_upwards_trend" if ch["dir"] == "up" else "warning"],
                           "click": SITE + "#i=" + urllib.parse.quote(ch["symbol"])}).encode()
        try:
            urllib.request.urlopen(urllib.request.Request("https://ntfy.sh/", data=body,
                                                          headers={"Content-Type": "application/json"}), timeout=15)
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
    changes, new_changes = detect_changes(items, prev)
    sc = scan((prev or {}).get("scan"), {i["symbol"] for i in instruments})
    world = world_news((prev or {}).get("world"), instruments)
    notify(items, new_changes)
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump({"updated": NOW.isoformat(), "pulse": pulse(), "fx": fx, "calendar": cal, "items": items,
                   "changes": changes, "scan": sc, "world": world},
                  f, ensure_ascii=False, separators=(",", ":"))
    print("Zapisano", len(items), "instrumentów,", len(cal), "wydarzeń w kalendarzu")

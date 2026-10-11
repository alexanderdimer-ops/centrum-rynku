import json, math, statistics as st, urllib.request, datetime as dt
import xml.etree.ElementTree as ET

UA = {"User-Agent": "Mozilla/5.0"}
FEEDS = ["https://www.bankier.pl/rss/wiadomosci.xml", "https://www.bankier.pl/rss/gielda.xml",
         "https://www.bankier.pl/rss/surowce.xml", "https://www.bankier.pl/rss/waluty.xml"]
POS = ["wzrost", "rośnie", "rosną", "zysk", "rekord", "odbicie", "dywidend", "poprawa", "przejęci", "umocnien"]
NEG = ["spadek", "spadk", "spada", "strata", "obaw", "kryzys", "przecen", "cięci", "kara", "pozew", "wyprzedaż", "załamani", "osłabien"]

def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read()

def history(sym):
    d = json.loads(get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=2y&interval=1d"))["chart"]["result"][0]
    rows = [(t, c) for t, c in zip(d["timestamp"], d["indicators"]["quote"][0]["close"]) if c]
    return rows, d["meta"].get("currency", "")

def news():
    out = []
    for f in FEEDS:
        try:
            for it in ET.fromstring(get(f)).iter("item"):
                title = it.findtext("title") or ""
                text = (title + " " + (it.findtext("description") or "")).lower()
                p, n = sum(w in text for w in POS), sum(w in text for w in NEG)
                out.append({"title": title, "link": it.findtext("link"), "text": text,
                            "tone": (p - n) / max(1, p + n)})
        except Exception as e:
            print("RSS pominięty:", f, e)
    return out

def phi(x): return 0.5 * (1 + math.erf(x / math.sqrt(2)))
def clamp(p): return round(max(5, min(95, p)), 1)

def rsi(c, n=14):
    g = sum(max(c[i] - c[i-1], 0) for i in range(-n, 0)); l = sum(max(c[i-1] - c[i], 0) for i in range(-n, 0))
    return 100 if l == 0 else 100 - 100 / (1 + g / l)

def methods(rows, tone):
    c = [x for _, x in rows]
    r = [c[i] / c[i-1] - 1 for i in range(1, len(c))]
    m = []
    nxt = [r[i+1] > 0 for i in range(len(r) - 1) if (r[i] > 0) == (r[-1] > 0)]
    m.append({"name": "Historia: po takiej samej sesji", "p": clamp(100 * sum(nxt) / len(nxt)), "note": f"{len(nxt)} podobnych sesji z 2 lat"})
    wd = dt.datetime.utcnow().weekday(); wd = wd if wd < 5 else 0
    same = [r[i] > 0 for i in range(len(r)) if dt.datetime.utcfromtimestamp(rows[i+1][0]).weekday() == wd]
    m.append({"name": "Sezonowość: ten dzień tygodnia", "p": clamp(100 * sum(same) / len(same)), "note": f"{len(same)} takich dni w historii"})
    s20, s50, rs = sum(c[-20:]) / 20, sum(c[-50:]) / 50, rsi(c)
    p = 50 + (8 if c[-1] > s20 else -8) + (7 if c[-1] > s50 else -7) + (8 if rs < 30 else -8 if rs > 70 else (rs - 50) * 0.2)
    m.append({"name": "Trend i momentum", "p": clamp(p), "note": f"RSI {rs:.0f}, cena vs średnie 20/50 dni (heurystyka)"})
    mu, sd = sum(r[-20:]) / 20, st.stdev(r[-60:])
    m.append({"name": "Model zmienności", "p": clamp(50 + (100 * phi(mu / sd) - 50) * 0.5), "note": "średni ruch 20 dni vs wahania 60 dni"})
    m.append({"name": "Nastrój polskich newsów", "p": None if tone is None else clamp(50 + tone * 20),
              "note": "brak newsów o tym instrumencie" if tone is None else "słownikowa ocena nagłówków"})
    return m

def verdict(p):
    return "Sprzyjające warunki" if p >= 58 else "Neutralnie, poczekaj na sygnał" if p >= 46 else "Niekorzystne warunki"

items, N = [], news()
for ins in json.load(open("instruments.json", encoding="utf-8")):
    try:
        rows, cur = history(ins["symbol"])
        rel = [n for n in N if any(k in n["text"] for k in ins["keywords"])]
        tone = sum(n["tone"] for n in rel) / len(rel) if rel else None
        m = methods(rows, tone)
        ok = [x["p"] for x in m if x["p"] is not None]
        overall = round(sum(ok) / len(ok), 1)
        items.append({"symbol": ins["symbol"], "name": ins["name"], "group": ins["group"], "currency": cur,
                      "price": rows[-1][1], "change": 100 * (rows[-1][1] / rows[-2][1] - 1),
                      "methods": m, "overall": overall, "verdict": verdict(overall),
                      "news": [{"title": n["title"], "link": n["link"], "tone": n["tone"]} for n in rel[:6]]})
    except Exception as e:
        print("Pominięto", ins["symbol"], e)
json.dump({"updated": dt.datetime.utcnow().isoformat() + "Z", "items": items}, open("data.json", "w", encoding="utf-8"), ensure_ascii=False)
print("Zapisano", len(items), "instrumentów")

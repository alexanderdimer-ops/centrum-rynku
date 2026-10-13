"""Dodatkowe, niezależne źródła informacji (wszystkie darmowe, bez kluczy):
- COT (CFTC): jak ustawione są fundusze na złocie, srebrze i ropie,
- prognozy analityków (Nasdaq): cena docelowa i rekomendacje dla spółek z USA,
- reakcje na wyniki: jak mocno cena ruszała się po poprzednich raportach (USA: Nasdaq, GPW: Bankier),
- sezonowość miesięczna: jak instrument zachowywał się w danym miesiącu przez wiele lat (Yahoo, dane miesięczne),
- sektor: czy cała branża spółki rośnie i czy spółka jest od niej silniejsza (fundusze sektorowe ETF).
"""
import re, math, statistics as st, datetime as dt, urllib.parse

COT_CODES = {"GC=F": ("088691", "złoto"), "SI=F": ("084691", "srebro"), "BZ=F": ("067651", "ropa (WTI)"),
             "CL=F": ("067651", "ropa (WTI)")}
SECTOR_ETF = {"Technology": "XLK", "Finance": "XLF", "Energy": "XLE", "Health Care": "XLV",
              "Consumer Discretionary": "XLY", "Consumer Staples": "XLP", "Industrials": "XLI",
              "Basic Materials": "XLB", "Utilities": "XLU", "Real Estate": "XLRE", "Telecommunications": "XLC"}
SECTOR_PL = {"Technology": "technologie", "Finance": "finanse", "Energy": "energia", "Health Care": "ochrona zdrowia",
             "Consumer Discretionary": "dobra konsumpcyjne", "Consumer Staples": "artykuły codziennego użytku",
             "Industrials": "przemysł", "Basic Materials": "surowce i materiały", "Utilities": "użyteczność publiczna",
             "Real Estate": "nieruchomości", "Telecommunications": "telekomunikacja"}
MON_PL = ["styczniu", "lutym", "marcu", "kwietniu", "maju", "czerwcu", "lipcu", "sierpniu", "wrześniu",
          "październiku", "listopadzie", "grudniu"]


def cot(sym, get_json):
    """Pozycje funduszy (managed money) z raportu COT i ich skrajność na tle 3 lat."""
    if sym not in COT_CODES:
        return None
    code, name = COT_CODES[sym]
    url = ("https://publicreporting.cftc.gov/resource/72hh-3qpy.json?" + urllib.parse.urlencode({
        "$where": f"cftc_contract_market_code='{code}'", "$order": "report_date_as_yyyy_mm_dd DESC", "$limit": 160,
        "$select": "report_date_as_yyyy_mm_dd,m_money_positions_long_all,m_money_positions_short_all"}))
    rows = get_json(url, ttl=43200)
    net = [int(r["m_money_positions_long_all"]) - int(r["m_money_positions_short_all"]) for r in rows][::-1]
    if len(net) < 52:
        return None
    lo, hi = min(net), max(net)
    idx = 100 * (net[-1] - lo) / (hi - lo) if hi > lo else 50
    ch4 = net[-1] - net[-5]
    if idx > 85:
        txt, d = (f"Fundusze są bardzo mocno ustawione na wzrost ({name}: {idx:.0f}/100 na tle 3 lat). Rynek jest „zatłoczony” – "
                  "gdy wszyscy już kupili, łatwiej o spadek."), -1
    elif idx < 15:
        txt, d = (f"Fundusze są wyjątkowo pesymistyczne ({name}: {idx:.0f}/100 na tle 3 lat). Historycznie takie skrajności "
                  "często poprzedzały odbicie."), 1
    else:
        txt, d = (f"Fundusze w ostatnich 4 tygodniach {'dokupują' if ch4 > 0 else 'sprzedają'} ({name}: pozycja "
                  f"{idx:.0f}/100 na tle 3 lat) – to {'wspiera' if ch4 > 0 else 'osłabia'} trend wzrostowy."), (1 if ch4 > 0 else -1) * 0.5
    return {"index": round(idx), "net": net[-1], "change4w": ch4, "date": rows[0]["report_date_as_yyyy_mm_dd"][:10],
            "text": txt, "dir": d, "name": name}


def analysts(sym, price, get_json):
    """Cena docelowa analityków (12 miesięcy) i rozkład rekomendacji – tylko spółki z USA."""
    d = get_json(f"https://api.nasdaq.com/api/analyst/{sym}/targetprice", ttl=43200)["data"]
    co = (d or {}).get("consensusOverview") or {}
    if not co.get("priceTarget"):
        return None
    t, b, h, s = co["priceTarget"], co.get("buy", 0), co.get("hold", 0), co.get("sell", 0)
    up = t / price - 1
    tot = max(1, b + h + s)
    ts = f"{t:,.2f}".replace(",", " ").replace(".", ",")
    txt = (f"Analitycy: średnia cena docelowa {ts} USD ({'+' if up >= 0 else '−'}{abs(up) * 100:.0f}% od obecnej ceny), "
           f"rekomendacje: {b} kupuj, {h} trzymaj, {s} sprzedaj.")
    return {"target": t, "low": co.get("lowPriceTarget"), "high": co.get("highPriceTarget"), "upside": up,
            "buy": b, "hold": h, "sell": s, "buy_share": b / tot, "text": txt}


def _move_after(H, day):
    """Ruch ceny wokół daty raportu: od zamknięcia przed raportem do zamknięcia sesji po raporcie."""
    d = H["d"]; c = H["c"]
    before = max((k for k in range(len(d)) if d[k] < day), default=None)
    after = min((k for k in range(len(d)) if d[k] > day), default=None)
    if before is None or after is None or after - before > 4:
        return None
    return c[after] / c[before] - 1


def earnings_moves(ins, H, get_json, get):
    """Jak cena reagowała na poprzednie wyniki (ostatnie raporty)."""
    out = []
    try:
        if ins.get("earnings"):
            rows = get_json(f"https://api.nasdaq.com/api/company/{ins['symbol']}/earnings-surprise", ttl=86400)["data"]
            for r in ((rows or {}).get("earningsSurpriseTable") or {}).get("rows", [])[:4]:
                m_, d_, y_ = (int(x) for x in r["dateReported"].split("/"))
                mv = _move_after(H, dt.date(y_, m_, d_))
                if mv is not None:
                    out.append({"date": dt.date(y_, m_, d_).isoformat(), "move": mv,
                                "surprise": float(r["percentageSurprise"]) if r.get("percentageSurprise") not in (None, "", "N/A") else None})
        elif ins.get("bankier"):
            s = get(f"https://www.bankier.pl/gielda/notowania/akcje/{ins['bankier']}/kalendarium", ttl=21600).decode("utf-8", "ignore")
            today = dt.date.today()
            for m in re.finditer(r'data-timestamp="(\d+)"(.*?)(?=data-timestamp="|$)', s, re.S):
                day = dt.datetime.fromtimestamp(int(m.group(1)) + 4 * 3600, dt.timezone.utc).date()
                if day < today and "Wyniki spółek" in m.group(2) and "raportu" in m.group(2):
                    mv = _move_after(H, day)
                    if mv is not None:
                        out.append({"date": day.isoformat(), "move": mv, "surprise": None})
            out = sorted(out, key=lambda x: x["date"], reverse=True)[:4]
    except Exception as e:
        print("Reakcje na wyniki pominięte:", ins["symbol"], e)
    if not out:
        return None
    avg = st.fmean(abs(x["move"]) for x in out)
    return {"items": out, "avg_abs": avg,
            "text": f"Po ostatnich {len(out)} raportach cena ruszała się średnio o ±{avg * 100:.1f}% w 1–2 sesje."
                    .replace(".", ",", 1)}


def seasonality(sym, get_json, chart_url):
    """Sezonowość: wyniki w bieżącym i następnym miesiącu w kolejnych latach (dane miesięczne, wiele lat)."""
    d = get_json(chart_url(sym, "max", "1mo"), ttl=86400)["chart"]["result"][0]
    ts, cl = d.get("timestamp") or [], d["indicators"]["quote"][0]["close"]
    pts = [(dt.datetime.fromtimestamp(t, dt.timezone.utc).date(), c) for t, c in zip(ts, cl) if c]
    rets = {}
    for (d0, c0), (d1, c1) in zip(pts, pts[1:]):
        if (d1.year * 12 + d1.month) - (d0.year * 12 + d0.month) == 1:
            rets.setdefault(d1.month, []).append(c1 / c0 - 1)
    if not rets:
        return None
    now = dt.date.today().month
    allr = [x for v in rets.values() for x in v]
    base = sum(x > 0 for x in allr) / len(allr)
    def m_(mo):
        v = rets.get(mo, [])
        return None if len(v) < 5 else {"n": len(v), "up": sum(x > 0 for x in v) / len(v), "med": st.median(v)}
    cur, nxt = m_(now), m_(now % 12 + 1)
    txt = ""
    if cur:
        txt = (f"Sezonowość: w {MON_PL[now - 1]} cena rosła w {cur['up'] * 100:.0f}% lat (z {cur['n']}; zwykle w "
               f"{base * 100:.0f}% miesięcy), typowo o {cur['med'] * 100:+.1f}%.").replace(".", ",", 1)
        if cur["n"] < 10:
            txt += " Mało lat danych – traktuj ostrożnie."
    return {"cur": cur, "next": nxt, "base": base, "month": now, "text": txt}


def sector(sym, H, get_json, history):
    """Sektor spółki z USA i porównanie z funduszem sektorowym (ETF)."""
    d = get_json(f"https://api.nasdaq.com/api/quote/{sym}/summary?assetclass=stocks", ttl=604800)["data"]
    sec = (((d or {}).get("summaryData") or {}).get("Sector") or {}).get("value")
    etf = SECTOR_ETF.get(sec)
    if not etf:
        return None
    E = history(etf, "2y")
    ec, c = E["c"], H["c"]
    e1m, s1m = ec[-1] / ec[-22] - 1, c[-1] / c[-22] - 1
    e3m, s3m = ec[-1] / ec[-64] - 1, c[-1] / c[-64] - 1
    e_up = ec[-1] > sum(ec[-50:]) / 50
    rel = s3m - e3m
    txt = (f"Branża ({SECTOR_PL.get(sec, sec)}, fundusz {etf}) jest {'w trendzie wzrostowym' if e_up else 'w trendzie spadkowym'}"
           f" (miesiąc {e1m * 100:+.1f}%). Spółka w 3 miesiące {'silniejsza' if rel > 0 else 'słabsza'} od branży o "
           f"{abs(rel) * 100:.0f} pkt proc.").replace(".", ",", 1)
    return {"sector": sec, "sector_pl": SECTOR_PL.get(sec, sec), "etf": etf, "etf_up": e_up, "etf_1m": e1m,
            "rel_3m": rel, "text": txt}


def insiders(sym, get):
    """Transakcje osób z zarządu i rady nadzorczej (raporty SEC Form 4, zebrane przez OpenInsider) – spółki z USA.
    Zakupy za własne pieniądze to jeden z lepiej udokumentowanych sygnałów; sprzedaże bywają rutynowe (podatki, plany)."""
    s = get(f"http://openinsider.com/screener?s={urllib.parse.quote(sym)}&fd=90&cnt=60", ttl=43200).decode("utf-8", "ignore")
    i = s.find('class="tinytable"')
    if i < 0:
        return None
    buy = sell = 0.0; buyers = set(); n_s = 0
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", s[i:], re.S)[1:]:
        cells = [re.sub(r"<[^>]+>", "", c).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        if len(cells) < 12:
            continue
        typ, val = cells[6], cells[11].replace("$", "").replace(",", "").replace("+", "")
        try:
            val = abs(float(val))
        except ValueError:
            continue
        if typ.startswith("P"):
            buy += val; buyers.add(cells[4])
        elif typ.startswith("S"):
            sell += val; n_s += 1
    if not buy and not sell:
        return None
    def m(x): return f"{x / 1e6:.1f} mln $".replace(".", ",")
    if buy > 0:
        d = 1 if len(buyers) >= 2 or buy > 1e6 else 0.5
        txt = (f"Osoby z zarządu/rady KUPIŁY akcje za {m(buy)} w ostatnich 90 dniach ({len(buyers)} os.). "
               "Zakupy za własne pieniądze to zwykle dobry znak – znają firmę najlepiej.")
    else:
        d = -0.5 if sell > 50e6 else 0
        txt = (f"Osoby z zarządu/rady tylko sprzedawały akcje ({n_s} transakcji, {m(sell)}) w ostatnich 90 dniach. "
               "Sprzedaże bywają rutynowe (podatki, wcześniej zaplanowane), więc to słaby sygnał.")
    return {"buy": buy, "sell": sell, "buyers": len(buyers), "dir": d, "text": txt}


def superinvestors(sym, price, get):
    """Znani inwestorzy (fundusze typu Berkshire, Tiger Global, Appaloosa…) – dane z raportów 13F zebrane przez Dataroma.
    Raporty są kwartalne i spóźnione ok. 45 dni, więc pokazują kierunek, a nie bieżące decyzje."""
    s = get(f"https://www.dataroma.com/m/stock.php?sym={urllib.parse.quote(sym)}", ttl=86400).decode("utf-8", "ignore")
    t = re.sub(r"<script.*?</script>|<style.*?</style>", "", s, flags=re.S)
    cnt = re.search(r"Ownership count:\s*</td>\s*<td[^>]*>\s*(\d+)", t) or re.search(r"Ownership count:.*?(\d+)", re.sub(r"<[^>]+>", " ", t), re.S)
    hold = re.search(r"Hold Price \*.*?\$([\d,.]+)", re.sub(r"<[^>]+>", " ", t), re.S)
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", t, re.S):
        cells = [re.sub(r"<[^>]+>", "", c).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        if len(cells) >= 5 and " - " in cells[1] or (len(cells) >= 5 and re.search(r"(Management|Capital|Funds|Partners|Advisors|Hathaway)", cells[1] or "")):
            act = cells[3]
            if re.match(r"^(Add|Reduce|Buy|Sell)", act) or act == "":
                rows.append({"who": cells[1], "pct": cells[2], "act": act})
    if not cnt and not rows:
        return None
    adds = [r for r in rows if r["act"].startswith(("Add", "Buy"))]
    reds = [r for r in rows if r["act"].startswith(("Reduce", "Sell"))]
    new = [r for r in rows if r["act"].startswith("Buy")]
    hp = float(hold.group(1).replace(",", "")) if hold else None
    n = int(cnt.group(1)) if cnt else len(rows)
    d = 0.5 if len(adds) > len(reds) * 1.5 and adds else -0.5 if len(reds) > len(adds) * 2 and reds else 0
    famous = [r for r in rows if re.search(r"Buffett|Ackman|Tepper|Burry|Icahn|Klarman|Li Lu|Coleman|Druckenmiller|Pabrai|Akre|Russo|Smith|Greenblatt|Loeb", r["who"])]
    txt = (f"{n} znanych inwestorów ma te akcje w portfelu. W ostatnim kwartale {len(adds)} dokupiło"
           + (f" (w tym {len(new)} nowych)" if new else "") + f", {len(reds)} sprzedało część.")
    if hp:
        txt += f" Ich średnia cena zakupu: {hp:,.2f} USD ({'+' if price >= hp else '−'}{abs(price / hp - 1) * 100:.0f}% do dziś).".replace(",", " ").replace(".", ",", 1)
    txt += " Dane kwartalne (13F), opóźnione ok. 1,5 miesiąca."
    def pl(act):
        m_ = re.match(r"(Add|Reduce|Buy|Sell)\s*([\d.]*)%?", act or "")
        if not m_:
            return "trzyma"
        word = {"Add": "dokupił", "Reduce": "sprzedał część", "Buy": "kupił (nowa pozycja)", "Sell": "sprzedał całość"}[m_.group(1)]
        return word + (f" ({m_.group(2).replace('.', ',')}%)" if m_.group(2) and m_.group(1) in ("Add", "Reduce") else "")
    return {"n": n, "adds": len(adds), "reduces": len(reds), "new": len(new), "hold": hp, "dir": d,
            "famous": [f"{r['who'].split(' - ')[0]}: {pl(r['act'])}" for r in famous][:5],
            "top": [f"{r['who'].split(' - ')[0]}: {pl(r['act'])}" for r in rows[:5]], "text": txt}


def reddit_buzz(get_json):
    """Najczęściej komentowane spółki na Reddicie (ApeWisdom). Duży szum = duże emocje i zmienność, nie gwarancja wzrostu."""
    out = {}
    for page in (1, 2):
        try:
            for r in get_json(f"https://apewisdom.io/api/v1.0/filter/all-stocks/page/{page}", ttl=3600)["results"]:
                m0, m1 = r.get("mentions_24h_ago") or 0, r.get("mentions") or 0
                out[r["ticker"]] = {"rank": r["rank"], "mentions": m1, "prev": m0, "rank_prev": r.get("rank_24h_ago"),
                                    "change": (m1 / m0 - 1) if m0 else None, "name": r.get("name")}
        except Exception as e:
            print("Reddit pominięty:", e)
            break
    return out


def buzz_text(b):
    ch = b.get("change")
    txt = f"Reddit: {b['mentions']} wzmianek w dobę (miejsce {b['rank']} wśród spółek)"
    if ch is not None and ch > 0.5 and b["mentions"] >= 20:
        txt += f", o {ch * 100:.0f}% więcej niż dzień wcześniej – rośnie zainteresowanie drobnych inwestorów. Taki szum często oznacza duże wahania w obie strony."
    elif ch is not None and ch < -0.4:
        txt += " – zainteresowanie słabnie."
    else:
        txt += "."
    return txt

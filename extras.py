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

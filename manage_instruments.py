"""Dodaje lub usuwa instrument z instruments.json na podstawie tytułu zgłoszenia (issue) na GitHubie.

Tytuł: "Dodaj: Sony" albo "Usuń: SONY". Wynik (tekst po polsku) trafia do pliku result.md,
a do pliku changed zapisujemy "1", jeśli lista się zmieniła.
Uruchamiane przez .github/workflows/instruments.yml.
"""
import json, os, re, sys, urllib.parse
from fetch_data import get_json, history, group_of, ref_for

sys.stdout.reconfigure(encoding="utf-8")

LEV = {"Akcje GPW": 5, "Akcje USA": 5, "Akcje – świat": 5, "ETF": 5, "Krypto": 2, "Indeksy": 20, "Surowce": 10}
SPREAD = {"Akcje GPW": 0.2, "Akcje USA": 0.1, "Akcje – świat": 0.15, "ETF": 0.1, "Krypto": 0.5, "Indeksy": 0.03,
          "Surowce": 0.05}
UNIT = {"Akcje GPW": "akcji", "Akcje USA": "akcji", "Akcje – świat": "akcji", "ETF": "jedn.", "Krypto": "szt.",
        "Indeksy": "jedn.", "Surowce": "jedn."}
TYPES = ("EQUITY", "ETF", "CRYPTOCURRENCY", "FUTURE", "INDEX")


def search(q):
    """Szuka instrumentu w wyszukiwarce Yahoo Finance; preferuje dokładny symbol i giełdy główne."""
    res = get_json("https://query2.finance.yahoo.com/v1/finance/search?"
                   + urllib.parse.urlencode({"q": q, "quotesCount": 10, "newsCount": 0}))
    quotes = [x for x in res.get("quotes", []) if x.get("quoteType") in TYPES and x.get("symbol")]
    if not quotes:
        return None
    exact = [x for x in quotes if x["symbol"].upper() == q.upper()]
    if exact:
        return exact[0]
    def rank(x):
        sym = x["symbol"]
        main = "." not in sym or sym.endswith(".WA")  # USA i GPW najpierw, potem inne giełdy
        return (0 if main else 1, -x.get("score", 0))
    return sorted(quotes, key=rank)[0]


def clean_name(name):
    name = re.sub(r"\s+(S\.A\.|SA|Inc\.?|Corporation|Corp\.?|plc|Ltd\.?|AG|N\.V\.|SE|Holdings?)$", "", name.strip(), flags=re.I)
    return name.strip(" ,")


def add(q, items):
    hit = search(q)
    if not hit:
        return f"Nie znalazłem instrumentu „{q}”. Spróbuj wpisać dokładny symbol (np. SONY, KGH.WA, ETH-USD)."
    sym = hit["symbol"]
    if any(i["symbol"].upper() == sym.upper() for i in items):
        return f"{sym} już jest na liście."
    H = history(sym)
    if len(H["c"]) < 260:
        return f"{sym} ma za krótką historię notowań (potrzeba co najmniej roku), więc analiza nie byłaby wiarygodna."
    group = group_of(sym, hit.get("quoteType", ""))
    name = clean_name(hit.get("longname") or hit.get("shortname") or sym)
    if group == "Krypto":
        name = re.sub(r"\s+USD$", "", name)
    first = name.split()[0].lower()
    entry = {"name": name, "symbol": sym, "group": group, "ref": ref_for(sym, group), "macro": ["USD"],
             "lev": LEV.get(group, 5), "spread": SPREAD.get(group, 0.1), "unit": UNIT.get(group, "szt."),
             "news_en": name + (" stock" if group.startswith("Akcje") else " price"), "news_pl": name,
             "keywords": sorted({name.lower(), first} if len(first) > 3 else {name.lower()}), "added": True}
    if group == "Akcje USA" and hit.get("quoteType") == "EQUITY":
        entry["earnings"] = True
    if group == "Akcje GPW":
        entry["macro"] = ["EUR"]
    items.append(entry)
    return (f"Dodano: **{name}** ({sym}, {hit.get('exchDisp', '')}, grupa „{group}”). "
            "Pełna analiza pojawi się na stronie za ok. 3–5 minut (odśwież stronę).")


def remove(q, items):
    ql = q.lower()
    hit = next((i for i in items if i["symbol"].lower() == ql), None) or \
        next((i for i in items if i["name"].lower() == ql), None)
    if not hit:
        return f"Na liście nie ma „{q}”. Podaj symbol dokładnie tak, jak na stronie (np. TPE.WA)."
    items.remove(hit)
    return f"Usunięto: **{hit['name']}** ({hit['symbol']})."


def save(items):
    with open("instruments.json", "w", encoding="utf-8", newline="\n") as f:
        f.write("[\n" + ",\n".join(" " + json.dumps(i, ensure_ascii=False, separators=(",", ":")) for i in items) + "\n]\n")


if __name__ == "__main__":
    title = os.environ.get("TITLE", "").strip()
    m = re.match(r"^(dodaj|usuń|usun)\s*:\s*(.{1,60})$", title, re.I)
    items = json.load(open("instruments.json", encoding="utf-8"))
    before = len(items)
    if not m:
        msg = "Nie rozumiem zgłoszenia. Tytuł powinien wyglądać tak: „Dodaj: Sony” albo „Usuń: TPE.WA”."
    elif m.group(1).lower() == "dodaj":
        try:
            msg = add(m.group(2).strip(), items)
        except Exception as e:
            msg = f"Nie udało się dodać „{m.group(2).strip()}”: {e}"
    else:
        msg = remove(m.group(2).strip(), items)
    changed = len(items) != before
    if changed:
        save(items)
    open("result.md", "w", encoding="utf-8").write(msg + "\n\n_Automatyczna odpowiedź Centrum rynku._\n")
    open("changed", "w").write("1" if changed else "0")
    print(msg)

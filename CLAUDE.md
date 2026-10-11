# CLAUDE.md: "Centrum rynku" (market info dashboard)

## About the user
- Polish speaker, **no technical or programming experience**. Reply in the language the user writes in (Polish or English).
- Explain things in plain, simple words. Before any larger change, say in one or two sentences what you are going to do. Avoid jargon; if you must use a term, explain it briefly.
- The user is a **day trader** interested in: Polish stocks (GPW), US stocks, commodities (gold, silver, oil), indices and Bitcoin.
- Budget for data: **0 PLN, free sources only**.

## What this project is
A personal website that collects market data and news automatically and shows, for each instrument, several independent probability bars plus one overall bar answering: "Is it worth entering now?"

## How it works (no server, all free)
1. `fetch_data.py` runs every 15 minutes on weekdays via GitHub Actions (`.github/workflows/update.yml`).
2. It downloads 5 years of daily prices from the unofficial Yahoo Finance chart endpoint (instruments + reference markets: WIG20 via ETF `ETFBW20TR.WA`, `^GSPC`, `^IXIC`, `^VIX`, `PLN=X`, `DX-Y.NYB`), news from Google News RSS (per instrument, English + Polish, last 14 days) and Bankier.pl RSS (`wiadomosci`, `gielda`, `firma`, `espi`, `waluty`; `surowce.xml` no longer exists).
3. Yahoo sometimes "freezes" daily bars (same close, zero volume, seen on GPW stocks). The script detects this and rebuilds the last days from 60-minute bars.
4. It analyses everything itself (no copied opinions) and writes `data.json`, which the workflow commits back to the repo.
5. `index.html` (static page on GitHub Pages: https://alexanderdimer-ops.github.io/centrum-rynku/) reads `data.json` and renders the list and a detail view per instrument (`#i=SYMBOL`).
6. The list of instruments lives in `instruments.json` (fields: `name`, `symbol` as on Yahoo Finance, `group`, `ref` reference market symbol, `news_en` / `news_pl` Google News queries, `keywords` for matching Bankier headlines).

## Probability bars (each = estimated chance the next session closes UP)
1. **Historia**: share of up-days following a day with the same direction as the last one (last ~500 sessions).
2. **Sezonowość**: share of up-days on the weekday of the next session.
3. **Trend i momentum**: heuristic from RSI(14) and price vs SMA20/SMA50.
4. **Model zmienności**: normal-distribution estimate from 20-day mean return vs 60-day volatility, shrunk toward 50%.
5. **Otoczenie rynku**: 60-day correlation with the reference market times that market's trend (max ±12 pp).
6. **Nastrój newsów**: keyword-based sentiment (PL + EN dictionaries) of last-7-day headlines (no value if there are none). Not backtestable.
- **Backtest**: methods 1-5 are re-run day by day over the last ~500 sessions; hit rate over the last 250 is shown per method. Weights = clamp(1 + 8*(acc - 0.5), 0.3, 1.8); news weight 0.8. The overall bar's own hit rate is measured with weights from the earlier half only (no look-ahead). Hit rates are close to 50%: say so honestly.
- **Overall bar** = weighted average of available methods. Verdict: >= 58 favorable, 46-58 neutral, < 46 unfavorable.
- All values are clamped to 5-95%. These are statistical estimates, not investment advice. Keep the disclaimer in the page footer.

## Generated analysis (all computed in `fetch_data.py`, Polish text)
- Plain-language summary (trend vs SMA50/200, performance, RSI, volatility regime, 52-week range, news tone, reference market, backtest honesty line).
- Plan "Czy warto wejść teraz?": checklist of up-conditions with concrete price levels (resistance/support = 20-session high/low, SMA20/50), concrete signals to wait for, warning level, and for favorable verdicts stop loss (2×ATR) and target (3×ATR).
- Forecast: volatility-based 68% price ranges (next session, week, month) and historical analogs (same trend state + RSI bucket over 5 years: share up, median, quartiles).
- News per instrument split into last 7 days / 7-14 days ago, with counts, tone and frequent topics.

## UI requirements (set by the user)
- Easy, intuitive, works on phone and desktop. Polish interface text. Dark black/grey theme.
- Colors: rises and probabilities above 50% green, falls and below 50% red; each method bar has its own color.
- Explain everything step by step for a total beginner (glossary and "how to use" guide on the page).
- Detail view: chart with selectable range (week, month, 3M, 6M, year, 5 years), boxes "Teraz", "Przyszłość – prognoza", methods, news.
- Heart button per instrument to add or remove favorites; tabs "Ulubione" / "Wszystkie"; search box. Favorites are stored in the browser (`localStorage`).
- Default favorites: Tauron (TPE.WA), CD Projekt (CDR.WA), Bitcoin (BTC-USD), Silver CFD (SI=F), Gold CFD (GC=F), Apple (AAPL).
- Gold and silver "CFD" are shown through futures (GC=F, SI=F), which track CFD prices closely but are not the broker's quotes.

## Known limitations and open items
- Live data verified on 2026-10-11. Yahoo is unofficial and may change or block; Stooq is behind a bot check (do not use).
- Free data may be delayed. The page is an information and context tool, not for scalping.
- Weekends: the workflow runs Monday to Friday only.

## Planned next steps (ask the user before starting)
1. ~~Verify live data~~ (done). ~~Basic backtest and weighting~~ (done).
2. Improve accuracy: better methods, calibration of probabilities.
3. Add more methods: analyst forecasts, prediction markets (Polymarket/Kalshi), event calendar (macro data, company earnings).
4. Make adding new instruments easier (the user currently edits `instruments.json` on GitHub).
5. Optional alerts when the overall probability crosses a threshold.

## Working rules
- Keep everything free. Do not add paid APIs or require API keys without asking.
- Keep the page simple: no build tools, plain HTML/CSS/JS, plain Python standard library where possible.
- After any change: run `python fetch_data.py` and check `data.json`; open `index.html` to confirm it renders. Tell the user what changed and whether it worked.
- Never remove the "not investment advice" disclaimer.

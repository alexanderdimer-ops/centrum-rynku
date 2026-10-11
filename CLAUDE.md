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
2. It downloads 2 years of daily prices from the unofficial Yahoo Finance chart endpoint and Polish news from Bankier.pl RSS feeds.
3. It computes the probabilities and writes everything to `data.json`, which the workflow commits back to the repo.
4. `index.html` (static page on GitHub Pages) reads `data.json` and renders the cards.
5. The list of instruments lives in `instruments.json` (fields: `name`, `symbol` as on Yahoo Finance, `group`, `keywords` for matching Polish news).

## Probability bars (each = estimated chance the next session closes UP)
1. **Historia**: share of up-days following a day with the same direction as the last one.
2. **Sezonowość**: share of up-days on the same weekday.
3. **Trend i momentum**: heuristic from RSI(14) and price vs SMA20/SMA50.
4. **Model zmienności**: normal-distribution estimate from 20-day mean return vs 60-day volatility, shrunk toward 50%.
5. **Nastrój newsów**: keyword-based sentiment of Polish headlines (no value if there are no news for the instrument).
- **Overall bar** = average of available methods. Verdict: >= 58 favorable, 46-58 neutral, < 46 unfavorable.
- All values are clamped to 5-95%. These are statistical estimates, not investment advice. Keep the disclaimer in the page footer.

## UI requirements (set by the user)
- Easy, intuitive, works on phone and desktop. Polish interface text.
- Heart button per instrument to add or remove favorites; tabs "Ulubione" / "Wszystkie"; search box. Favorites are stored in the browser (`localStorage`).
- Default favorites: Tauron (TPE.WA), CD Projekt (CDR.WA), Bitcoin (BTC-USD), Silver CFD (SI=F), Gold CFD (GC=F), Apple (AAPL).
- Gold and silver "CFD" are shown through futures (GC=F, SI=F), which track CFD prices closely but are not the broker's quotes.

## Known limitations and open items
- The code has **not yet been tested with live data**: the first task is to run `fetch_data.py` and fix anything that breaks (Yahoo may block or change the endpoint; RSS feed URLs on Bankier may need verifying).
- Free data may be delayed. The page is an information and context tool, not for scalping.
- Weekends: the workflow runs Monday to Friday only.

## Planned next steps (ask the user before starting)
1. Verify live data and fix errors.
2. Backtest: measure how accurate each bar has been historically and weight the overall bar accordingly.
3. Add more methods: analyst forecasts, prediction markets (Polymarket/Kalshi), event calendar (macro data, company earnings).
4. Make adding new instruments easier (the user currently edits `instruments.json` on GitHub).
5. Optional alerts when the overall probability crosses a threshold.

## Working rules
- Keep everything free. Do not add paid APIs or require API keys without asking.
- Keep the page simple: no build tools, plain HTML/CSS/JS, plain Python standard library where possible.
- After any change: run `python fetch_data.py` and check `data.json`; open `index.html` to confirm it renders. Tell the user what changed and whether it worked.
- Never remove the "not investment advice" disclaimer.

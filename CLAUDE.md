# CLAUDE.md: "Centrum rynku" (market info dashboard)

## About the user
- Polish speaker, **no technical or programming experience**. **Correspond in Polish** (user's request on 2026-10-11).
- The user's Windows and GitHub interface are **in English**: name programs, menus and buttons in English exactly as on screen (e.g. "Credential Manager", "Settings → Pages", "Run workflow"), explanations in Polish.
- The user may type fast without Polish characters and with typos; read for intent.
- Explain things in plain, simple words. Before any larger change, say in one or two sentences what you are going to do. Avoid jargon; if you must use a term, explain it briefly.
- The user is a **day trader** interested in: Polish stocks (GPW), US stocks, commodities (gold, silver, oil), indices and Bitcoin.
- Budget for data: **0 PLN, free sources only**.

## What this project is
A personal website that collects market data and news automatically and shows, for each instrument, several independent probability bars plus one overall bar answering: "Is it worth entering now?"

## How it works (no server, all free)
1. `fetch_data.py` runs via GitHub Actions (`.github/workflows/update.yml`): every 15 minutes Mon-Fri, every 2 hours on weekends (Bitcoin).
2. Data sources (no API keys):
   - Prices: Yahoo Finance chart endpoint, 5 years daily + last session in 5-minute bars ("Dziś" chart). Reference markets: WIG20 via ETF `ETFBW20TR.WA`, `^GSPC`, `^IXIC`, `^VIX`, `PLN=X`, `EURPLN=X`, `DX-Y.NYB`.
   - Calendar: ForexFactory weekly JSON `nfs.faireconomy.media/ff_calendar_thisweek.json` (macro; rate-limited with HTTP 429, so fetched at most once per hour, otherwise reused from previous `data.json`), Nasdaq `api.nasdaq.com/api/analyst/<SYM>/earnings-date` (US earnings, Zacks consensus), Bankier per-company page `bankier.pl/gielda/notowania/akcje/<CODE>/kalendarium` (GPW results, dividends, AGMs; parsed from HTML).
   - News: Google News RSS per instrument (EN + PL, 14 days) and Bankier RSS (`wiadomosci`, `gielda`, `firma`, `espi`, `waluty`).
   - Not usable: Stooq and nbp.pl (bot protection, do not bypass), Yahoo quoteSummary (needs crumb), Bankier `surowce.xml` (gone). No free automatic source for Polish macro (RPP, GUS) yet.
3. Yahoo sometimes "freezes" daily bars (same close, zero volume, seen on GPW stocks). The script detects this and rebuilds the last days from 60-minute bars.
4. It analyses everything itself and writes `data.json` (items, pulse, fx, calendar), which the workflow commits back.
5. The page (GitHub Pages: https://alexanderdimer-ops.github.io/centrum-rynku/) is `index.html` + `style.css` + `app.js` (bump the `?v=N` query in `index.html` after changing CSS/JS so browsers don't use the old cached file).
6. `instruments.json` fields: `name`, `symbol` (Yahoo), `group`, `ref` (reference market), `bankier` (Bankier code, GPW only), `earnings` (true for US stocks), `macro` (currencies whose macro events affect it), `oil` (oil-inventory events), `lev` (ESMA retail max leverage), `spread` (% typical), `lot` (units per CFD lot), `unit`, `news_en`/`news_pl` (Google News queries, may use `-word` exclusions), `keywords` (Bankier matching).
7. Adding/removing instruments (no coding, no token): the page opens a pre-filled GitHub issue "Dodaj: <name or symbol>" / "Usuń: <SYMBOL>"; the user clicks "Create". `.github/workflows/instruments.yml` (only for issues by the repo owner) runs `manage_instruments.py` (Yahoo search API `query2.finance.yahoo.com/v1/finance/search`, needs ≥ 260 daily bars, derives group/ref/lev/spread/news queries, marks `"added": true`), reruns `fetch_data.py`, commits, comments the result in Polish and closes the issue. Both workflows share `concurrency: dane` and retry pushes with `git pull --rebase -X theirs`.
8. Market scanner (`scan()`, hourly, cached in `data.json`): `UNIVERSE` (~60 large GPW/US stocks, commodities, crypto, indices) + Yahoo trending/day_gainers/most_actives (market cap ≥ 2 bn, price ≥ 5, liquidity filter); 2 years daily; potential score; top 10 get Google News headlines (interpreted) and US earnings dates. World headlines (`world_news()`, hourly): tier ≤ 1 sources only, last 2 days, interpreted, matched to instruments.
9. Optional phone alerts: if GitHub secret `NTFY_TOPIC` exists, `notify()` posts to ntfy.sh when a decision changes or price crosses resistance/support (compares with previous `data.json`). Not set up yet.

## Probability bars (each = estimated chance the next session closes UP)
1. **Historia**: share of up-days following a day with the same direction as the last one (last ~500 sessions).
2. **Sezonowość**: share of up-days on the weekday of the next session.
3. **Trend i momentum**: heuristic from RSI(14) and price vs SMA20/SMA50.
4. **Model zmienności**: normal-distribution estimate from 20-day mean return vs 60-day volatility, shrunk toward 50%.
5. **Otoczenie rynku**: 60-day correlation with the reference market times that market's trend (max ±12 pp).
6. **Nastrój newsów**: keyword sentiment (PL + EN, phrase rules like "record low") of last-7-day headlines, weighted by source tier (official 1.3, tier1 1.0, tier2 0.6, other 0.3). Not backtestable, weight 0.8.
- **Backtest**: methods 1-5 re-run day by day over ~500 sessions; hit rate over the last 250 shown per method; weights = clamp(1 + 8*(acc - 0.5), 0.3, 1.8), computed out-of-sample for the overall test.
- **Calibration** (shown as "Szansa wzrostu jutro"): p = base up-rate (last 500 sessions) + k*(raw - 50), where k = out-of-sample regression slope of outcome on raw score, clamped 0..1 (often 0, so p is close to the base rate). If VIX > 25 the deviation from 50 is shrunk by 0.7. Clamp 5-95.
- **Chance within ~4 hours** (`hourly_chance`): 6 months of 60-minute bars; state = (last hour up?, above hourly SMA20?, RSI bucket); share of times price was higher 4 bars later, shrunk toward the base rate; out-of-sample accuracy on the last 30% shown.
- **Potential score 0-100** (`potential()`, used in "Teraz warto" and the Prognoza tab): base 42; trend vs SMA50/SMA20, breakout/near resistance, RSI zone, volume surge, strength vs reference market (1M), historical setup edge on that instrument, news tone, candle patterns of the last 2 days, hourly chance; penalties for earnings within 3 days, risk level 3/4, and chasing (today's move > 3× typical). "Teraz warto" shows score ≥ 70, risk ≤ 3, not "Nie wchodź", top 6; risk-4 ones counted but hidden.
- **Candle patterns** (`patterns_at`, `candle_patterns`): hammer, inverted hammer, hanging man, shooting star, engulfing, harami, piercing, dark cloud, morning/evening star, three soldiers/crows, marubozu, doji (trend context = close vs SMA10). Stats per instrument over 5 years: share up after 3 sessions vs base. Explanations for beginners live in `app.js` (`PAT`).
- **News interpretation** (`interpret`, `NEWS_RULES`): market-specific rules (stocks / metals / oil / crypto: e.g. strong dollar → gold down, OPEC cuts → oil up, yields rising → stocks/gold down, ETF outflows → crypto down) with Polish "why"; fallback = keyword tone. Calendar events carry a "Co to oznacza dla ceny" hint (`MACRO_HINT`, `EVENT_HINT`).
- **Changes / alerts** (`detect_changes`): decision change, breakout above resistance, drop below support, unusual move (> 2.5× typical); kept 3 days in `data.json["changes"]`; shown in "Teraz warto", as a badge on the nav, as toasts when the open page auto-refreshes (every 5 min) and optionally as browser notifications; ntfy uses the same new changes.
- **Weekly chance**: historical analogs (same SMA50 side + RSI bucket, 5 years), shrunk toward the base weekly up-rate.
- **Verdict / decision** (setup quality, not a probability): checklist of 6 conditions (above SMA50, above SMA20, RSI 50-70, close above 20-session high, reference market favorable, calibrated p > 50). good = all but one met and p >= 50; bad = <= 1 met or p < 45; else neutral. Decision: "Możesz rozważyć wejście" / "Poczekaj…" (also when earnings within 3 days, high-impact macro within 1 day, or risk level 4) / "Nie wchodź teraz". Adds a warning when, on that instrument, such setups historically did no better than average (`setup_history`).
- These are statistical estimates, not investment advice. Keep the disclaimer in the page footer.

## Generated analysis (all computed in `fetch_data.py`, Polish text)
- Plain-language summary (trend, performance, RSI, volatility regime, 52-week range, risk, news, reference market, setup history, backtest honesty line).
- Plan with concrete price levels (resistance/support = 20-session high/low, SMA20/50), signals to wait for, warning level; for favorable: stop 2×ATR, target 3×ATR.
- Risk profile: annualized volatility level 1-4 (<15%, <35%, <60%, more), +1 for imminent events, +1 if VIX > 25; worst day, max drawdown, 5% daily VaR, overnight gaps.
- Forecast: 68% price ranges (next session, week, month), analogs, setup history.
- News per instrument: last 7 days / 7-14 days ago, sorted credible-first, with counts, tone, topics and source tier tags.

## UI requirements (set by the user)
- Clean, readable, intuitive, not cluttered; phone and desktop. Polish interface text. Dark black/grey theme.
- Colors: rises and probabilities above 50% green, falls and below 50% red; each method bar has its own color.
- Explain everything step by step for a total beginner.
- Main navigation (bottom bar on phones): **Teraz warto** (changes, best current opportunities from the list and the whole market with reasons, risk, sample plan, interpreted news; "Na co uważać"; world headlines), **Rynki** (market status GPW/USA/commodities/crypto, pulse, favorites/all, cards with decision + risk + upcoming event), **Kalendarz** (grouped by day, filters favorites/all and all/important/macro/companies, instrument chips), **Dziennik** (paper vs real trades in localStorage, live P/L in PLN and R, stop/target hit hints, 3% daily loss stop, export/import JSON), **Poradnik** (decision steps, safety rules, source credibility tiers, alerts info, limitations, glossary).
- Rynki has "Dodaj dowolny instrument" (opens the GitHub issue); Decyzja tab ends with "Usuń z listy".
- Instrument view tabs (`#i=SYMBOL/tab`): Decyzja (chances: ~4 h, tomorrow, week; risk), Wykres (Dziś/1T/1M/3M/6M/Rok/5 lat, line or candles; candles show pattern markers, click a candle for an explanation; list of patterns from the last 20 sessions; candle-reading lesson), Kalkulator ryzyka, Prognoza, Newsy i wydarzenia.
- Position calculator: capital and risk % (saved), CFD vs no leverage, long/short, entry/stop/target (suggested 2×/3×ATR), leverage (ESMA default), spread, commission, overnight cost, days; outputs units/lots, value, margin, loss/gain in PLN (USD/EUR converted), R:R, break-even win rate, driftless chance target-before-stop, expected value after costs, gap risk, 10-loss streak, broker minimum (0.01 lot) check, events, verdict; save to journal.
- Heart favorites (localStorage). Default favorites: Tauron (TPE.WA), CD Projekt (CDR.WA), Bitcoin (BTC-USD), Silver CFD (SI=F), Gold CFD (GC=F), Apple (AAPL).
- Gold, silver and oil "CFD" are shown through futures (GC=F, SI=F, BZ=F), which track CFD prices closely but are not the broker's quotes.

## Setup and workflow (state on 2026-10-11)
- Local folder `C:\Users\nachu\Desktop\Claude` is a git clone of https://github.com/alexanderdimer-ops/centrum-rynku (branch `main`). Git identity in local config: alexanderdimer-ops.
- GitHub sign-in is stored by Git Credential Manager. If `git push` from the Bash tool fails with an auth error, run `git push origin main` in a terminal tab (run_in_terminal) so the browser sign-in can appear; the user signs in themselves (never enter credentials).
- The bot commits `data.json` every 15 minutes on weekdays: always `git pull --rebase origin main` before committing; on a `data.json` conflict just regenerate it with `python fetch_data.py`.
- GitHub Pages is enabled (Deploy from branch `main`, `/ (root)`); the workflow "Aktualizacja danych" is enabled and was run successfully by hand.
- Local preview: `.claude/launch.json` config "strona" (`python -m http.server 8765`); `.claude/` is gitignored.
- On Windows run Python with `PYTHONIOENCODING=utf-8` when printing Polish text from ad-hoc scripts (`fetch_data.py` already sets UTF-8 itself).
- Method bar colors (validated for the dark background with the dataviz palette validator): Historia #3987e5, Sezonowość #d95926, Trend #9085e9, Zmienność #c98500, Newsy #d55181, Otoczenie #1d9bb0. Up #22c55e, down #ef4444, neutral verdict #eab308.

## Known limitations and open items
- Yahoo is unofficial and may change or block. Free data may be delayed ~15 min; not for scalping.
- Market hours ignore holidays. Polish macro calendar missing. English headlines not translated. Summaries are rule-based, not AI.
- Google News queries can pull noise (e.g. "Tauron Liga" sports); refine `news_pl`/`news_en` with `-word` exclusions.
- Backtest hit rates are about 47-57% and calibration k is often 0: the page is a risk/decision-discipline tool, not a predictor. Keep saying this honestly.

## Planned next steps (ask the user before starting)
Done on 2026-10-12: position/risk calculator, event calendar, market hours, CFD cost/leverage info, trade journal + paper trading, intraday chart, source credibility tiers, calibration, weekly chance, setup history, weekend updates, optional ntfy alerts (code ready).
Done on 2026-10-12 (second round): "Teraz warto" tab with market scanner, candle charts with pattern explanations, news impact notes, ~4 h chance, add/remove any instrument via GitHub issues, auto-refresh with change alerts.
Open ideas:
- Set up phone alerts (user installs the ntfy app, adds `NTFY_TOPIC` secret in GitHub → Settings → Secrets and variables → Actions).
- Polish macro calendar (RPP decisions, GUS inflation) from a free source; holiday calendars for market hours.
- Better prediction: longer walk-forward tests, multi-day horizons, analyst consensus/target prices, COT reports for commodities, options-implied volatility, seasonality by month.
- Make adding new instruments easier (the user currently edits `instruments.json` on GitHub).

## Working rules
- Keep everything free. Do not add paid APIs or require API keys without asking.
- Keep the page simple: no build tools, plain HTML/CSS/JS, plain Python standard library where possible.
- After any change: run `python fetch_data.py` and check `data.json`; open `index.html` to confirm it renders. Tell the user what changed and whether it worked.
- Never remove the "not investment advice" disclaimer.

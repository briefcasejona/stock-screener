# Step 2: Playbook and ASML worked example

The playbook itself is a Claude Doc: "Stock-Picking Playbook" (https://claude.ai/code/artifact/3017388d-3384-4204-ba59-1858b8dfb525). This folder holds the code and data behind its numbers.

- `code/valuation.py`: two-stage DCF, reverse DCF, CAGR. Tests: `python3 -I code/test_valuation.py` (8 pass).
- `code/asml_example.py`: the ASML worked example (quality filters, GARP, normalised FCF, reverse DCF, scenarios, P/E check). Re-run with a new price after refreshing `raw/ASML.AS_daily.csv`. Writes `output/asml_example.json`.
- `sources/`: ASML Q3 2026 statements and press release (PDF + text). The quarterly figures are parsed from the text, and the parser checks them against the nine-month totals.
- `raw/ASML.AS_daily.csv`: Yahoo prices (unadjusted close, EUR). `raw/peer_pe_yahoo.json`: peers' trailing P/E from Yahoo, not checked against filings.
- Annual figures come from `../data-check/` (step 1).

Snapshot on 19 Oct 2026: price €1,496; normalised FCF €29.43/share; implied growth 17.8%; bear €527 / base €978 / bull €2,147; decision: wait.

## Dashboard
"Stock Candidates" (https://claude.ai/artifact/LBubds4AMFczB3SrtjEFCY), a Dashboard artifact. Data files: `dashboard/*.json`, built by `python3 -I code/build_dashboard_data.py` from `output/asml_example.json` and `journal/journal.json`; the page source is `dashboard/index.html`. To refresh: rerun asml_example.py and build_dashboard_data.py, upload each JSON as an asset, update each `datasets/<id>` url and `updated`. The what-if sliders use the same DCF in JavaScript (checked against valuation.py: 527 / 978 / 2,147, implied 17.8%).

## Watchlist and one-time analyses (from 19 Oct 2026)
- `code/analyse.py TICKER`: the standard analysis of any screened company, in the same shape as the worked example (10 checks, reverse DCF, bear/base/bull, P/E history). Starting FCF = average FCF/share of the last 3 years (`--normalised` for cyclicals). Unless growth rates are set by hand, a starting rule sets them (base = lower of delivered FCF/share growth and 3-year revenue growth, 2–12%; bear = half; bull = delivered, max 20%) and a price under buy-below reads "Deep dive", not "Buy".
- `code/watchlist.py`: `add TICKER [--once]`, `set TICKER --base 0.09 [--reviewed]`, `watch`, `once`, `remove`, `list`, `check`. State: `journal/watchlist.json`, analyses in `journal/analyses/`, every change appended to `journal/journal.json`. ASML stays the hand-made worked example (one-time) until the user asks to watch it.
- `check` is run every Saturday 07:52 Amsterdam time by a scheduled task in the "Building the stock screener" thread: for each watched company it refreshes the figures and price (`screener/code/refresh_company.py`), notes a new annual report when a new year shows up in the figures, notes new 10-Q/interim reports, and notes a price crossing a buy-below price at any margin. Then `build_dashboard_data.py` and upload the datasets.

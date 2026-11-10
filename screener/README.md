# Screener (step 3)

An idea generator. It runs the playbook's 10 checks (6 quality, 4 GARP) over the S&P 500 and the STOXX Europe 600, without banks, insurers and real estate. Passing all 10 means "worth a deep dive", never "buy".

## Sources
- **US:** SEC EDGAR company facts (10-K), 10+ years.
- **Europe:** SEC filings for the 42 companies that file 20-Fs; ESEF annual reports from filings.xbrl.org for the rest (from FY2020, so 5–7 years). 105 companies have no free machine-readable reports, mostly German and Swiss.
- **Prices and exchange rates:** Yahoo Finance.
- **Second source:** Yahoo statements (last 4 years), used only to flag disagreements and for one rule. Where the filing's debt and Yahoo's (leases excluded) differ by more than 10%, or the filing tags no debt, the larger figure is used and flagged.

## Checks done (19 Oct 2026)
- Second source, US: revenue 97%, profit 96%, cash flow 99%, equity 99% and debt 84% of company-years agree within 2%.
- Against the 10-Ks for the 18 US companies passing all 10: 172 of 180 figures exact. All misses are debt at principal vs. carrying value; now fixed. Results in `output/spotcheck_us.csv`.
- Against the annual reports for 8 European companies: 73 of 80 exact. The misses are debt and short-term investments that companies file under their own names, now covered by the debt rule. Kongsberg's EPS is split-adjusted on purpose, to match today's price. Results in `output/spotcheck_eu.csv`.

## Refresh (run from anywhere; each step reads the previous one's output)
```
S=/mnt/project-files/screener
python3 -I $S/code/fetch_sec.py                  # US company facts (local cache)
python3    $S/code/prices.py us                  # US prices and splits
python3 -I $S/code/extract_sec.py us             # output/figures_us.csv
python3    $S/code/crosscheck_yahoo.py us        # output/crosscheck_us.csv
python3 -I $S/code/screen.py us                  # output/screen_us.csv

python3 -I $S/code/build_universe_eu.py          # raw/universe_eu.csv (Yahoo symbol, LEI, SEC CIK)
python3    $S/code/prices.py eu
python3 -I $S/code/extract_esef.py               # output/figures_eu.csv (SEC + ESEF)
python3    $S/code/fx.py eu                      # raw/fx.json
python3    $S/code/crosscheck_yahoo.py eu
python3 -I $S/code/screen.py eu

python3 -I $S/code/build_screen_data.py          # dashboard/screen.json -> upload to the dashboard as the "screen" dataset
```
Caches of SEC and ESEF downloads live on local disk (`/tmp/claude-0/sec_cache`, `/tmp/claude-0/esef_cache`) and are rebuilt when missing.

## One company at a time
`python3 -I code/refresh_company.py TICKER` downloads that company's figures (SEC company facts or its ESEF filing list), price, splits and second-source statements afresh, replaces its rows, and re-runs crosscheck, screen and build_screen_data (offline, a few seconds). The watchlist's weekly check uses it.

## Paid data, later
`code/eodhd_test.py` runs the one-month EODHD test against the step 1 reference figures when `EODHD_API_KEY` is set as an environment secret. Never paste the key in chat.

## Your own annual reports (`code/user_reports.py`)
For companies without free machine-readable data (most German and Swiss companies), or for longer histories. The user attaches a downloaded report in the project and says which company it is.
- **ESEF package (.zip) or ESEF report (.xhtml/.html):** `python3 -I code/user_reports.py esef <file> --ticker SIE.DE`. The tagged figures are read exactly. On IMCD's 2024 package this matched the filings.xbrl.org figures to the cent for both years.
- **PDF:** `pdf-find <file> <regex>` locates the statement lines, then you write a small map (page, label and optional column index per figure; see `pdf_maps/example_siemens_2025.json`, a worked example on Siemens 2025) and run `pdf <file> --map map.json`. The report is saved only if the balance sheet balances, EPS x shares matches net profit, and the cash flow adds up to the change in cash (each check runs when its figures are in the map). Page references are stored with the figures.
- A company outside the two indexes: add `--name` and `--yahoo`.
- Reports are saved in `user_reports/<ticker>/<year end>__<kind>.json`. `extract_esef.py` merges them (newest report wins) and labels the source "your files". Then rerun prices (for a new company), extract, fx, crosscheck, screen and `build_screen_data.py`.

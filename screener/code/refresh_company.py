"""Bring one company's figures, price and second-source check up to date, for example after a new annual report.

Updates only that company's rows in output/figures_<region>.csv, raw/prices_<region>.csv, raw/splits_<region>.json
and raw/yahoo_statements_<region>.json (fresh downloads: SEC company facts, ESEF filing list, Yahoo), then re-runs
the offline steps for everyone: crosscheck_yahoo.py, screen.py and build_screen_data.py.
Run: python3 -I code/refresh_company.py ADBE
"""
import csv
import gzip
import json
import os
import subprocess
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import crosscheck_yahoo  # noqa: E402
import extract_esef  # noqa: E402
import extract_sec  # noqa: E402
import localdata  # noqa: E402
import net  # noqa: E402

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CODE = os.path.dirname(os.path.abspath(__file__))


def find(ticker):
    """(region, universe row with a yahoo symbol) for a ticker in either universe."""
    for region in ('us', 'eu'):
        rows = localdata.eu_universe() if region == 'eu' else csv.DictReader(open(f'{BASE}/raw/universe_us.csv'))
        for u in rows:
            if u['ticker'] == ticker:
                if region == 'us':
                    u = {**u, 'yahoo': ticker.replace('.', '-'), 'source': 'sec'}
                return region, u
    raise KeyError(f'{ticker} is in neither universe (add it with user_reports.py --name/--yahoo first)')


def quote(symbol):
    """Latest close, its date and currency, and the split history, from Yahoo."""
    import yfinance as yf
    tk = yf.Ticker(symbol)
    h = tk.history(period='1mo', interval='1d', auto_adjust=False).dropna(subset=['Close'])
    if h.empty:
        raise RuntimeError(f'no price for {symbol}')
    splits = [[str(d.date()), float(r)] for d, r in tk.splits.items() if d.year >= 2014]
    return {'price': float(h['Close'].iloc[-1]), 'date': str(h.index[-1].date()), 'currency': tk.fast_info['currency']}, splits


def replace_rows(path, ticker, new_rows, fields=None):
    rows = list(csv.DictReader(open(path)))
    fields = fields or list(rows[0])
    rows = [r for r in rows if r['ticker'] != ticker] + new_rows
    with open(path, 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def refresh(ticker, rerun=True):
    region, u = find(ticker)
    q, splits = quote(u['yahoo'])
    replace_rows(f'{BASE}/raw/prices_{region}.csv', ticker, [{'ticker': ticker, 'yahoo': u['yahoo'], **q}],
                 ['ticker', 'yahoo', 'price', 'currency', 'date'])
    splits_path = f'{BASE}/raw/splits_{region}.json'
    splits_all = json.load(open(splits_path)) if os.path.exists(splits_path) else {}
    splits_all[ticker] = splits
    json.dump(splits_all, open(splits_path, 'w'), indent=0)

    failed = []
    if u['source'] == 'sec':  # fresh company facts, overwriting the cached copy
        os.makedirs(extract_sec.CACHE, exist_ok=True)
        data = net.fetch(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{u['cik']}.json")
        with gzip.open(f"{extract_sec.CACHE}/{u['cik']}.json.gz", 'wb') as fh:
            fh.write(data)
    if region == 'us':
        rows = extract_sec.company_rows(u, splits_all)
    else:
        lists_path = f'{BASE}/raw/esef_filings_eu.json'
        lists = json.load(open(lists_path))
        if u.get('lei'):
            lists[u['lei']] = extract_esef.filing_list(u['lei'])  # fresh list: a new report shows up here
            json.dump(lists, open(lists_path, 'w'))
        rows = extract_esef.company_rows(u, lists, splits_all, failed)
    if not rows:
        raise RuntimeError(f'no figures found for {ticker}')
    replace_rows(f'{BASE}/output/figures_{region}.csv', ticker, rows)

    cache_path = f'{BASE}/raw/yahoo_statements_{region}.json'
    cache = json.load(open(cache_path)) if os.path.exists(cache_path) else {}
    try:
        cache[ticker] = crosscheck_yahoo.fetch(u['yahoo'])
    except Exception as e:  # the second source is optional; the old copy stays
        failed.append(f'second source not refreshed: {e}')
    json.dump(cache, open(cache_path, 'w'))

    if rerun:
        for script in ('crosscheck_yahoo.py', 'screen.py'):
            subprocess.run(localdata.python_cmd(f'{CODE}/{script}', region), check=True, capture_output=True, **localdata.hidden())
        subprocess.run(localdata.python_cmd(f'{CODE}/build_screen_data.py'), check=True, capture_output=True, **localdata.hidden())
    return {'ticker': ticker, 'region': region, 'years': len(rows), 'last_year': int(rows[-1]['fiscal_year']),
            'last_period_end': rows[-1]['period_end'], 'price': q, 'problems': failed}


if __name__ == '__main__':
    print(json.dumps(refresh(sys.argv[1]), indent=1))

"""Latest share prices and split history from Yahoo Finance (prices only: step 1 found Yahoo unfit for company figures).

Input:  raw/universe_<region>.csv (ticker, plus yahoo column for Europe)
Output: raw/prices_<region>.csv (ticker, yahoo, price, currency, date), raw/splits_<region>.json
Run: python3 code/prices.py us
"""
import csv
import json
import os
import sys
import time

import yfinance as yf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import localdata  # noqa: E402
import net  # noqa: E402

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    region = sys.argv[1]
    universe = localdata.eu_universe() if region == 'eu' else list(csv.DictReader(open(f'{BASE}/raw/universe_us.csv', encoding='utf-8', errors='replace')))
    ymap = {u['ticker']: u.get('yahoo') or u['ticker'].replace('.', '-') for u in universe}
    symbols = sorted(set(ymap.values()))
    got = {}
    todo = symbols
    for wait in (0, 30, 90):  # symbols Yahoo did not answer (it throttles big requests) are asked for again, later
        if not todo:
            break
        if wait:
            print(f'  {len(todo)} prices missing: trying those again in {wait} s', flush=True)
            time.sleep(wait)
        hist = net.patient(yf.download, todo, period='1mo', interval='1d', auto_adjust=False, actions=True,
                           group_by='ticker', threads=True, progress=False)
        for y in todo:
            if y in hist.columns.get_level_values(0):
                h = hist[y].dropna(subset=['Close'])
                if not h.empty:
                    got[y] = h
        todo = [y for y in todo if y not in got]
    prices = []
    # the split history from before: kept for a company whose history Yahoo doesn't hand over this time
    old_path = f'{BASE}/raw/splits_{region}.json'
    splits = json.load(open(old_path, encoding='utf-8', errors='replace')) if os.path.exists(old_path) else {}
    no_splits = []
    for t, y in ymap.items():
        if y in got:
            h = got[y]
            prices.append({'ticker': t, 'yahoo': y, 'price': float(h['Close'].iloc[-1]), 'date': str(h.index[-1].date())})
    # split history (whole period) and currency, one call per company
    for i, p in enumerate(prices):
        tk = yf.Ticker(p['yahoo'])
        s = None
        for wait in (0, 5, 20):  # when Yahoo throttles, yfinance can hand back nothing instead of an error
            time.sleep(wait)
            s = net.patient(lambda: tk.splits)
            if s is not None:
                break
        if s is not None:
            splits[p['ticker']] = [[str(d.date()), float(r)] for d, r in s.items() if d.year >= 2014]
        else:
            splits.setdefault(p['ticker'], [])
            no_splits.append(p['ticker'])
        try:
            p['currency'] = tk.fast_info['currency']
        except Exception:
            p['currency'] = ''
        if i % 100 == 0:
            print(i, p['ticker'], flush=True)
    with open(f'{BASE}/raw/prices_{region}.csv', 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=['ticker', 'yahoo', 'price', 'currency', 'date'])
        w.writeheader()
        w.writerows(prices)
    json.dump(splits, open(f'{BASE}/raw/splits_{region}.json', 'w', encoding='utf-8'), indent=0)
    if no_splits:
        print(f'no split history from Yahoo this time (the previous one is kept): {no_splits}')
    print(f'{len(prices)} of {len(universe)} prices; missing {[t for t in ymap if t not in {p["ticker"] for p in prices}]}')


if __name__ == '__main__':
    main()

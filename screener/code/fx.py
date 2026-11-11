"""Exchange rates for companies whose share price and annual report use different currencies
(Shell: price in GBp/EUR, report in USD). Rates are prices, so they come from Yahoo like share prices.

Input:  raw/prices_<region>.csv, output/figures_<region>.csv
Output: raw/fx.json as fx[price currency][report currency] = report-currency units per price-currency unit
        (pence-quoted prices are handled in screen.py: GBp -> GBP first)
Run: python3 -I code/fx.py eu
"""
import csv
import json
import os
import sys

import yfinance as yf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import net  # noqa: E402

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    region = sys.argv[1]
    report_ccy = {}
    for r in csv.DictReader(open(f'{BASE}/output/figures_{region}.csv', encoding='utf-8', errors='replace')):
        report_ccy[r['ticker']] = r['currency']  # rows are in year order: the last one is the latest
    pairs = set()
    for p in csv.DictReader(open(f'{BASE}/raw/prices_{region}.csv', encoding='utf-8', errors='replace')):
        pc = 'GBP' if p['currency'] in ('GBp', 'GBX') else p['currency']
        rc = report_ccy.get(p['ticker'], '')
        if rc and pc and rc != pc and ',' not in rc:
            pairs.add((pc, rc))
    path = f'{BASE}/raw/fx.json'
    fx = json.load(open(path, encoding='utf-8', errors='replace')) if os.path.exists(path) else {}
    for pc, rc in sorted(pairs):
        h = net.patient(yf.download, f'{pc}{rc}=X', period='5d', interval='1d', progress=False, auto_adjust=False)
        rate = float(h['Close'].dropna().iloc[-1].squeeze())
        fx.setdefault(pc, {})[rc] = rate
        fx.setdefault('_date', {})[f'{pc}{rc}'] = str(h['Close'].dropna().index[-1].date())
        print(pc, rc, rate)
    json.dump(fx, open(path, 'w', encoding='utf-8'), indent=1)


if __name__ == '__main__':
    main()

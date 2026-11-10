"""Cross-check the extracted figures against Yahoo Finance's statements (last 4 years).

Yahoo is not trusted (step 1), so this does not correct anything: agreement is reassurance, and a
disagreement marks a figure to look at in the filing itself.
Input:  output/figures_<region>.csv, raw/prices_<region>.csv (for Yahoo symbols)
Output: raw/yahoo_statements_<region>.json (cache), output/crosscheck_<region>.csv
Run: python3 code/crosscheck_yahoo.py us
"""
import csv
import json
import math
import os
import sys

import yfinance as yf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import net  # noqa: E402

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROWS = {  # our metric: (statement, Yahoo row)
    'revenue': ('inc', 'Total Revenue'),
    'net_income': ('inc', 'Net Income Common Stockholders'),
    'operating_cash_flow': ('cf', 'Operating Cash Flow'),
    'equity': ('bs', 'Stockholders Equity'),
    'debt': ('bs', 'Total Debt'),
    'lease': ('bs', 'Capital Lease Obligations'),
}


def fetch(symbol):
    t = yf.Ticker(symbol)
    out = {}
    for st, df in (('inc', t.income_stmt), ('bs', t.balance_sheet), ('cf', t.cashflow)):
        if df is None or df.empty:
            continue
        for col in df.columns:
            for metric, (s, row) in ROWS.items():
                if s == st and row in df.index:
                    v = df.loc[row, col]
                    if v is not None and not (isinstance(v, float) and math.isnan(v)):
                        out.setdefault(metric, {})[str(col.date())] = float(v)
    return out


def main():
    region = sys.argv[1]
    cache_path = f'{BASE}/raw/yahoo_statements_{region}.json'
    cache = json.load(open(cache_path)) if os.path.exists(cache_path) else {}
    prices = {r['ticker']: r['yahoo'] for r in csv.DictReader(open(f'{BASE}/raw/prices_{region}.csv'))}
    for i, (t, y) in enumerate(prices.items()):
        if t in cache:
            continue
        try:
            cache[t] = net.patient(fetch, y)
        except Exception as e:  # kept, so a company Yahoo has nothing for is not asked again; a refusal is not kept
            if not net.rate_limited(e):
                cache[t] = {'error': str(e)}
        if i % 50 == 0:
            print(i, t, flush=True)
            json.dump(cache, open(cache_path, 'w'))
    json.dump(cache, open(cache_path, 'w'))

    out = []
    for r in csv.DictReader(open(f'{BASE}/output/figures_{region}.csv')):
        yh = cache.get(r['ticker'], {})
        for metric in ('revenue', 'net_income', 'operating_cash_flow', 'equity', 'debt'):
            series = yh.get(metric, {})
            # Yahoo dates its columns by period end; match within 7 days
            hit = [v for d, v in series.items() if abs((_d(d) - _d(r['period_end'])).days) <= 7]
            if not hit or r[metric] in ('', None):
                continue
            ours, theirs = float(r[metric]), hit[0]
            if metric == 'debt':
                lease = [v for d, v in yh.get('lease', {}).items() if abs((_d(d) - _d(r['period_end'])).days) <= 7]
                theirs -= lease[0] if lease else 0  # our debt leaves leases out
            denom = max(abs(ours), abs(theirs), 1.0)
            diff = abs(ours - theirs) / denom
            out.append({'ticker': r['ticker'], 'fiscal_year': r['fiscal_year'], 'metric': metric, 'ours': ours,
                        'yahoo': theirs, 'diff': round(diff, 4),
                        'verdict': 'agree' if diff <= 0.02 else ('close' if diff <= 0.10 else 'DIFFERENT')})
    with open(f'{BASE}/output/crosscheck_{region}.csv', 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    from collections import Counter
    for metric in ('revenue', 'net_income', 'operating_cash_flow', 'equity', 'debt'):
        c = Counter(o['verdict'] for o in out if o['metric'] == metric)
        n = sum(c.values())
        print(f'{metric:20s} n={n:5d} agree {c["agree"] / n:.1%} close {c["close"] / n:.1%} different {c["DIFFERENT"] / n:.1%}')


def _d(s):
    from datetime import date
    return date.fromisoformat(s[:10])


if __name__ == '__main__':
    main()

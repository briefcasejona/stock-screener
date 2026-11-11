"""Turn the screen results into the dashboard's "screen" dataset (one JSON file).

Input:  output/screen_us.csv, output/screen_eu.csv (screen.py), output/figures_<region>.csv (for the source)
Output: dashboard/screen.json, one row per screened company
Run: python3 -I code/build_screen_data.py
"""
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import localdata  # noqa: E402

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGIONS = {'us': 'US', 'eu': 'Europe'}
NUM = ['roic_median', 'roic_min', 'fcf_to_net_income', 'net_debt_m', 'net_debt_to_fcf', 'margin_median', 'margin_min',
       'shares_change',
       'revenue_growth', 'revenue_growth_3y', 'fcf_ps_growth', 'implied_growth', 'pe', 'fcf_yield', 'price']
TESTS = ['q_roic', 'q_roic_min', 'q_cash_conversion', 'q_debt', 'q_margins', 'q_dilution',
         'g_revenue', 'g_fcf_ps', 'g_still_growing', 'g_price']


def num(x, nd=4):
    return round(float(x), nd) if x not in ('', None) else None


def display_names():
    """Readable company names for Europe (the ETF list is in capitals): the display_name column of universe_eu.csv
    (build_universe_eu.py), else Yahoo's long name when its search results are at hand, else the list's name."""
    names = {}
    ys_path, u_path = f'{BASE}/raw/yahoo_search_eu.json', f'{BASE}/raw/universe_eu.csv'
    if os.path.exists(u_path):
        ys = json.load(open(ys_path, encoding='utf-8', errors='replace')) if os.path.exists(ys_path) else {}
        for u in localdata.eu_universe():
            names[u['ticker']] = u.get('display_name') or ys.get(u.get('isin', ''), {}).get('name') or u['name']
    return names


def main():
    names = display_names()
    out = []
    for region, label in REGIONS.items():
        path = f'{BASE}/output/screen_{region}.csv'
        if not os.path.exists(path):
            continue
        source = {}
        for r in csv.DictReader(open(f'{BASE}/output/figures_{region}.csv', encoding='utf-8', errors='replace')):
            source[r['ticker']] = r.get('source') or 'SEC'
        for r in csv.DictReader(open(path, encoding='utf-8', errors='replace')):
            row = {'ticker': r['ticker'], 'company': names.get(r['ticker'], r['name']).replace('|', '').strip(), 'region': label, 'sector': r['sector'],
                   'source': source.get(r['ticker'], ''), 'years': int(r['years']),
                   'first_year': int(r['first_year']), 'last_year': int(r['last_year']),
                   'report_currency': r['report_currency'], 'price_currency': r['price_currency'],
                   'quality_passed': int(r['quality_passed']), 'garp_passed': int(r['garp_passed']),
                   'passed': int(r['passed']), 'margin_kind': r['margin_kind'], 'data_flags': r['data_flags']}
            for k in NUM:
                row[k] = num(r[k], 2 if k in ('pe', 'price', 'net_debt_m') else 4)
            for k in TESTS:
                row[k] = r[k]
            out.append(row)
    out.sort(key=lambda o: (-o['passed'], -o['quality_passed'], o['implied_growth'] if o['implied_growth'] is not None else 9))
    os.makedirs(f'{BASE}/dashboard', exist_ok=True)
    json.dump(out, open(f'{BASE}/dashboard/screen.json', 'w', encoding='utf-8'), separators=(',', ':'))
    print(len(out), 'rows;', sum(o['passed'] == 10 for o in out), 'pass all 10')


if __name__ == '__main__':
    main()

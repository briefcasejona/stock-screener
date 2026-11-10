"""Download SEC EDGAR company facts for the screener's US universe (S&P 500 minus banks, insurers, real estate).

Input:  raw/sp500_constituents.csv (Wikipedia list, columns Symbol, Security, GICS Sector, CIK, ...)
Output: a gzip cache of each company's facts in CACHE (local disk; the files are large), plus
        raw/universe_us.csv with the companies kept.
Run: python3 -I code/fetch_sec.py   (from the screener folder). Safe to re-run: cached files are skipped.
"""
import csv
import gzip
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import net  # noqa: E402

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.environ.get('SEC_CACHE', '/tmp/claude-0/sec_cache')
EXCLUDED_SECTORS = {'Financials', 'Real Estate'}  # playbook: special cases, separate rules


def main():
    os.makedirs(CACHE, exist_ok=True)
    rows = list(csv.DictReader(open(f'{BASE}/raw/sp500_constituents.csv')))
    keep = [r for r in rows if r['GICS Sector'] not in EXCLUDED_SECTORS]
    with open(f'{BASE}/raw/universe_us.csv', 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=['ticker', 'name', 'sector', 'industry', 'cik'])
        w.writeheader()
        for r in keep:
            w.writerow({'ticker': r['Symbol'], 'name': r['Security'], 'sector': r['GICS Sector'],
                        'industry': r['GICS Sub-Industry'], 'cik': f"{int(r['CIK']):010d}"})
    print(f'{len(rows)} in the S&P 500 list, {len(keep)} kept (financials and real estate left out)')
    failed = []
    for i, r in enumerate(keep):
        cik = f"{int(r['CIK']):010d}"
        path = f'{CACHE}/{cik}.json.gz'
        if os.path.exists(path):
            continue
        try:  # net.fetch waits and tries again when the SEC asks us to slow down
            data = net.fetch(f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json')
            with gzip.open(path, 'wb') as fh:
                fh.write(data)
        except Exception:
            failed.append((r['Symbol'], cik))
        time.sleep(0.15)  # stay well under SEC's limit of 10 requests a second
        if i % 50 == 0:
            print(i, r['Symbol'], flush=True)
    print('failed:', failed)


if __name__ == '__main__':
    main()

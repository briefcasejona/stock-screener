"""Yearly figures for the European universe: SEC filings where the company files with the SEC (10+ years),
otherwise its ESEF annual reports from filings.xbrl.org (from FY2020; each report also holds the year before).

ESEF reports are read the same way as in step 1 (data-check/code/extract.py): only facts without extra
dimensions, period ends moved back one day (xBRL-JSON writes them as the next midnight). The figures then go
through the same rules as the US (extract_sec.build_row): the same concepts, newest report wins, the same
fallbacks, so both regions are judged alike.

Input:  raw/universe_eu.csv (build_universe_eu.py), raw/splits_eu.json (prices.py eu),
        user_reports/<ticker>/*.json (annual reports added with user_reports.py)
Output: output/figures_eu.csv (same columns as figures_us.csv, plus source), raw/esef_filings_eu.json (filing lists)
Caches: ESEF_CACHE (default /tmp/claude-0/esef_cache, local disk), SEC_CACHE as in fetch_sec.py
Run: python3 -I code/extract_esef.py
"""
import csv
import glob
import gzip
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract_sec import CACHE as SEC_CACHE, build_row, index, load, periods, real_split  # noqa: E402
import localdata  # noqa: E402
import net  # noqa: E402

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.environ.get('ESEF_CACHE', '/tmp/claude-0/esef_cache')
API = 'https://filings.xbrl.org'
KEEP_DIMS = {'concept', 'entity', 'period', 'unit', 'language'}


def get(url, as_json=True):
    try:
        b = net.fetch(url, timeout=120)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise RuntimeError(f'could not fetch {url}: {e}')
    except Exception as e:
        raise RuntimeError(f'could not fetch {url}: {e}')
    return json.loads(b) if as_json else b


def filing_list(lei):
    """All ESEF filings of one entity. (The API's own 'next' links drop the entity, so pages are counted here.)"""
    out, page = [], 1
    while True:
        d = get(f'{API}/api/entities/{lei}/filings?page%5Bsize%5D=100&page%5Bnumber%5D={page}')
        if not d:
            return out
        out += [f['attributes'] for f in d['data']]
        if len(out) >= d.get('meta', {}).get('count', 0) or not d['data']:
            return out
        page += 1


def choose(filings):
    """One report per period end: fewest validation errors, then the most recently added (a corrected re-filing)."""
    best = {}
    for f in filings:
        if not f.get('json_url'):
            continue
        key = (-(f.get('error_count') or 0), f.get('date_added') or '')
        if f['period_end'] not in best or key > best[f['period_end']][0]:
            best[f['period_end']] = (key, f)
    return [f for _, f in sorted(best.values(), key=lambda kv: kv[1]['period_end'])]


def report_facts(f):
    """Facts of one report as (concept, start, end, value, unit, report id, filed), cached on local disk."""
    path = f"{CACHE}/{f['fxo_id']}.json.gz"
    if not os.path.exists(path):
        data = get(API + urllib.parse.quote(f['json_url'], safe='/'))  # some file names contain spaces
        facts = []
        for x in (data or {}).get('facts', {}).values():
            dims = x['dimensions']
            if set(dims) - KEEP_DIMS or x.get('value') in (None, ''):
                continue
            try:
                value = float(x['value'])
            except (TypeError, ValueError):
                continue
            period = dims['period']
            if '/' in period:
                start, end = period.split('/')
                start = start[:10]
            else:
                start, end = None, period
            end = (date.fromisoformat(end[:10]) - timedelta(days=1)).isoformat()
            unit = dims.get('unit', '').replace('iso4217:', '').replace('xbrli:', '')
            facts.append([dims['concept'].split(':')[-1], start, end, value, unit])
        with gzip.open(path, 'wt') as fh:
            json.dump(facts, fh)
    facts = json.load(gzip.open(path, 'rt'))
    # 'filed' orders reports (newest wins) and decides split adjustment. filings.xbrl.org's date_added can be
    # years late for old reports, so it is capped at four months after the year end.
    pe = date.fromisoformat(f['period_end'])
    filed = min((f.get('date_added') or '9999')[:10], (pe + timedelta(days=120)).isoformat())
    return [(c, s, e, v, u, f['fxo_id'], filed) for c, s, e, v, u in facts]


def fetch_sec(cik):
    path = f'{SEC_CACHE}/{cik}.json.gz'
    if os.path.exists(path):
        return
    data = get(f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json', as_json=False)
    with gzip.open(path, 'wb') as fh:
        fh.write(data)
    time.sleep(0.15)


def company_rows(u, lists, splits_all, failed):
    """One company's yearly rows: SEC or ESEF reports, plus the annual reports the user added.
    lists caches ESEF filing lists by LEI; reports that cannot be read are added to failed."""
    os.makedirs(CACHE, exist_ok=True)  # a new laptop starts with empty caches
    os.makedirs(SEC_CACHE, exist_ok=True)
    splits = sorted((d, r) for d, r in splits_all.get(u['ticker'], []) if real_split(r))
    if u['source'] == 'sec':
        fetch_sec(u['cik'])
        facts = load(u['cik'])[1]
    elif u['lei']:
        if u['lei'] not in lists:
            lists[u['lei']] = filing_list(u['lei'])
        facts = []
        for f in choose(lists[u['lei']]):
            try:
                facts += report_facts(f)
            except RuntimeError as e:  # one unreadable report should not stop the run; it is listed at the end
                failed.append(f"{u['ticker']} {f['period_end']}: {e}")
    else:
        facts = []
    # annual reports the user added (user_reports.py): same facts, merged; newest report wins
    own = sorted(glob.glob(f"{localdata.USER_REPORTS}/{u['ticker']}/*.json"))
    n_public = len(facts)
    for path in own:
        d = json.load(open(path))
        filed = (date.fromisoformat(d['period_end']) + timedelta(days=120)).isoformat()
        facts += [(c, s, e, v, unit, 'user:' + os.path.basename(path), filed) for c, s, e, v, unit in d['facts']]
    idx = index(facts)
    rows = []
    for fy, end in sorted(periods(facts).items()):
        row = build_row(u, fy, end, idx, splits)
        public = 'SEC' if u['source'] == 'sec' else 'ESEF'
        row['source'] = (public + ' + your files' if n_public else 'your files') if own else public
        rows.append(row)
    return rows


def main():
    os.makedirs(CACHE, exist_ok=True)
    os.makedirs(SEC_CACHE, exist_ok=True)
    universe = localdata.eu_universe()
    splits_all = json.load(open(f'{BASE}/raw/splits_eu.json')) if os.path.exists(f'{BASE}/raw/splits_eu.json') else {}
    lists_path = f'{BASE}/raw/esef_filings_eu.json'
    lists = json.load(open(lists_path)) if os.path.exists(lists_path) else {}
    out, no_data, failed = [], [], []
    for i, u in enumerate(universe):
        rows = company_rows(u, lists, splits_all, failed)
        if not rows:
            no_data.append(u['ticker'])
        out += rows
        if i % 25 == 0:
            print(i, u['ticker'], len(rows), flush=True)
            json.dump(lists, open(lists_path, 'w'))
    json.dump(lists, open(lists_path, 'w'))
    with open(f'{BASE}/output/figures_eu.csv', 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    print(f'{len(out)} company-years for {len({r["ticker"] for r in out})} of {len(universe)} companies; '
          f'no figures for {len(no_data)}: {no_data}')
    print('reports that could not be read:', failed)


if __name__ == '__main__':
    main()

"""The European universe: STOXX Europe 600 members (Xtrackers ETF holdings) minus banks, insurers and real estate.

For each company it finds
- the Yahoo symbol and sector (Yahoo search by ISIN), used for prices and for the sector filter;
- the LEI (GLEIF, by ISIN), which is how filings.xbrl.org files ESEF annual reports;
- the SEC CIK when the company files annual reports with the SEC (20-F/40-F/10-K), because SEC data
  reaches back 10+ years while ESEF starts in 2020. SEC candidates are found by name and then
  confirmed against the SEC's own record (it must file annual reports and not be a US address,
  unless the holdings list says the company is American).

Input:  raw/stoxx600_xtrackers_holdings.csv
Output: raw/universe_eu.csv (ticker, name, isin, country, sector, industry, yahoo, lei, cik, source),
        caches raw/yahoo_search_eu.json, raw/gleif_eu.json, raw/sec_match_eu.json
Run: python3 -I code/build_universe_eu.py
"""
import csv
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

import yfinance as yf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import net  # noqa: E402

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXCLUDED_SECTORS = {'Financial Services', 'Real Estate'}  # playbook: special cases, separate rules
ANNUAL = {'20-F', '40-F', '10-K'}
SUFFIXES = r'\b(plc|ag|se|sa|nv|n v|asa|ab|a s|as|oyj|spa|s p a|bv|ltd|limited|group|holding|holdings|co|kgaa|' \
           r'and|the|company|corporation|corp|inc|international|de|class|cl|a|b|publ|reg|registered|shs|sca|lt)\b'


def norm(name):
    n = name.lower().replace('&', ' and ').replace('.', ' ').replace('-', ' ').replace(',', ' ')
    n = re.sub(r'\(.*?\)', ' ', n)
    n = re.sub(SUFFIXES, ' ', n)
    return ' '.join(n.split())


LEGAL = r'\b(plc|ag|se|sa|nv|n v|asa|ab|oyj|spa|s p a|inc|ltd|limited|kgaa|class [ab]|p l c)\b'
COUNTRY_NAMES = {'GB': 'United Kingdom', 'CH': 'Switzerland', 'NL': 'Netherlands', 'DE': 'Germany', 'FR': 'France',
                 'AU': 'Australia', 'DK': 'Denmark', 'NO': 'Norway', 'SE': 'Sweden', 'LU': 'Luxembourg', 'IT': 'Italy'}


def wrong_us_namesake(name, hit):
    """Name matching strips words like 'group' and 'holdings', so Compass Group plc matches Compass, Inc. A
    filer of US 10-Ks with a US address is kept only when the names match with just the legal form removed
    (Logitech International S.A. files 10-Ks from California and is kept)."""
    us_address = len(hit['country']) == 2 and hit['country'].isalpha()
    if not (us_address and hit['forms'] == ['10-K']):
        return False
    strict = lambda n: ' '.join(re.sub(LEGAL, ' ', re.sub(r'[^a-z ]', ' ', n.lower().replace('&', ' and '))).split())
    return strict(name) != strict(hit['sec_name'])


def get_json(url, headers=None):
    req = urllib.request.Request(url, headers=headers or net.headers_for(url))
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except Exception:
            time.sleep(2 ** attempt)
    return None


def cached(path, keys, fetch, every=25):
    cache = json.load(open(path)) if os.path.exists(path) else {}
    for i, k in enumerate(keys):
        if k in cache:
            continue
        cache[k] = fetch(k)
        if i % every == 0:
            print(os.path.basename(path), i, k, flush=True)
            json.dump(cache, open(path, 'w'))
    json.dump(cache, open(path, 'w'))
    return cache


def yahoo(isin):
    try:
        q = [q for q in yf.Search(isin, max_results=5).quotes if q.get('quoteType') == 'EQUITY']
    except Exception as e:
        return {'error': str(e)}
    if not q:
        return {}
    return {'symbol': q[0]['symbol'], 'exchange': q[0].get('exchange'), 'sector': q[0].get('sectorDisp') or q[0].get('sector', ''),
            'industry': q[0].get('industryDisp') or q[0].get('industry', ''), 'name': q[0].get('longname') or q[0].get('shortname', '')}


def gleif(isin, name=''):
    d = get_json('https://api.gleif.org/api/v1/lei-records?filter%5Bisin%5D=' + isin, {'Accept': 'application/vnd.api+json'})
    if (not d or not d.get('data')) and name:
        # GLEIF does not map every ISIN (Finnish shares, for one): search by name in the ISIN's country and keep
        # only a record whose legal name is the same once the legal form is removed
        q = urllib.parse.urlencode({'filter[fulltext]': name, 'filter[entity.legalAddress.country]': isin[:2], 'page[size]': 10})
        d = get_json('https://api.gleif.org/api/v1/lei-records?' + q, {'Accept': 'application/vnd.api+json'}) or {}
        d['data'] = [x for x in d.get('data', []) if norm(x['attributes']['entity']['legalName']['name']) == norm(name)
                     and x['attributes']['entity']['status'] == 'ACTIVE'][:1]
    if not d or not d.get('data'):
        return {}
    a = d['data'][0]['attributes']
    return {'lei': d['data'][0]['id'], 'legal_name': a['entity']['legalName']['name'],
            'country': a['entity']['legalAddress']['country']}


def main():
    rows = [r for r in csv.DictReader(open(f'{BASE}/raw/stoxx600_xtrackers_holdings.csv'))
            if r['Type of Security'] == 'Aktien' and float(r['Weighting'] or 0) > 0]
    isins = [r['ISIN'] for r in rows]
    ys = cached(f'{BASE}/raw/yahoo_search_eu.json', isins, yahoo)
    keep = [r for r in rows if ys.get(r['ISIN'], {}).get('symbol') and ys[r['ISIN']]['sector'] not in EXCLUDED_SECTORS]
    no_symbol = [r['Name'] for r in rows if not ys.get(r['ISIN'], {}).get('symbol')]
    lei = cached(f'{BASE}/raw/gleif_eu.json', [r['ISIN'] for r in keep], gleif)
    retry = [i for i, v in lei.items() if not v]  # GLEIF connections drop now and then: try the empty ones again
    if retry:
        for i in retry:
            lei[i] = gleif(i, ys[i].get('name', ''))
        json.dump(lei, open(f'{BASE}/raw/gleif_eu.json', 'w'))

    # SEC candidates by name, confirmed against each candidate's SEC record
    sec_path = f'{BASE}/raw/sec_match_eu.json'
    sec = json.load(open(sec_path)) if os.path.exists(sec_path) else {}
    tickers = get_json('https://www.sec.gov/files/company_tickers.json')
    by_name = {}
    for t in tickers.values():
        by_name.setdefault(norm(t['title']), set()).add(f"{int(t['cik_str']):010d}")
    for r in keep:
        if r['ISIN'] in sec:
            continue
        names = {norm(r['Name']), norm(ys[r['ISIN']]['name']), norm(lei.get(r['ISIN'], {}).get('legal_name', ''))} - {''}
        ciks = set().union(*(by_name.get(n, set()) for n in names))
        hits = []
        for cik in sorted(ciks):
            sub = get_json(f'https://data.sec.gov/submissions/CIK{cik}.json')
            time.sleep(0.15)
            if not sub:
                continue
            forms = sub['filings']['recent']['form']
            dates = sub['filings']['recent']['filingDate']
            annual = [d for f, d in zip(forms, dates) if f in ANNUAL]
            addr = (sub.get('addresses', {}).get('business') or {})
            hits.append({'cik': cik, 'sec_name': sub.get('name'), 'last_annual': max(annual) if annual else '',
                         'forms': sorted({f for f in forms if f in ANNUAL}),
                         'country': addr.get('stateOrCountryDescription') or addr.get('stateOrCountry') or ''})
        sec[r['ISIN']] = hits
        json.dump(sec, open(sec_path, 'w'), indent=0)

    out = []
    for r in keep:
        y, l = ys[r['ISIN']], lei.get(r['ISIN'], {})
        cik = ''
        hits = [h for h in sec.get(r['ISIN'], []) if h['last_annual'] >= '2025-01-01'  # still files with the SEC
                and not wrong_us_namesake(r['Name'], h)]
        # Rio Tinto plc and Rio Tinto Ltd both match: take the one registered in the company's own country
        hits.sort(key=lambda h: COUNTRY_NAMES.get(l.get('country', ''), '?') not in h['country'])
        if hits:
            cik = hits[0]['cik']
        out.append({'ticker': y['symbol'], 'name': r['Name'], 'isin': r['ISIN'], 'country': l.get('country', ''),
                    'sector': y['sector'], 'industry': y['industry'], 'yahoo': y['symbol'], 'lei': l.get('lei', ''),
                    'cik': cik, 'source': 'sec' if cik else ('esef' if l.get('lei') else 'none')})
    with open(f'{BASE}/raw/universe_eu.csv', 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    from collections import Counter
    print(f'{len(rows)} holdings, {len(keep)} kept (financials and real estate left out); no Yahoo symbol: {no_symbol}')
    print('source:', Counter(o['source'] for o in out))


if __name__ == '__main__':
    main()

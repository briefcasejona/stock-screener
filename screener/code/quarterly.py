"""The latest twelve months (TTM) from quarterly and half-year reports, next to the last full year.

Quarterly figures are unaudited and come as "year to date" (the months since the last year end). Twelve months are
put together the standard way, one figure at a time, from the same concept in all three parts:
    last full year + this year to date - the same months a year earlier
Balance-sheet figures (cash, debt, equity) are taken as they stand at the quarter's end. Shares and earnings per
share are not added up this way where that would be wrong: the diluted share count is the year-to-date one.

The result has the same fields as a yearly row of figures_<region>.csv (built by extract_sec.build_row), so it reads
the same way. It is only shown next to the yearly figures; the screener and the valuation keep using full years.

Sources:
- US companies (and others filing with the SEC): every 10-Q in the SEC company facts, no upload needed;
- quarterly or half-year reports the user added (user_reports.py interim): kind "interim" in user_reports/<ticker>/.

Run: python3 -I code/quarterly.py <ticker>
"""
import csv
import glob
import gzip
import json
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import localdata  # noqa: E402
from extract_sec import CACHE as SEC_CACHE, FLOWS, SHARE_METRICS, build_row, index, real_split  # noqa: E402

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INTERIM_FORMS = {'10-Q', '10-Q/A', '10-K', '10-K/A', '20-F', '20-F/A', '40-F', '40-F/A', '10-KT', '6-K', '6-K/A'}
SLACK = 7  # days: 52/53-week years end on slightly different dates


def _d(s):
    return date.fromisoformat(s)


def near(a, b, days=SLACK):
    return abs((_d(a) - _d(b)).days) <= days


def sec_facts(cik):
    """Every non-dimensional fact of a company's SEC company facts, annual and quarterly filings alike."""
    path = f'{SEC_CACHE}/{cik}.json.gz'
    if not os.path.exists(path):
        return []
    data = json.load(gzip.open(path))
    out = []
    for tags in data.get('facts', {}).values():
        for concept, body in tags.items():
            for unit, rows in body['units'].items():
                for r in rows:
                    if r.get('form') in INTERIM_FORMS:
                        out.append((concept, r.get('start'), r['end'], float(r['val']), unit, r['accn'], r['filed']))
    return out


def own_interim(ticker):
    """Facts of the quarterly and half-year reports the user added, newest report wins (filed = when added)."""
    out = []
    for path in sorted(glob.glob(f'{localdata.USER_REPORTS}/{ticker}/*__interim.json')):
        d = json.load(open(path, encoding='utf-8', errors='replace'))
        filed = d.get('added') or d['period_end']
        out += [(c, s, e, v, unit, 'user:' + os.path.basename(path), filed + 'z') for c, s, e, v, unit in d['facts']]
    return out


def latest_end(facts, annual_end):
    """The end of the newest year-to-date period after the last full year (None when there is none)."""
    names = {c for m in ('revenue', 'net_income', 'operating_cash_flow') for c in FLOWS[m][1]}
    first = (_d(annual_end) + timedelta(days=1)).isoformat()
    ends = [e for c, s, e, v, u, a, f in facts
            if c in names and s and near(s, first) and 60 <= (_d(e) - _d(s)).days <= 300]
    return max(ends) if ends else None


def newest(cands):
    return max(cands, key=lambda f: f[6]) if cands else None


def ytd(idx, concept, start, end):
    return newest([f for f in idx.get(concept, ()) if f[1] and near(f[1], start) and near(f[2], end)])


def same_months_before(idx, concept, cur):
    """The same months one year earlier, as compared in the same reports."""
    days = (_d(cur[2]) - _d(cur[1])).days
    end = (_d(cur[2]) - timedelta(days=365)).isoformat()
    return newest([f for f in idx.get(concept, ()) if f[1] and near(f[2], end)
                   and abs((_d(f[2]) - _d(f[1])).days - days) <= 10])


def full_year(idx, concept, end):
    return newest([f for f in idx.get(concept, ()) if f[1] and near(f[2], end)
                   and 350 <= (_d(f[2]) - _d(f[1])).days <= 380])


def ttm(u, annual, facts, splits=()):
    """The twelve months to the newest quarter after `annual` (a yearly row), or None when no newer quarter is in
    the facts. Returns {'row': yearly-style row, 'quarter_end', 'annual_end', 'months', 'missing': [metrics]}."""
    a_end = annual['period_end']
    e = latest_end(facts, a_end)
    if not e:
        return None
    first = (_d(a_end) + timedelta(days=1)).isoformat()
    idx = index(facts)
    synth, missing = [], []
    for m, (how, concepts) in FLOWS.items():
        own = annual.get(m + '_concept') or ''
        order = ([own] if own else []) + [c for c in concepts if c != own]
        done = False
        for c in order:
            cur = ytd(idx, c, first, e)
            if not cur:
                continue
            if m in SHARE_METRICS:  # a share count is not added up: the year-to-date average is the one to use
                synth.append((c, (_d(e) - timedelta(days=364)).isoformat(), e, cur[3], cur[4], cur[5], cur[6]))
                done = True
                break
            before = same_months_before(idx, c, cur)
            if not before:
                continue
            fy = None if c == own else full_year(idx, c, a_end)
            if fy:
                year = fy[3]
            elif (c == own or cur[5].startswith('user:')) and annual.get(m) not in ('', None):
                # a report the user added names its lines by meaning (Revenue), so it goes with the full year's
                # figure for the same line, whatever concept that came from
                year = float(annual[m])
            else:
                continue
            synth.append((c, (_d(e) - timedelta(days=364)).isoformat(), e, year + cur[3] - before[3], cur[4], cur[5], cur[6]))
            done = True
            break
        if not done and own and annual.get(m) not in ('', None):
            missing.append(m)
    instants = [f for f in facts if not f[1] and f[2] == e]
    row = build_row(u, _d(e).year, e, index(synth + instants), [s for s in splits if real_split(s[1])])
    months = round((_d(e) - _d(a_end)).days / 30.4)
    own = any(f[5].startswith('user:') for f in synth + instants)
    return {'row': row, 'quarter_end': e, 'annual_end': a_end, 'months': months, 'missing': missing,
            'source': 'your quarterly report' if own else 'SEC quarterly filings (10-Q)'}


def universe_row(ticker):
    for region in ('us', 'eu'):
        rows = localdata.eu_universe() if region == 'eu' else \
            csv.DictReader(open(f'{BASE}/raw/universe_us.csv', encoding='utf-8', errors='replace'))
        for u in rows:
            if u['ticker'] == ticker:
                return region, {**u, 'source': u.get('source') or 'sec', 'sector': u.get('sector', '')}
    return None, None


def for_ticker(ticker):
    """TTM for one company from what is on disk (no downloads), with where it came from; None when there is none."""
    region, u = universe_row(ticker)
    if not u:
        return None
    path = f'{BASE}/output/figures_{region}.csv'
    years = [r for r in csv.DictReader(open(path, encoding='utf-8', errors='replace')) if r['ticker'] == ticker] \
        if os.path.exists(path) else []
    if not years:
        return None
    annual = years[-1]
    facts = (sec_facts(u['cik']) if u['source'] == 'sec' and u.get('cik') else []) + own_interim(ticker)
    splits_path = f'{BASE}/raw/splits_{region}.json'
    splits = json.load(open(splits_path, encoding='utf-8', errors='replace')).get(ticker, []) \
        if os.path.exists(splits_path) else []
    r = ttm(u, annual, facts, splits)
    if not r:
        return None
    r['annual'] = annual
    return r


if __name__ == '__main__':
    res = for_ticker(sys.argv[1])
    print(json.dumps(res, indent=1, default=str) if res else 'no quarter after the last full year')

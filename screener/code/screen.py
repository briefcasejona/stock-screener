"""Run the playbook's quality and GARP filters and the reverse DCF over every company in a region.

The screener is an idea generator: it finds companies worth a deep dive. It does not set bear/base/bull
values, because those need judgement about each business (the playbook, step 3).

Input:  output/figures_<region>.csv (extract_sec.py / extract_esef.py), raw/prices_<region>.csv,
        raw/fx.json (when prices and figures use different currencies),
        output/crosscheck_<region>.csv (optional, crosscheck_yahoo.py: big disagreements become data flags)
Output: output/screen_<region>.csv, one row per company with every filter's value and result.
Run: python3 -I code/screen.py us
"""
import csv
import json
import os
import statistics
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(BASE), 'playbook', 'code'))
from valuation import cagr, reverse_dcf  # noqa: E402

R_BASE, G_T_BASE = 0.09, 0.025  # playbook base case
YEARS = 10
MIN_YEARS = 5


def num(x):
    return float(x) if x not in ('', None) else None


def per_year(rows):
    out = []
    for r in rows:
        y = {k: num(r[k]) for k in ('revenue', 'gross_profit', 'operating_income', 'pretax_income', 'income_tax',
                                     'net_income', 'eps_diluted', 'diluted_shares', 'operating_cash_flow', 'capex',
                                     'equity', 'cash', 'short_term_investments', 'debt')}
        y['year'], y['debt_found'] = int(r['fiscal_year']), r['debt_found'] == 'yes'
        # no capital spending figure: free cash flow unknown (taking operating cash flow would overstate it)
        y['fcf'] = (y['operating_cash_flow'] - y['capex']
                    if y['operating_cash_flow'] is not None and y['capex'] is not None else None)
        y['fcf_ps'] = y['fcf'] / y['diluted_shares'] if y['fcf'] is not None and y['diluted_shares'] else None
        # no debt figure in the standard tags (some companies use their own): unknown, not zero
        y['net_debt'] = ((y['debt'] or 0) - (y['cash'] or 0) - (y['short_term_investments'] or 0)
                         if y['debt_found'] or r.get('debt_free_confirmed') else None)
        tax_rate = 0.21
        if y['pretax_income'] and y['pretax_income'] > 0 and y['income_tax'] is not None:
            tax_rate = min(max(y['income_tax'] / y['pretax_income'], 0.0), 0.5)
        capital = y['equity'] + y['net_debt'] if y['equity'] is not None and y['net_debt'] is not None else None
        y['roic'] = (y['operating_income'] * (1 - tax_rate) / capital
                     if y['operating_income'] is not None and capital and capital > 0 else None)
        y['gross_margin'] = y['gross_profit'] / y['revenue'] if y['gross_profit'] is not None and y['revenue'] else None
        y['operating_margin'] = y['operating_income'] / y['revenue'] if y['operating_income'] is not None and y['revenue'] else None
        out.append(y)
    return out


def growth_of_averages(values, k):
    """Compound growth between the average of the first k and the last k values."""
    n = len(values)
    a, b = sum(values[:k]) / k, sum(values[-k:]) / k
    if a <= 0 or b <= 0:
        return None
    return cagr(a, b, n - k)


def screen(ticker, meta, rows, price, fx, second_source=()):
    ys = per_year(rows)[-YEARS:]
    res = {'ticker': ticker, **meta, 'years': len(ys), 'first_year': ys[0]['year'], 'last_year': ys[-1]['year']}
    flags = []
    # quality
    roics = [y['roic'] for y in ys if y['roic'] is not None]
    res['roic_median'] = statistics.median(roics) if len(roics) >= MIN_YEARS else None
    res['roic_min'] = min(roics) if len(roics) >= MIN_YEARS else None
    if len(roics) < len(ys):
        flags.append(f'ROIC missing for {len(ys) - len(roics)} years (negative capital or missing data)')
    fcfs = [y['fcf'] for y in ys if y['fcf'] is not None]
    nis = [y['net_income'] for y in ys if y['fcf'] is not None and y['net_income'] is not None]
    res['fcf_to_net_income'] = sum(fcfs) / sum(nis) if len(nis) >= MIN_YEARS and sum(nis) > 0 else None
    last = ys[-1]
    res['net_debt_m'] = last['net_debt'] / 1e6 if last['net_debt'] is not None else None
    res['net_debt_to_fcf'] = (last['net_debt'] / last['fcf'] if last['net_debt'] is not None and last['fcf'] and last['fcf'] > 0 else None)
    if not last['debt_found'] and rows[-1].get('debt_free_confirmed'):
        flags.append('no debt tagged; the second source also shows no borrowings (leases aside), so debt is taken as zero')
    elif not last['debt_found']:
        flags.append('no debt figure in the standard tags for the latest year: debt test and value not computed')
    no_capex = sum(1 for y in ys if y['operating_cash_flow'] is not None and y['capex'] is None)
    if no_capex:
        flags.append(f'capital spending not found for {no_capex} years (free cash flow left out for those years)')
    gms = [y['gross_margin'] for y in ys if y['gross_margin'] is not None]
    margin_kind = 'gross'
    if len(gms) < MIN_YEARS:
        gms, margin_kind = [y['operating_margin'] for y in ys if y['operating_margin'] is not None], 'operating'
    res['margin_kind'] = margin_kind
    res['margin_median'] = statistics.median(gms) if len(gms) >= MIN_YEARS else None
    res['margin_min'] = min(gms) if len(gms) >= MIN_YEARS else None
    shares = [y['diluted_shares'] for y in ys if y['diluted_shares']]
    res['shares_change'] = cagr(shares[0], shares[-1], len(shares) - 1) if len(shares) >= MIN_YEARS else None
    for a, b in zip(shares, shares[1:]):
        if b / a > 1.4 or b / a < 0.7:
            flags.append('share count jumps more than 40% in one year (merger or unadjusted split)')
            break
    # GARP
    revs = [y['revenue'] for y in ys if y['revenue']]
    res['revenue_growth'] = cagr(revs[0], revs[-1], len(revs) - 1) if len(revs) >= MIN_YEARS and revs[0] > 0 else None
    res['revenue_growth_3y'] = cagr(revs[-4], revs[-1], 3) if len(revs) >= 4 and revs[-4] > 0 else None
    fps = [y['fcf_ps'] for y in ys if y['fcf_ps'] is not None]
    k = 3 if len(fps) >= 7 else 2
    res['fcf_ps_growth'] = growth_of_averages(fps, k) if len(fps) >= MIN_YEARS else None
    # valuation (price converted into the reporting currency)
    res['price'], res['price_currency'] = price['price'], price['currency']
    res['fx_to_report'] = fx
    p = price['price'] * fx if price and fx else None
    res['fcf0'] = sum(fps[-3:]) / 3 if len(fps) >= 3 else None
    res['net_cash_ps'] = -last['net_debt'] / last['diluted_shares'] if last['diluted_shares'] and last['net_debt'] is not None else None
    res['implied_growth'] = None
    if p and res['fcf0'] and res['fcf0'] > 0 and res['net_cash_ps'] is not None:
        try:
            res['implied_growth'] = reverse_dcf(p, res['fcf0'], R_BASE, G_T_BASE, res['net_cash_ps'])
        except ValueError:
            flags.append('implied growth outside -50%..100%')
    res['pe'] = p / last['eps_diluted'] if p and last['eps_diluted'] and last['eps_diluted'] > 0 else None
    res['fcf_yield'] = res['fcf0'] / p if p and res['fcf0'] is not None else None
    if last['eps_diluted'] and last['net_income'] and last['diluted_shares']:
        gap = abs(last['eps_diluted'] * last['diluted_shares'] / last['net_income'] - 1)
        if gap > 0.05:
            flags.append(f'EPS x shares differs {gap:.0%} from net profit (check share classes or units)')
    if rows[-1].get('debt_adjusted'):
        ours, theirs = rows[-1]['debt_adjusted']
        flags.append(f'latest debt: filing tags give {ours / 1e6:,.0f}m, the second source {theirs / 1e6:,.0f}m; '
                     'the larger is used (check the annual report)')
    for metric, ours, theirs in second_source:
        if metric == 'debt':
            continue  # handled above
        flags.append(f'latest {metric} differs more than 10% from a second source ({ours / 1e6:,.0f}m vs {theirs / 1e6:,.0f}m)')
    # filters (None = not enough data, counts as not passed)
    tests = {
        'q_roic': (res['roic_median'], lambda v: v >= 0.15),
        'q_roic_min': (res['roic_min'], lambda v: v >= 0.10),
        'q_cash_conversion': (res['fcf_to_net_income'], lambda v: v >= 0.80),
        'q_debt': (res['net_debt_m'], lambda v: v <= 0 or (res['net_debt_to_fcf'] is not None and res['net_debt_to_fcf'] <= 3)),
        'q_margins': (res['margin_min'], lambda v: v >= res['margin_median'] - 0.05),
        'q_dilution': (res['shares_change'], lambda v: v <= 0.01),
        'g_revenue': (res['revenue_growth'], lambda v: v >= 0.05),
        'g_fcf_ps': (res['fcf_ps_growth'], lambda v: v >= 0.05),
        'g_still_growing': (res['revenue_growth_3y'], lambda v: v > 0),
        'g_price': (res['implied_growth'], lambda v: res['fcf_ps_growth'] is not None and v <= res['fcf_ps_growth']),
    }
    for name, (v, ok) in tests.items():
        res[name] = 'n/a' if v is None else ('pass' if ok(v) else 'fail')
    res['quality_passed'] = sum(res[n] == 'pass' for n in tests if n.startswith('q_'))
    res['garp_passed'] = sum(res[n] == 'pass' for n in tests if n.startswith('g_'))
    res['passed'] = res['quality_passed'] + res['garp_passed']
    res['data_flags'] = '; '.join(flags)
    return res


def fx_rate(price_currency, report_currency, fx):
    """Multiply a price by this to get it in the reporting currency (pence-quoted London prices: GBp -> GBP first)."""
    pc = 'GBP' if price_currency in ('GBp', 'GBX') else price_currency
    scale = 0.01 if price_currency in ('GBp', 'GBX') else 1.0
    return scale * fx[pc][report_currency] if pc != report_currency else scale


def prepare(region):
    """Every screenable company of a region: {ticker: {meta, rows, price, rate, disagree}}, with the same
    debt rules the screen uses. Companies with fewer than MIN_YEARS years are left out."""
    figs = {}
    for r in csv.DictReader(open(f'{BASE}/output/figures_{region}.csv')):
        figs.setdefault(r['ticker'], []).append(r)
    prices = {r['ticker']: {**r, 'price': float(r['price'])} for r in csv.DictReader(open(f'{BASE}/raw/prices_{region}.csv'))}
    fx = json.load(open(f'{BASE}/raw/fx.json')) if os.path.exists(f'{BASE}/raw/fx.json') else {}
    # A company with no debt tags at all is either debt-free or tags debt under its own names. Only when the
    # second source (Yahoo, crosscheck_yahoo.py cache) shows no borrowings in every year it has is it taken as zero.
    yahoo = json.load(open(f'{BASE}/raw/yahoo_statements_{region}.json')) if os.path.exists(f'{BASE}/raw/yahoo_statements_{region}.json') else {}

    def debt_free(t):
        y = yahoo.get(t, {})
        d, lease = y.get('debt', {}), y.get('lease', {})
        return bool(d) and all(v - lease.get(k, 0) <= 0.005 * max(v, 1) for k, v in d.items())
    for t, rows in figs.items():
        if debt_free(t):
            for r in rows:
                if r['debt_found'] == 'no':
                    r['debt_free_confirmed'] = True
    # crosscheck_yahoo.py output, when it has been run: disagreements become data flags
    cross = {}
    if os.path.exists(f'{BASE}/output/crosscheck_{region}.csv'):
        for c in csv.DictReader(open(f'{BASE}/output/crosscheck_{region}.csv')):
            cross.setdefault(c['ticker'], []).append(c)
    # Debt is the one figure the filing tags often get wrong: companies file current loans under their own
    # names (Ahold), or include leases (Shell). The European spot-check found 3 of 8 debt figures off. Where the
    # filing tags and the second source disagree by more than 10%, or the tags have no debt at all, the LARGER
    # of the two is used and flagged: it can only make the debt test and the valuation stricter, never kinder.
    for t, rows in figs.items():
        debt_cross = {c['fiscal_year']: c for c in cross.get(t, []) if c['metric'] == 'debt'}
        for r in rows:
            c = debt_cross.get(r['fiscal_year'])
            if c and (c['verdict'] == 'DIFFERENT' or r['debt_found'] == 'no'):
                ours, theirs = float(r['debt'] or 0), float(c['yahoo'])
                r['debt'], r['debt_found'] = max(ours, theirs, 0.0), 'yes'
                if r['debt'] != ours:
                    r['debt_adjusted'] = (ours, theirs)
    out = {}
    for t, rows in figs.items():
        rows.sort(key=lambda r: int(r['fiscal_year']))
        # a company that changed its reporting currency (CRH: EUR to USD) is judged on the latest currency's years
        rows = [r for r in rows if r['currency'] == rows[-1]['currency']]
        if len(rows) < MIN_YEARS:
            continue
        meta = {'name': rows[0]['name'], 'sector': rows[0]['sector'], 'report_currency': rows[-1]['currency']}
        pr = prices.get(t)
        rate = fx_rate(pr['currency'], meta['report_currency'], fx) if pr else 1.0
        last_fy = rows[-1]['fiscal_year']
        disagree = [(c['metric'], float(c['ours']), float(c['yahoo'])) for c in cross.get(t, [])
                    if c['fiscal_year'] == last_fy and c['verdict'] == 'DIFFERENT']
        out[t] = {'meta': meta, 'rows': rows, 'price': pr, 'rate': rate, 'disagree': disagree}
    return out


def main():
    region = sys.argv[1]
    prepared = prepare(region)
    out = [screen(t, c['meta'], c['rows'], c['price'], c['rate'], c['disagree']) for t, c in prepared.items() if c['price']]
    out = [o for o in out if o]
    out.sort(key=lambda o: (-o['passed'], -(o['quality_passed']), o['implied_growth'] if o['implied_growth'] is not None else 9))
    with open(f'{BASE}/output/screen_{region}.csv', 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    from collections import Counter
    print(f'{len(out)} companies screened')
    print('passed (of 10):', sorted(Counter(o['passed'] for o in out).items(), reverse=True))
    print('all 6 quality:', sum(o['quality_passed'] == 6 for o in out), '| all 10:', sum(o['passed'] == 10 for o in out))
    print('with data flags:', sum(bool(o['data_flags']) for o in out))


if __name__ == '__main__':
    main()

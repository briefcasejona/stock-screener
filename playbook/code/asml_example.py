"""ASML worked example for the playbook: history, reverse DCF, bear/base/bull DCF and P/E check.

Inputs (nothing typed by hand except the scenario choices):
  ../data-check/output/free_source_figures.csv   annual figures from SEC EDGAR, checked in step 1
  ../data-check/reference/annual_report_values.csv  only for 2016 operating cash flow (missing in SEC data)
  ../data-check/raw/companyfacts_0000937966.json   purchases of intangible assets, debt, short-term investments
  sources/asml_q3_2026_statements.txt   ASML's Q3 2026 US GAAP statements (pdftotext -layout of the PDF)
  raw/ASML.AS_daily.csv                  Euronext Amsterdam prices in EUR from Yahoo (unadjusted close)
Output: output/asml_example.json, plus a printed walk-through.
Run: python3 -I code/asml_example.py   (from the playbook folder)
"""
import csv
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from valuation import cagr, dcf, reverse_dcf  # noqa: E402

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECK = os.path.join(os.path.dirname(BASE), 'data-check')
M = 1e6

# Playbook step 3: discount rate and long-term growth per scenario, plus the growth for years 1-10.
# The growth rates are this example's judgement, explained in the playbook text.
SCENARIOS = {
    'bear': {'g': 0.06, 'r': 0.10, 'g_t': 0.02},
    'base': {'g': 0.12, 'r': 0.09, 'g_t': 0.025},
    'bull': {'g': 0.19, 'r': 0.08, 'g_t': 0.03},  # revenue growth 2016-2025 (18.9%) continues
}


def annual():
    """{metric: {year: value in EUR (per share for EPS)}} using the latest reported values."""
    out = {}
    for r in csv.DictReader(open(f'{CHECK}/output/free_source_figures.csv')):
        if r['company'] == 'ASML' and r['latest']:
            out.setdefault(r['metric'], {})[int(r['fiscal_year'])] = float(r['latest'])
    for r in csv.DictReader(open(f'{CHECK}/reference/annual_report_values.csv')):
        if r['company'] == 'ASML' and r['metric'] == 'operating_cash_flow' and r['fiscal_year'] == '2016':
            out['operating_cash_flow'][2016] = float(r['report_value']) * M
    facts = json.load(open(f'{CHECK}/raw/companyfacts_0000937966.json'))['facts']['us-gaap']
    out['capex_intangibles'] = {}
    for a in facts['PaymentsToAcquireIntangibleAssets']['units']['EUR']:
        y = int(a['end'][:4])
        if a.get('form') == '20-F' and a['start'][5:] == '01-01' and a['end'][5:] == '12-31' \
                and int(a['fy']) == y:  # the value as filed for that year
            out['capex_intangibles'][y] = float(a['val'])
    return out


def sec_series(key, instant):
    """Yearly values 2016-2025 for one SEC tag, taking the latest 20-F that reports each year (EUR)."""
    facts = json.load(open(f'{CHECK}/raw/companyfacts_0000937966.json'))['facts']['us-gaap']
    out = {}
    for x in facts.get(key, {}).get('units', {}).get('EUR', []):
        full_year = 'start' not in x if instant else x.get('start', '')[5:] == '01-01'
        if x.get('form') == '20-F' and x['end'][5:] == '12-31' and full_year:
            y = int(x['end'][:4])
            if 2016 <= y <= 2025 and (y not in out or x['filed'] > out[y][1]):
                out[y] = (float(x['val']), x['filed'])
    return {y: v for y, (v, _) in out.items()}


def quality(a, fcf):
    """Playbook step 1 filters for 2016-2025."""
    gross = sec_series('GrossProfit', False)
    tax = sec_series('IncomeTaxExpenseBenefit', False)
    pretax = sec_series('IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments', False)
    debt_long = sec_series('LongTermDebtAndCapitalLeaseObligations', True)
    cur1, cur2 = sec_series('LongTermDebtCurrent', True), sec_series('LongTermDebtAndCapitalLeaseObligationsCurrent', True)
    sti = sec_series('AvailableForSaleSecuritiesDebtSecuritiesCurrent', True)
    sti[2016] = 1150.0 * M  # 20-F FY2016 balance sheet; 2017 is not tagged, so left out (understates 2017 ROIC)
    rows = []
    for y in range(2016, 2026):
        debt = debt_long[y] + max(cur1.get(y, 0.0), cur2.get(y, 0.0))
        net_debt = debt - a['cash'][y] - sti.get(y, 0.0)
        nopat = a['operating_income'][y] * (1 - tax[y] / pretax[y])
        rows.append({'year': y, 'roic': nopat / (a['equity_to_shareholders'][y] + net_debt),
                     'gross_margin': gross[y] / a['revenue'][y], 'net_debt_m': net_debt / M})
    roics = sorted(r['roic'] for r in rows)
    gms = sorted(r['gross_margin'] for r in rows)
    return {
        'rows': rows,
        'roic_median': (roics[4] + roics[5]) / 2, 'roic_min': roics[0],
        'fcf_to_net_income': sum(fcf.values()) / sum(a['net_income_to_shareholders'][y] for y in range(2016, 2026)),
        'net_debt_to_fcf_2025': rows[-1]['net_debt_m'] * M / fcf[2025],
        'gross_margin_median': (gms[4] + gms[5]) / 2, 'gross_margin_min': gms[0],
        'shares_change_per_year': cagr(a['diluted_shares'][2016], a['diluted_shares'][2025], 9),
    }


def quarterly():
    """Last five quarters (Q3 2025 .. Q3 2026) from the quarterly pages of the Q3 2026 statements."""
    text = open(f'{BASE}/sources/asml_q3_2026_statements.txt').read()
    heading = lambda title: re.search(r'^[ \t]*' + title + r'[ \t]*$', text, re.M).start()  # page title, not contents
    start_q = heading('Quarterly Summary US GAAP Consolidated Statements of Operations')
    summary, quarterly_part = text[heading('Summary US GAAP Consolidated Statements of Operations'):start_q], text[start_q:]
    num = r'(?:\(?-?[\d,]+\.\d+\)?|—)'  # '—' means zero

    def row(label, part=quarterly_part, n=5):
        m = re.search(re.escape(label) + r'[ \t]+((?:' + num + r'[ \t]+){%d}' % (n - 1) + num + ')', part)
        if not m:
            raise ValueError(f'row not found: {label}')
        vals = re.findall(num, m.group(1))
        return [0.0 if v == '—' else -float(v.strip('()').replace(',', '')) if v.startswith('(')
                else float(v.replace(',', '')) for v in vals]

    q = {
        'revenue': row('Total net sales'),
        'net_income': row('Net income'),
        'eps_diluted': row('Diluted net income per ordinary share'),
        'diluted_shares_m': row('Diluted'),
        'operating_cash_flow': row('operating activities'),
        'capex_ppe': [-v for v in row('equipment')],
        'capex_intangibles': [-v for v in row('Purchase of intangible assets')],
        'gain_equity_investments': row('Gain (loss) on equity investments'),
        'cash': row('Cash and cash equivalents'),
        'short_term_investments': row('Short-term investments'),
        'long_term_debt': row('Long-term debt'),
        'contract_liabilities': row('Contract liabilities'),
    }
    # self-check: the nine-month totals on the summary page must equal the sum of the 2026 quarters
    # (columns there: Q3 2025, Q3 2026, 9M 2025, 9M 2026)
    for key, label in (('revenue', 'Total net sales'), ('net_income', 'Net income'),
                       ('gain_equity_investments', 'Gain (loss) on equity investments')):
        nine = row(label, summary, 4)[3]
        assert abs(sum(q[key][2:]) - nine) < 0.15, f'quarterly parse mismatch: {key}'
    return q


def main():
    a, q = annual(), quarterly()
    prices = {}
    for r in csv.DictReader(open(f'{BASE}/raw/ASML.AS_daily.csv')):
        prices[r['Date'][:10]] = float(r['Close'])
    price_date = max(prices)
    price = prices[price_date]
    year_end_price = {y: prices[max(d for d in prices if d.startswith(str(y)))] for y in range(2016, 2026)}

    years = range(2016, 2026)
    fcf = {y: a['operating_cash_flow'][y] - a['capex_ppe'][y] - a['capex_intangibles'][y] for y in years}
    fcf_ps = {y: fcf[y] / a['diluted_shares'][y] for y in years}
    history = [{
        'year': y,
        'revenue_m': a['revenue'][y] / M,
        'operating_margin': a['operating_income'][y] / a['revenue'][y],
        'net_income_m': a['net_income_to_shareholders'][y] / M,
        'eps_diluted': a['eps_diluted'][y],
        'fcf_m': fcf[y] / M,
        'fcf_per_share': fcf_ps[y],
        'fcf_to_net_income': fcf[y] / a['net_income_to_shareholders'][y],
        'year_end_price': year_end_price[y],
        'pe_year_end': year_end_price[y] / a['eps_diluted'][y],
    } for y in years]

    # growth delivered: 3-year averages around 2017 and 2024, 7 years apart, smooth out the lumpy cash flows
    avg = lambda d, ys: sum(d[y] for y in ys) / len(ys)
    growth = {
        'revenue_cagr_2016_2025': cagr(a['revenue'][2016], a['revenue'][2025], 9),
        'eps_cagr_2016_2025': cagr(a['eps_diluted'][2016], a['eps_diluted'][2025], 9),
        'fcf_ps_cagr_3yavg_2017_to_2024': cagr(avg(fcf_ps, (2016, 2017, 2018)), avg(fcf_ps, (2023, 2024, 2025)), 7),
        'shares_change_per_year_2016_2025': cagr(a['diluted_shares'][2016], a['diluted_shares'][2025], 9),
    }

    # latest twelve months = Q4 2025 .. Q3 2026
    ltm = {k: sum(v[1:]) for k, v in q.items() if k not in ('cash', 'short_term_investments', 'long_term_debt',
                                                              'contract_liabilities', 'diluted_shares_m')}
    shares_now = q['diluted_shares_m'][-1] * M
    ltm['fcf'] = ltm['operating_cash_flow'] - ltm['capex_ppe'] - ltm['capex_intangibles']

    # net cash at 27 Sep 2026. The quarterly balance sheet shows long-term debt only; the current part is the
    # year-end 2025 total debt minus the 2026 repayments minus the long-term part (no new borrowing in 2026).
    facts = json.load(open(f'{CHECK}/raw/companyfacts_0000937966.json'))['facts']['us-gaap']
    ye = lambda k: next(x['val'] for x in facts[k]['units']['EUR'] if x['end'] == '2025-12-31' and x.get('fy') == 2025)
    debt_ye2025 = ye('LongTermDebtCurrent') + ye('LongTermDebtNoncurrent')
    repaid_2026 = 692.9 + 0.3 + 1000.4  # 'Repayment of debt' Q1-Q3 2026, quarterly cash flow page
    assert abs(q['long_term_debt'][1] * M - ye('LongTermDebtNoncurrent')) < 0.1 * M
    debt_now = debt_ye2025 - repaid_2026 * M
    cash_now = (q['cash'][-1] + q['short_term_investments'][-1]) * M
    net_cash_ps = (cash_now - debt_now) / shares_now

    # starting FCF. ASML is cyclical (special cases section): normalised FCF = average FCF margin
    # 2016-2025 x revenue of the latest twelve months, per diluted share of the latest quarter
    fcf_margin = sum(fcf.values()) / sum(a['revenue'][y] for y in years)
    fcf0 = fcf_margin * ltm['revenue'] * M / shares_now
    implied = reverse_dcf(price, fcf0, 0.09, 0.025, net_cash_ps)
    scen = {name: dcf(fcf0, net_cash=net_cash_ps, **p) | p for name, p in SCENARIOS.items()}
    # what the implied growth means: revenue in year 10 at the same FCF margin and share count
    implied_revenue_y10 = fcf0 * (1 + implied) ** 10 * shares_now / fcf_margin

    # for comparison, the ordinary rule (average FCF per share 2023-2025) lags a fast grower
    fcf0_alt = avg(fcf_ps, (2023, 2024, 2025))
    implied_alt = reverse_dcf(price, fcf0_alt, 0.09, 0.025, net_cash_ps)
    peers = json.load(open(f'{BASE}/raw/peer_pe_yahoo.json'))

    qual = quality(a, fcf)
    pe_hist = sorted(h['pe_year_end'] for h in history)
    result = {
        'price': price, 'price_date': price_date, 'history': history, 'growth': growth, 'quality': qual,
        'ltm': {k: v for k, v in ltm.items()}, 'ltm_eps': ltm['eps_diluted'],
        'pe_ltm': price / ltm['eps_diluted'], 'pe_fy2025': price / a['eps_diluted'][2025],
        'pe_median_2016_2025': (pe_hist[4] + pe_hist[5]) / 2, 'pe_min': pe_hist[0], 'pe_max': pe_hist[-1],
        'shares_now': shares_now, 'cash_now': cash_now, 'debt_now': debt_now, 'net_cash_ps': net_cash_ps,
        'contract_liabilities': {'2026Q2': q['contract_liabilities'][3] * M, '2026Q3': q['contract_liabilities'][4] * M},
        'fcf0': fcf0, 'implied_growth': implied, 'scenarios': scen,
        'fcf_margin_2016_2025': fcf_margin, 'implied_revenue_y10': implied_revenue_y10,
        'peers_trailing_pe_yahoo_unchecked': {t: v['trailingPE'] for t, v in peers.items()},
        'fair_pe_base_on_ltm_eps': scen['base']['value'] / ltm['eps_diluted'], 'fcf0_alt': fcf0_alt, 'implied_growth_alt': implied_alt,
        'scenarios_alt': {n: dcf(fcf0_alt, net_cash=net_cash_ps, **p)['value'] for n, p in SCENARIOS.items()},
        'buy_below': scen['bear']['value'],
    }
    os.makedirs(f'{BASE}/output', exist_ok=True)
    json.dump(result, open(f'{BASE}/output/asml_example.json', 'w'), indent=1)

    print(f'Price {price:.2f} EUR on {price_date}')
    print('year  revenue  op.margin  EPS    FCF/sh  FCF/NI  YE price  P/E')
    for h in history:
        print(f"{h['year']}  {h['revenue_m']:8.0f}  {h['operating_margin']:6.1%}  {h['eps_diluted']:5.2f}  "
              f"{h['fcf_per_share']:6.2f}  {h['fcf_to_net_income']:5.0%}  {h['year_end_price']:8.2f}  {h['pe_year_end']:5.1f}")
    print({k: f'{v:.1%}' for k, v in growth.items()})
    print('ROIC', ' '.join(f"{r['year']}:{r['roic']:.0%}" for r in qual['rows']))
    print('gross margin', ' '.join(f"{r['year']}:{r['gross_margin']:.1%}" for r in qual['rows']))
    print('net debt', ' '.join(f"{r['year']}:{r['net_debt_m']:.0f}" for r in qual['rows']))
    print({k: round(v, 3) for k, v in qual.items() if k != 'rows'})
    print(f"LTM revenue {ltm['revenue']:.0f}m, net income {ltm['net_income']:.0f}m, EPS {ltm['eps_diluted']:.2f}, "
          f"OCF {ltm['operating_cash_flow']:.0f}m, FCF {ltm['fcf']:.0f}m, one-off gain {ltm['gain_equity_investments']:.0f}m")
    print(f"P/E LTM {result['pe_ltm']:.1f}, FY2025 {result['pe_fy2025']:.1f}, median {result['pe_median_2016_2025']:.1f} "
          f"(range {pe_hist[0]:.1f}-{pe_hist[-1]:.1f})")
    print(f'cash {cash_now/M:.0f}m, debt {debt_now/M:.0f}m, shares {shares_now/M:.1f}m, net cash/share {net_cash_ps:.2f}')
    print(f"contract liabilities Q2 {q['contract_liabilities'][3]:.0f}m -> Q3 {q['contract_liabilities'][4]:.0f}m")
    print(f'FCF margin 2016-25 {fcf_margin:.1%}; FCF0 normalised {fcf0:.2f}; implied growth {implied:.1%}; '
          f'implied revenue year 10 {implied_revenue_y10/1e9:.0f}bn')
    for n, s in scen.items():
        print(f"  {n}: g {s['g']:.0%} r {s['r']:.0%} gT {s['g_t']:.1%} -> value {s['value']:.0f}, "
              f"after year 10 {s['terminal_share']:.0%}, FCF y10 {s['fcf_year10']:.0f}")
    print(f"fair P/E base {result['fair_pe_base_on_ltm_eps']:.1f}; peers {result['peers_trailing_pe_yahoo_unchecked']}")
    print(f"alt FCF0 (avg FCF/share 2023-25) {fcf0_alt:.2f}; implied growth {implied_alt:.1%}; "
          + ', '.join(f'{n} {v:.0f}' for n, v in result['scenarios_alt'].items()))


if __name__ == '__main__':
    main()

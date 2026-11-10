"""Turn the worked-example results into the dashboard's data files (one JSON file per dataset).

Input:  output/asml_example.json (from asml_example.py), journal/journal.json (decision journal),
        journal/watchlist.json and journal/analyses/<ticker>.json (watchlist.py: every other analysed company)
Output: dashboard/candidates.json, scenarios.json, checks.json, history.json, journal.json
Run: python3 -I code/build_dashboard_data.py   (from the playbook folder)
"""
import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(BASE), 'screener', 'code'))
import localdata  # noqa: E402

JOURNAL_DIR = localdata.JOURNAL_DIR
OUT = f'{BASE}/dashboard'
r1 = lambda x: round(x, 1)
r2 = lambda x: round(x, 2)
r4 = lambda x: round(x, 4)


def build():
    """The five datasets as lists of rows (the laptop program reads these directly)."""
    a = json.load(open(f'{BASE}/output/asml_example.json'))
    q, g, s = a['quality'], a['growth'], a['scenarios']
    company = 'ASML'
    hist = {h['year']: h for h in a['history']}
    revenue_3y = (hist[2025]['revenue_m'] / hist[2022]['revenue_m']) ** (1 / 3) - 1
    roic_low = min(q['rows'], key=lambda r: r['roic'])
    gm_low = min(q['rows'], key=lambda r: r['gross_margin'])
    gm_gap = (q['gross_margin_median'] - q['gross_margin_min']) * 100
    net_cash_2025 = -q['rows'][-1]['net_debt_m'] / 1000

    checks = [
        ('Quality', 'ROIC', f"Median {q['roic_median']:.0%}", 'Median ≥ 15%', q['roic_median'] >= 0.15),
        ('Quality', 'ROIC consistency', f"Lowest {roic_low['roic']:.0%} ({roic_low['year']})", '≥ 10% every year',
         q['roic_min'] >= 0.10),
        ('Quality', 'Profits turn into cash', f"FCF {q['fcf_to_net_income']:.0%} of net profit", '≥ 80%',
         q['fcf_to_net_income'] >= 0.80),
        ('Quality', 'Debt you can carry', f'Net cash €{net_cash_2025:.1f}bn (end 2025)', '≤ 3 years of FCF',
         q['net_debt_to_fcf_2025'] <= 3),
        ('Quality', 'Margins hold', f"Gross margin low {gm_low['gross_margin']:.1%} ({gm_low['year']}), "
         f"median {q['gross_margin_median']:.1%}", '≤ 5 points below median', gm_gap <= 5),
        ('Quality', 'No dilution', f"Shares {q['shares_change_per_year']:+.1%} a year", '≤ +1% a year',
         q['shares_change_per_year'] <= 0.01),
        ('GARP', 'Growing revenue', f"{g['revenue_cagr_2016_2025']:.1%} a year (2016–2025)", '≥ 5%',
         g['revenue_cagr_2016_2025'] >= 0.05),
        ('GARP', 'Growing cash per share', f"{g['fcf_ps_cagr_3yavg_2017_to_2024']:.1%} a year", '≥ 5%',
         g['fcf_ps_cagr_3yavg_2017_to_2024'] >= 0.05),
        ('GARP', 'Still growing', f'{revenue_3y:.1%} a year (2022–2025)', 'Above zero', revenue_3y > 0),
        ('GARP', 'Reasonable price', f"Implied {a['implied_growth']:.1%} vs delivered "
         f"{g['fcf_ps_cagr_3yavg_2017_to_2024']:.1%}", 'Implied ≤ delivered',
         a['implied_growth'] <= g['fcf_ps_cagr_3yavg_2017_to_2024']),
    ]
    checks = [{'company': company, 'step': st, 'filter': f, 'value': v, 'threshold': t,
               'result': 'Pass' if ok else 'Fail'} for st, f, v, t, ok in checks]
    passed = lambda step: sum(c['result'] == 'Pass' for c in checks if c['step'] == step)
    total = lambda step: sum(c['step'] == step for c in checks)

    candidates = [{
        'company': company, 'ticker': 'ASML.AS', 'exchange': 'Euronext Amsterdam', 'currency': 'EUR',
        'price': r2(a['price']), 'price_date': a['price_date'],
        'bear': r1(s['bear']['value']), 'base': r1(s['base']['value']), 'bull': r1(s['bull']['value']),
        # buy-below = base value minus the default 30% margin of safety (19 Oct 2026; it used to be the bear value)
        'buy_below': r1(s['base']['value'] * 0.7), 'price_to_buy_below': r2(a['price'] / (s['base']['value'] * 0.7)),
        'implied_growth': r4(a['implied_growth']), 'delivered_growth': r4(g['fcf_ps_cagr_3yavg_2017_to_2024']),
        'pe_ltm': r1(a['pe_ltm']), 'pe_median_10y': r1(a['pe_median_2016_2025']),
        'pe_min_10y': r1(a['pe_min']), 'pe_max_10y': r1(a['pe_max']),
        'fcf0': r2(a['fcf0']), 'net_cash_per_share': r2(a['net_cash_ps']),
        'quality_passed': passed('Quality'), 'quality_total': total('Quality'),
        'garp_passed': passed('GARP'), 'garp_total': total('GARP'),
        'decision': 'Buy' if a['price'] <= s['base']['value'] * 0.7 else 'Wait',
        'next_check': 'Full-year 2026 results, late January 2027',
        'pe_basis': 'P/E, latest 12 months', 'follow': 'One-time', 'analysed': a['price_date'], 'region': 'Europe',
        'figures_to': '2026-09-27', 'fcf_basis': 'normalised (cyclical: average margin x latest 12 months revenue)',
        'assumptions_source': 'set by hand in the worked example', 'notes': '',
    }]
    scenarios = [{'company': company, 'scenario': name.capitalize(), 'growth': v['g'], 'discount_rate': v['r'],
                  'long_term_growth': v['g_t'], 'value': r1(v['value']), 'after_year_10': r4(v['terminal_share'])}
                 for name, v in s.items()]
    roic = {r['year']: r for r in q['rows']}
    history = [{'company': company, 'year': h['year'], 'revenue_m': r1(h['revenue_m']),
                'fcf_per_share': r2(h['fcf_per_share']), 'eps': r2(h['eps_diluted']),
                'year_end_price': r2(h['year_end_price']), 'pe_year_end': r1(h['pe_year_end']),
                'roic': r4(roic[h['year']]['roic']), 'gross_margin': r4(roic[h['year']]['gross_margin'])}
               for h in a['history']]
    journal = json.load(open(f'{JOURNAL_DIR}/journal.json'))

    # every company on the watchlist or analysed once (watchlist.py); its own analysis replaces the worked example
    wl_path = f'{JOURNAL_DIR}/watchlist.json'
    for e in json.load(open(wl_path)) if os.path.exists(wl_path) else []:
        path = f"{JOURNAL_DIR}/analyses/{e['ticker']}.json"
        if e.get('worked_example'):
            for row in candidates:
                if row['ticker'] == e['ticker']:
                    row['follow'] = 'Watching' if e['mode'] == 'watch' else 'One-time'
            continue
        if not os.path.exists(path):
            continue
        an = json.load(open(path))
        names = {an['candidate']['company']} | {r['company'] for r in candidates if r['ticker'] == e['ticker']}
        drop = lambda rows: [r for r in rows if r['company'] not in names]
        candidates, scenarios, checks, history = drop(candidates), drop(scenarios), drop(checks), drop(history)
        candidates.append(an['candidate'])
        scenarios += an['scenarios']
        checks += an['checks']
        history += an['history']

    return {'candidates': candidates, 'scenarios': scenarios, 'checks': checks, 'history': history, 'journal': journal}


def main():
    os.makedirs(OUT, exist_ok=True)
    for name, rows in build().items():
        json.dump(rows, open(f'{OUT}/{name}.json', 'w'), ensure_ascii=False, indent=1)
        print(name, len(rows), 'rows')


if __name__ == '__main__':
    main()

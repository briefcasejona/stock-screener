"""Standard analysis of one company from the screener's figures: the 10 checks, reverse DCF, bear/base/bull DCF
and P/E history, in the same shape as the ASML worked example so the dashboard shows it the same way.

Differences from the worked example, on purpose (they keep it mechanical, so it can re-run by itself):
- starting free cash flow is the average FCF per share of the last 3 years ('average'), or for cyclicals the
  average FCF margin times the latest revenue ('normalised', the playbook's special case);
- P/E is on the latest full year, not the latest 12 months;
- history in another currency than the share price uses today's exchange rate for every year.
The scenario growth rates are judgement. Unless they are given, a starting rule sets them from the growth the
company delivered (default_assumptions), and the result says so. A price at or below buy-below then reads
'Deep dive', not 'Buy': the playbook buys only after reading the annual report and setting the growth rates by hand.
Discount rates and long-term growth are the playbook's (10/2%, 9/2.5%, 8/3%).

Run: python3 -I code/analyse.py ADBE   (prints the result; watchlist.py saves it)
"""
import json
import os
import statistics
import sys
from datetime import date, timedelta

CODE = os.path.dirname(os.path.abspath(__file__))
PLAYBOOK = os.path.dirname(CODE)
SCREENER = os.path.join(os.path.dirname(PLAYBOOK), 'screener')
sys.path.insert(0, CODE)
sys.path.insert(0, os.path.join(SCREENER, 'code'))
from valuation import dcf, reverse_dcf  # noqa: E402
import screen as scr  # noqa: E402
from build_screen_data import display_names  # noqa: E402
from refresh_company import find  # noqa: E402

RATES = {'bear': (0.10, 0.02), 'base': (0.09, 0.025), 'bull': (0.08, 0.03)}  # discount rate, long-term growth
EXCHANGES = {'NMS': 'Nasdaq', 'NGM': 'Nasdaq', 'NCM': 'Nasdaq', 'NYQ': 'NYSE', 'ASE': 'NYSE American', 'BTS': 'Cboe',
             'AMS': 'Euronext Amsterdam', 'PAR': 'Euronext Paris', 'BRU': 'Euronext Brussels', 'LIS': 'Euronext Lisbon',
             'ISE': 'Euronext Dublin', 'OSL': 'Oslo Børs', 'MIL': 'Borsa Italiana', 'MCE': 'Bolsa de Madrid',
             'LSE': 'London Stock Exchange', 'GER': 'Xetra', 'FRA': 'Frankfurt', 'EBS': 'SIX Swiss Exchange',
             'STO': 'Nasdaq Stockholm', 'CPH': 'Nasdaq Copenhagen', 'HEL': 'Nasdaq Helsinki', 'VIE': 'Vienna',
             'WSE': 'Warsaw', 'ATH': 'Athens'}
r1 = lambda x: None if x is None else round(x, 1)
r2 = lambda x: None if x is None else round(x, 2)
r4 = lambda x: None if x is None else round(x, 4)


def default_assumptions(delivered, recent_revenue):
    """Starting rule: base = the lower of delivered FCF/share growth and the last 3 years' revenue growth, kept between
    2% and 12%; bear = half of base; bull = the delivered growth (at least 1.5 x base), at most 20%. On ASML this gives
    12% / 6% / 20%, close to the worked example's judgement (12% / 6% / 19%)."""
    known = [g for g in (delivered, recent_revenue) if g is not None]
    base = min(max(min(known) if known else 0.02, 0.02), 0.12)
    base = round(base * 200) / 200  # nearest 0.5%
    bull = min(max(delivered if delivered is not None else 0, base * 1.5), 0.20)
    return {'bear': round(base / 2, 4), 'base': base, 'bull': round(bull, 4),
            'source': 'starting rule from delivered growth (not yet reviewed)'}


def market(symbol, price_currency, report_currency):
    """Yahoo: daily closes (12 years), exchange name, and today's rate from the price currency to the report currency."""
    import yfinance as yf
    tk = yf.Ticker(symbol)
    h = tk.history(period='12y', interval='1d', auto_adjust=False).dropna(subset=['Close'])
    closes = {str(d.date()): float(v) for d, v in h['Close'].items()}
    try:
        exchange = EXCHANGES.get(tk.fast_info['exchange'], tk.fast_info['exchange'])
    except Exception:
        exchange = ''
    fx = {}
    pc = 'GBP' if price_currency in ('GBp', 'GBX') else price_currency
    if pc != report_currency:
        f = yf.Ticker(f'{pc}{report_currency}=X').history(period='5d', interval='1d').dropna(subset=['Close'])
        fx = {pc: {report_currency: float(f['Close'].iloc[-1])}}
    return closes, exchange, fx


def close_on(closes, day):
    """Last close on or before a date."""
    ds = [d for d in closes if d <= day]
    return closes[max(ds)] if ds else None


def check_rows(company, res):
    pct = lambda v: 'n/a' if v is None else f'{v:.1%}'
    gpct = lambda v: 'n/a' if v is None else f'{v:+.1%}'.replace('-', '−')  # growth, with its sign
    f1 = lambda v: 'n/a' if v is None else f'{v:.1f}'
    debt = ('Debt not found' if res['net_debt_m'] is None else 'Net cash' if res['net_debt_m'] <= 0
            else f"Net debt {f1(res['net_debt_to_fcf'])} years of FCF")
    kind = 'Operating' if res['margin_kind'] == 'operating' else 'Gross'
    rows = [
        ('Quality', 'ROIC', f"Median {pct(res['roic_median'])}", 'Median ≥ 15%', 'q_roic'),
        ('Quality', 'ROIC consistency', f"Lowest {pct(res['roic_min'])}", '≥ 10% every year', 'q_roic_min'),
        ('Quality', 'Profits turn into cash', 'FCF n/a of net profit' if res['fcf_to_net_income'] is None
         else f"FCF {res['fcf_to_net_income']:.0%} of net profit", '≥ 80%', 'q_cash_conversion'),
        ('Quality', 'Debt you can carry', debt, '≤ 3 years of FCF', 'q_debt'),
        ('Quality', 'Margins hold', f"{kind} margin low {pct(res['margin_min'])}, median {pct(res['margin_median'])}",
         '≤ 5 points below median', 'q_margins'),
        ('Quality', 'No dilution', 'n/a' if res['shares_change'] is None else f"Shares {res['shares_change']:+.1%} a year",
         '≤ +1% a year', 'q_dilution'),
        ('GARP', 'Growing revenue', f"{gpct(res['revenue_growth'])} a year ({res['first_year']}–{res['last_year']})", '≥ 5%', 'g_revenue'),
        ('GARP', 'Growing cash per share', f"{gpct(res['fcf_ps_growth'])} a year", '≥ 5%', 'g_fcf_ps'),
        ('GARP', 'Still growing', f"{gpct(res['revenue_growth_3y'])} a year, last 3 years", 'Above zero', 'g_still_growing'),
        ('GARP', 'Reasonable price', f"Implied {gpct(res['implied_growth'])} vs delivered {gpct(res['fcf_ps_growth'])}",
         'Implied ≤ delivered', 'g_price'),
    ]
    word = {'pass': 'Pass', 'fail': 'Fail', 'n/a': 'No data'}
    return [{'company': company, 'step': st, 'filter': f, 'value': v, 'threshold': t, 'result': word[res[key]]}
            for st, f, v, t, key in rows]


def analyse(ticker, assumptions=None, fcf_basis='average', follow='Watching', analysed=None, company=None):
    region, u = find(ticker)
    c = scr.prepare(region).get(ticker)
    if not c:
        raise ValueError(f'{ticker}: fewer than {scr.MIN_YEARS} years of figures, so it cannot be analysed yet')
    meta, rows = c['meta'], c['rows']
    rc = meta['report_currency']
    first_price = c['price'] or {}
    import yfinance as yf
    fi = yf.Ticker(u['yahoo']).fast_info
    raw_ccy = fi['currency']
    closes, exchange, fx = market(u['yahoo'], raw_ccy, rc)
    price_date = max(closes)
    raw_price = closes[price_date]
    pence = raw_ccy in ('GBp', 'GBX')
    ccy = 'GBP' if pence else raw_ccy
    disp = lambda p: p / 100 if pence else p  # a price in pounds, not pence
    k = scr.fx_rate(ccy, rc, fx)  # one unit of the price currency in the report currency
    res = scr.screen(ticker, meta, rows, {'price': raw_price, 'currency': raw_ccy}, scr.fx_rate(raw_ccy, rc, fx), c['disagree'])
    ys = scr.per_year(rows)[-scr.YEARS:]
    price = disp(raw_price)
    notes = [n for n in res['data_flags'].split('; ') if n]

    # starting free cash flow per share, in the price currency
    if fcf_basis == 'normalised':
        pairs = [(y['fcf'], y['revenue']) for y in ys if y['fcf'] is not None and y['revenue']]
        margin = sum(f for f, _ in pairs) / sum(r for _, r in pairs)
        fcf0_report = margin * ys[-1]['revenue'] / ys[-1]['diluted_shares']
    else:
        fcf0_report = res['fcf0']
    if fcf0_report is None or fcf0_report <= 0:
        raise ValueError(f'{ticker}: starting free cash flow is not positive, so the DCF does not apply (playbook: special case)')
    if res['net_cash_ps'] is None:
        raise ValueError(f'{ticker}: no debt figure, so net cash per share is unknown')
    fcf0, net_cash = fcf0_report / k, res['net_cash_ps'] / k
    implied = reverse_dcf(price, fcf0, *RATES['base'], net_cash)

    a = assumptions or default_assumptions(res['fcf_ps_growth'], res['revenue_growth_3y'])
    scen = {}
    for name, (r, g_t) in RATES.items():
        scen[name] = dcf(fcf0, a[name], r, g_t, net_cash) | {'g': a[name], 'r': r, 'g_t': g_t}
    base = scen['base']['value']
    buy_below = base * 0.7

    hist = []
    for y, row in zip(ys, rows[-len(ys):]):
        p = close_on(closes, row['period_end'])
        p = disp(p) if p is not None else None
        eps = y['eps_diluted'] / k if y['eps_diluted'] is not None else None
        hist.append({'year': y['year'], 'revenue_m': r1(y['revenue'] / 1e6) if y['revenue'] else None,
                     'fcf_per_share': r2(y['fcf_ps'] / k) if y['fcf_ps'] is not None else None, 'eps': r2(eps),
                     'year_end_price': r2(p), 'pe_year_end': r1(p / eps) if p and eps and eps > 0 else None,
                     'roic': r4(y['roic']), 'gross_margin': r4(y['gross_margin'])})
    pes = [h['pe_year_end'] for h in hist if h['pe_year_end'] is not None]
    last_end = date.fromisoformat(rows[-1]['period_end'])
    expected = last_end.replace(year=last_end.year + 1) + timedelta(days=80)
    name = company or display_names().get(ticker, meta['name']).replace('|', '').strip()
    today = analysed or date.today().isoformat()
    if ccy != rc:
        notes.append(f'figures are reported in {rc}; per-share values are converted at today\'s rate')
    candidate = {
        'company': name, 'ticker': ticker, 'exchange': exchange, 'currency': ccy, 'price': r2(price), 'price_date': price_date,
        'bear': r1(scen['bear']['value']), 'base': r1(base), 'bull': r1(scen['bull']['value']),
        'buy_below': r1(buy_below), 'price_to_buy_below': r2(price / buy_below) if buy_below > 0 else None,
        'implied_growth': r4(implied), 'delivered_growth': r4(res['fcf_ps_growth']),
        'pe_ltm': r1(res['pe']), 'pe_basis': f"P/E, {res['last_year']} full year",
        'pe_median_10y': r1(statistics.median(pes)) if pes else None, 'pe_min_10y': r1(min(pes)) if pes else None,
        'pe_max_10y': r1(max(pes)) if pes else None, 'fcf0': r2(fcf0), 'net_cash_per_share': r2(net_cash),
        'quality_passed': res['quality_passed'], 'quality_total': 6, 'garp_passed': res['garp_passed'], 'garp_total': 4,
        'decision': ('Buy' if a.get('reviewed') else 'Deep dive') if price <= buy_below else 'Wait',
        'next_check': f"Annual report FY{last_end.year + 1}, around {expected.strftime('%b %Y')}",
        'follow': follow, 'analysed': today, 'figures_to': rows[-1]['period_end'], 'region': 'US' if region == 'us' else 'Europe',
        'fcf_basis': 'normalised (average margin x latest revenue)' if fcf_basis == 'normalised' else 'average of the last 3 years',
        'assumptions_source': a.get('source', 'set by hand'), 'notes': '; '.join(notes),
    }
    return {
        'ticker': ticker, 'region': region, 'candidate': candidate,
        'scenarios': [{'company': name, 'scenario': n.capitalize(), 'growth': v['g'], 'discount_rate': v['r'],
                       'long_term_growth': v['g_t'], 'value': r1(v['value']), 'after_year_10': r4(v['terminal_share'])}
                      for n, v in scen.items()],
        'checks': check_rows(name, res),
        'history': [{'company': name, **h} for h in hist],
        'assumptions': a, 'fcf_basis': fcf_basis, 'last_period_end': rows[-1]['period_end'],
        'screen_price_was': first_price.get('price'),
    }


if __name__ == '__main__':
    print(json.dumps(analyse(sys.argv[1]), indent=1, ensure_ascii=False))

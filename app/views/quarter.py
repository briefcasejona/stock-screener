"""The latest twelve months from quarterly reports, next to the last full year (screener/code/quarterly.py)."""
import pandas as pd
import streamlit as st

ROWS = [('Revenue', 'revenue'), ('Gross profit', 'gross_profit'), ('Operating profit', 'operating_income'),
        ('Net profit for shareholders', 'net_income'), ('Diluted earnings per share', 'eps_diluted'),
        ('Operating cash flow', 'operating_cash_flow'), ('Capital spending', 'capex'), ('Free cash flow', None),
        ('Cash and equivalents (at the end)', 'cash'), ('Debt (at the end)', 'debt'),
        ('Equity for shareholders (at the end)', 'equity'), ('Diluted shares', 'diluted_shares')]


def num(r, k):
    try:
        return float(r[k]) if r.get(k) not in ('', None) else None
    except (TypeError, ValueError):
        return None


def value(r, k):
    if k is None:  # free cash flow = operating cash flow - capital spending
        o, c = num(r, 'operating_cash_flow'), num(r, 'capex')
        return o - (c or 0) if o is not None else None
    return num(r, k)


def fmt(v, k, cur):
    if v is None:
        return 'n/a'
    if k == 'eps_diluted':
        return f'{cur} {v:,.2f}'.replace('-', '−')
    if k == 'diluted_shares':
        return f'{v / 1e6:,.1f} million'
    return f'{cur} {v / 1e6:,.1f}m'.replace('-', '−')


@st.cache_data(show_spinner=False, ttl=600)
def latest(ticker, _stamp):
    import quarterly
    return quarterly.for_ticker(ticker)


def show(ticker, stamp=None):
    """The table, or a line saying there is no quarter after the last full year."""
    try:
        r = latest(ticker, stamp)
    except Exception as e:
        st.caption(f'The quarterly figures could not be read ({type(e).__name__}: {e}).')
        return
    if not r:
        st.caption('No quarterly figures after the last full year. For US companies they come from the SEC with each '
                   'refresh; for others, add a quarterly report on the Add a report page.')
        return
    a, t = r['annual'], r['row']
    cur = (a.get('currency') or '').split(',')[0] or ''
    rows = []
    for label, k in ROWS:
        y, q = value(a, k), value(t, k)
        ch = f'{(q / y - 1) * 100:+.0f}%'.replace('-', '−') if y and q is not None and y > 0 and q > 0 else ''
        rows.append({'Figure': label, f"Full year to {a['period_end']}": fmt(y, k, cur),
                     f"12 months to {r['quarter_end']}": fmt(q, k, cur), 'Change': ch})
    st.dataframe(pd.DataFrame(rows), hide_index=True, height=36 * (len(rows) + 1) + 3, column_config={
        'Change': st.column_config.TextColumn(help='Only where both figures are above zero.')})
    st.caption(f"The 12 months are the last full year plus the {r['months']} months since, minus the same months a "
               f"year earlier, from {r['source']}. Quarterly figures are **unaudited**; balance-sheet figures are as at "
               f"{r['quarter_end']}. The screener and your valuation keep using full, audited years: use this to see "
               'whether the story is still on track, not to recompute the value.')
    if r['missing']:
        st.caption('Not in the quarterly figures: ' + ', '.join(r['missing']).replace('_', ' ') + '.')

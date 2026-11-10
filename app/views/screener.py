"""Screener: the 10 checks on the S&P 500 and STOXX Europe 600, and the buttons to analyse a company."""
import pandas as pd
import streamlit as st

import core
from views import data

CHECKS = [  # key, step, name, how the value reads, threshold
    ('q_roic', 'Quality', 'ROIC', lambda r: f"median {core.pct(r['roic_median'])}", 'median ≥ 15%'),
    ('q_roic_min', 'Quality', 'ROIC consistency', lambda r: f"lowest {core.pct(r['roic_min'])}", '≥ 10% every year'),
    ('q_cash_conversion', 'Quality', 'Profits turn into cash',
     lambda r: f"FCF {core.pct(r['fcf_to_net_income'], 0)} of net profit", '≥ 80%'),
    ('q_debt', 'Quality', 'Debt you can carry',
     lambda r: 'debt not found' if r['net_debt_m'] is None else 'net cash' if r['net_debt_m'] <= 0
     else f"net debt {r['net_debt_to_fcf']:.1f} years of FCF", '≤ 3 years of FCF'),
    ('q_margins', 'Quality', 'Margins hold',
     lambda r: f"{r['margin_kind']} margin low {core.pct(r['margin_min'])}, median {core.pct(r['margin_median'])}",
     '≤ 5 points below median'),
    ('q_dilution', 'Quality', 'No dilution',
     lambda r: 'n/a' if r['shares_change'] is None else f"shares {r['shares_change']:+.1%} a year", '≤ +1% a year'),
    ('g_revenue', 'GARP', 'Growing revenue',
     lambda r: f"{core.pct(r['revenue_growth'])} a year ({r['first_year']}–{r['last_year']})", '≥ 5%'),
    ('g_fcf_ps', 'GARP', 'Growing cash per share', lambda r: f"{core.pct(r['fcf_ps_growth'])} a year", '≥ 5%'),
    ('g_still_growing', 'GARP', 'Still growing', lambda r: f"{core.pct(r['revenue_growth_3y'])} a year, last 3 years",
     'above zero'),
    ('g_price', 'GARP', 'Reasonable price',
     lambda r: f"implied {core.pct(r['implied_growth'])} vs delivered {core.pct(r['fcf_ps_growth'])}", 'implied ≤ delivered'),
]
pct100 = lambda v: None if v is None else v * 100  # shown as 12.3%
RESULT = {'pass': '✅ Pass', 'fail': '❌ Fail', 'n/a': '— No data'}


def analyse_buttons(r):
    entry = next((e for e in core.watchlist() if e['ticker'] == r['ticker']), None)
    if entry:
        st.success(f"{r['company']} is already in your candidates "
                   f"({'following' if entry['mode'] == 'watch' else 'one-time analysis'}).")
        if st.button('Open it in Candidates'):
            st.session_state['focus'] = r['ticker']
            st.switch_page(st.session_state['pages']['candidates'])
        return
    st.markdown('**Analyse it:** reverse DCF, bear/base/bull values and 10 years of history. It then shows in Candidates.')
    ready = core.data_ready()
    if not ready:
        st.caption(core.NOT_READY)
    a, b = st.columns(2)
    follow = a.button('Analyse and follow', type='primary', use_container_width=True, disabled=not ready,
                      help='The weekly check keeps it up to date and notes new reports and price moves in the journal.')
    once = b.button('One-time analysis', use_container_width=True, disabled=not ready,
                    help='Analysed once, as of today; never updated.')
    if follow or once:
        with st.spinner(f"Analysing {r['company']} (downloads 12 years of prices)..."):
            _, err = core.wl('add', ticker=r['ticker'], once=once)
        if err:
            st.error(err)
        else:
            data.changed()
            st.session_state['focus'] = r['ticker']
            st.switch_page(st.session_state['pages']['candidates'])


def render():
    rows = data.screen()
    st.title('Screener')
    st.caption('An idea generator: the playbook\'s 10 checks on the S&P 500 and STOXX Europe 600 (banks, insurers and '
               'real estate left out). Passing all 10 means worth a deep dive, never "buy". ' + core.DISCLAIMER)
    if not rows:
        st.warning('No screener data. Run a full refresh on the Update data page.')
        return
    f = st.columns([1.6, 1.9, 2, 2])
    region = f[0].segmented_control('Region', ['All', 'US', 'Europe'], default='All', required=True)
    least = f[1].segmented_control('Checks passed', [10, 9, 8, 0], default=10, required=True,
                                   format_func=lambda v: 'Any' if v == 0 else f'{v}+' if v < 10 else 'All 10')
    sectors = sorted({r['sector'] for r in rows if r['sector']})
    pick = f[2].multiselect('Sector', sectors, placeholder='All sectors')
    q = f[3].text_input('Search', placeholder='Company or ticker').strip().lower()
    view = [r for r in rows if (region == 'All' or r['region'] == region) and r['passed'] >= least
            and (not pick or r['sector'] in pick) and (not q or q in r['company'].lower() or q in r['ticker'].lower())]
    st.caption(f"{len(view)} of {len(rows)} companies shown · {sum(r['passed'] == 10 for r in rows)} pass all 10. "
               'Missing a company (many German and Swiss ones have no free data)? Add its annual report on the '
               '"Add a report" page.')
    if not view:
        st.info('No company matches these filters.')
        return
    table = pd.DataFrame([{
        'Company': r['company'], 'Ticker': r['ticker'], 'Region': r['region'], 'Sector': r['sector'],
        'Checks': r['passed'], 'Quality': f"{r['quality_passed']}/6", 'GARP': f"{r['garp_passed']}/4",
        'ROIC (median)': pct100(r['roic_median']), 'Revenue growth': pct100(r['revenue_growth']), 'Cash/share growth': pct100(r['fcf_ps_growth']),
        'Growth price assumes': pct100(r['implied_growth']), 'P/E': r['pe'], 'Years': r['years'], 'Source': r['source'],
        'Notes': (lambda n: f"{n} note{'s' if n > 1 else ''}" if n else '')(len(core.data_notes(r['data_flags'])))}
        for r in view])
    pc = st.column_config.NumberColumn(format='%.1f%%')
    ev = st.dataframe(table, hide_index=True, on_select='rerun', selection_mode='single-row', key='scr_table',
                      height=min(420, 38 + 35 * len(view)), column_config={
                          'Company': st.column_config.TextColumn('Company', pinned=True),  # stays in view when scrolling
                          'Checks': st.column_config.ProgressColumn('Checks', min_value=0, max_value=10, format='%d/10'),
                          'ROIC (median)': pc, 'Revenue growth': pc, 'Cash/share growth': pc, 'Growth price assumes': pc,
                          'P/E': st.column_config.NumberColumn(format='%.1f'),
                          'Notes': st.column_config.TextColumn(
                              'Notes', help='Notes on the data. Click the row to read them in full.')})
    if not ev.selection.rows:
        st.caption('Click a row to see its checks and analyse it.')
        return
    r = view[ev.selection.rows[0]]
    st.divider()
    st.subheader(r['company'])
    st.caption(f"{r['ticker']} · {r['region']} · {r['sector']} · {r['years']} years of figures "
               f"({r['first_year']}–{r['last_year']}) · source {r['source']} · price {r['price']} {r['price_currency']}")
    st.dataframe(pd.DataFrame([{'Step': s, 'Check': n, 'Value': v(r), 'Threshold': t, 'Result': RESULT.get(r[k], r[k])}
                               for k, s, n, v, t in CHECKS]), hide_index=True)
    core.show_notes(r['data_flags'], st)
    analyse_buttons(r)

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
     else 'net debt, and free cash flow not positive' if r['net_debt_to_fcf'] is None
     else f"net debt {r['net_debt_to_fcf']:.1f} years of FCF", '≤ 3 years of FCF'),
    ('q_margins', 'Quality', 'Margins hold',
     lambda r: f"{r['margin_kind']} margin low {core.pct(r['margin_min'])}, median {core.pct(r['margin_median'])}",
     '≤ 5 points below median'),
    ('q_dilution', 'Quality', 'No dilution',
     lambda r: 'n/a' if r['shares_change'] is None else f"shares {r['shares_change']:+.1%} a year", '≤ +1% a year'),
    ('g_revenue', 'GARP', 'Growing revenue',
     lambda r: f"{core.gpct(r['revenue_growth'])} a year ({r['first_year']}–{r['last_year']})", '≥ 5%'),
    ('g_fcf_ps', 'GARP', 'Growing cash per share', lambda r: f"{core.gpct(r['fcf_ps_growth'])} a year", '≥ 5%'),
    ('g_still_growing', 'GARP', 'Still growing', lambda r: f"{core.gpct(r['revenue_growth_3y'])} a year, last 3 years",
     'above zero'),
    ('g_price', 'GARP', 'Reasonable price',
     lambda r: f"implied {core.gpct(r['implied_growth'])} vs cautious base {core.gpct(r.get('base_growth'))}",
     'implied ≤ base growth'),
]
# Streamlit shows an empty number cell as "None" whatever the format. So each number column holds a text key that sorts
# like the number ("" for none, which sorts first) and the table shows it formatted, or "—" for none.
key = lambda v: '' if v is None else f'{v + 1e6:015.4f}'
shown_as = lambda fmt: lambda k: '—' if k == '' else fmt.format(float(k) - 1e6)
pct100 = lambda v: key(None if v is None else v * 100)
RESULT = {'pass': '✅ Pass', 'fail': '❌ Fail', 'n/a': '— No data', 'ask': '❓ Ask why'}
# why a check has no result
NO_DATA = {
    'q_roic': 'fewer than 5 years with a return on capital (negative capital or missing figures)',
    'q_roic_min': 'fewer than 5 years with a return on capital (negative capital or missing figures)',
    'q_cash_conversion': 'fewer than 5 years with both free cash flow and net profit, or total net profit not positive',
    'q_debt': 'no debt figure for the latest year',
    'q_margins': 'fewer than 5 years with a gross or operating margin',
    'q_dilution': 'fewer than 5 years with a share count',
    'g_revenue': 'fewer than 5 years of revenue, or the first year\'s revenue not positive',
    'g_fcf_ps': 'fewer than 5 years of free cash flow per share, or its averages not positive',
    'g_still_growing': 'fewer than 4 years of revenue',
}


def result(r, k):
    v = r[k]
    if v == 'n/a':
        why = r.get('price_why') if k == 'g_price' else NO_DATA.get(k)
        return f"— No data: {why}" if why else RESULT[v]
    if v == 'ask':
        return '❓ Ask why: the price assumes the company shrinks. Cheap, or does the market know something?'
    return RESULT.get(v, v)


def analyse_buttons(r):
    entry = next((e for e in core.watchlist() if e['ticker'] == r['ticker']), None)
    if entry and entry.get('hidden'):
        st.info(f"You removed {r['company']} from your candidates on {entry['hidden']}. Put it back as it was, or "
                'analyse it again below.')
        if st.button('Put it back in Candidates'):
            _, err = core.wl('unhide', ticker=r['ticker'])
            if err:
                st.error(err)
            else:
                data.changed()
                st.session_state['focus'] = r['ticker']
                st.switch_page(st.session_state['pages']['candidates'])
    elif entry:
        st.success(f"{r['company']} is already in your candidates "
                   f"({'following' if entry['mode'] == 'watch' else 'one-time analysis'}).")
        if st.button('Open it in Candidates'):
            st.session_state['focus'] = r['ticker']
            st.switch_page(st.session_state['pages']['candidates'])
        return
    st.markdown(f"**Analyse it:** reverse DCF, bear/base/bull values and {r['years']} years of history. It then shows "
                'in Candidates.')
    ready = core.data_ready()
    if not ready:
        st.caption(core.NOT_READY)
    a, b = st.columns(2)
    follow = a.button('Analyse and follow', type='primary', use_container_width=True, disabled=not ready,
                      help='The monthly check keeps it up to date and notes new reports and price moves in the journal.')
    once = b.button('One-time analysis', use_container_width=True, disabled=not ready,
                    help='Analysed once, as of today; never updated.')
    if follow or once:
        with st.spinner(f"Analysing {r['company']} (downloads 12 years of prices)..."):
            _, err = core.wl('add', ticker=r['ticker'], once=once)
        if err and 'free cash flow is not positive' in err:
            st.warning(f"{r['company']} can't get a value range: its free cash flow is below zero (it uses more cash "
                       'than its business brings in), and a DCF only works on cash a company produces. Its checks are '
                       'above; its latest twelve months are on the Add a report page, Quarterly report tab.')
        elif err:
            st.error(err)
        else:
            data.changed()
            st.session_state['focus'] = r['ticker']
            st.switch_page(st.session_state['pages']['candidates'])


def added():
    """Companies you added yourself (Add a report: a new company, or a US company by ticker)."""
    try:
        import csv
        return {r['ticker'] for r in csv.DictReader(open(core.ADDED, encoding='utf-8', errors='replace'))
                if r.get('source') == 'user' or r.get('country') == 'US'}
    except OSError:
        return set()


def render():
    rows = data.screen()
    st.title('Screener')
    st.caption('An idea generator: the playbook\'s 10 checks on the S&P 500 and STOXX Europe 600 (banks, insurers and '
               'real estate left out). Passing all 10 means worth a deep dive, never "buy". ' + core.DISCLAIMER)
    if not rows:
        st.warning('No screener data. Run a full refresh on the Update data page.')
        return
    f = st.columns([1.6, 1.9, 2, 2])
    region = f[0].pills('Region', ['All', 'US', 'Europe'], default='All', key='scr_region') or 'All'
    least = f[1].pills('Checks passed', [10, 9, 8, 0], default=10, key='scr_least',
                       format_func=lambda v: 'Any' if v == 0 else f'{v}+' if v < 10 else 'All 10')
    least = 10 if least is None else least
    sectors = sorted({r['sector'] for r in rows if r['sector']})
    pick = f[2].multiselect('Sector', sectors, placeholder='All sectors', key='scr_sectors')
    import unicodedata  # "ＮＶＤＡ" typed with a Japanese or Chinese keyboard finds NVDA
    q = unicodedata.normalize('NFKC', f[3].text_input('Search', placeholder='Company or ticker', key='scr_q')).strip().lower()
    # a search finds a company whatever its checks, and the companies you added yourself are always shown
    mine = added()
    view = [r for r in rows if (region == 'All' or r['region'] == region)
            and (r['passed'] >= least or q or 'your files' in r['source'] or r['ticker'] in mine)
            and (not pick or r['sector'] in pick) and (not q or q in r['company'].lower() or q in r['ticker'].lower())]
    from collections import Counter
    dates = Counter(r.get('price_date') for r in rows if r.get('price_date'))
    common = dates.most_common(1)[0][0] if dates else None
    newer = sum(n for d, n in dates.items() if common and d > common)
    yours = sum(r['ticker'] in mine or 'your files' in r['source'] for r in rows)
    st.caption(f"{len(view)} of {len(rows)} companies shown"
               + (f" ({yours} of them added by you)" if yours else '')
               + f" · {sum(r['passed'] == 10 for r in rows)} pass all 10"
               + (f" · prices of {common}" + (f" ({newer} newer, from analyses and checks)" if newer else '')
                  if common else '') + '. '
               'A company whose figures need checking shows at most 9 of 10 until you have checked them. '
               'A search, and the companies you added yourself, show whatever their checks. '
               'Missing a company (many German and Swiss ones have no free data)? Add its annual report on the '
               '"Add a report" page.')
    if not view:
        st.info('No company matches these filters.')
        return
    table = pd.DataFrame([{
        'Company': r['company'], 'Ticker': r['ticker'], 'Region': r['region'], 'Sector': r['sector'],
        'Checks': r['passed'], 'Quality': f"{r['quality_passed']}/6", 'GARP': f"{r['garp_passed']}/4",
        'Data': 'check first' if r.get('data_check') else '',
        'ROIC (median)': pct100(r['roic_median']), 'Revenue growth': pct100(r['revenue_growth']), 'Cash/share growth': pct100(r['fcf_ps_growth']),
        'Growth price assumes': pct100(r['implied_growth']), 'P/E': key(r['pe']),
        'Years': r['years'], 'Source': r['source'],
        'Notes': (lambda n: f"{n} note{'s' if n > 1 else ''}" if n else '')(len(core.data_notes(r['data_flags'])))}
        for r in view])
    shown = table.style.format({k: shown_as('{:.1f}%') for k in ('ROIC (median)', 'Revenue growth', 'Cash/share growth',
                                                                  'Growth price assumes')} | {'P/E': shown_as('{:.1f}')})
    # the table is keyed on the filters, so a changed filter never leaves an old row number selected; the company you
    # had open stays selected when it is still in view
    fkey = f"scr_table_{region}_{least}_{'|'.join(pick)}_{q}"
    ss = st.session_state
    keep = next((i for i, r in enumerate(view) if r['ticker'] == ss.get('scr_ticker')), None)
    ev = st.dataframe(shown, hide_index=True, on_select='rerun', selection_mode=['single-row', 'single-cell'], key=fkey,
                      selection_default={'selection': {'rows': [keep]}} if keep is not None else None,
                      height=min(420, 38 + 35 * len(view)), column_config={
                          'Company': st.column_config.TextColumn('Company', pinned=True),  # stays in view when scrolling
                          **{k: st.column_config.TextColumn(k, alignment='right') for k in (
                              'ROIC (median)', 'Revenue growth', 'Cash/share growth', 'Growth price assumes', 'P/E')},
                          'Checks': st.column_config.ProgressColumn('Checks', min_value=0, max_value=10, format='%d/10'),
                          'Data': st.column_config.TextColumn(
                              'Data', help='"check first": a figure differs from a second source, or debt, capital '
                                           'spending or the share count looks odd. Click the row for the notes.'),
                          'Notes': st.column_config.TextColumn(
                              'Notes', help='Notes on the data. Click the row to read them in full.')})
    i = core.picked(ev, len(view), keep, ss.setdefault(f'pick_{fkey}', {}))
    if i is None:
        st.caption('Click a row to see its checks and analyse it.')
        return
    r = view[i]
    ss['scr_ticker'] = r['ticker']
    st.divider()
    st.subheader(r['company'])
    st.caption(f"{r['ticker']} · {r['region']} · {r['sector']} · {r['years']} years of figures "
               f"({r['first_year']}–{r['last_year']}) · source {r['source']} · price "
               + core.md(core.money(r['price'] / 100, 'GBP') if r['price_currency'] in ('GBp', 'GBX') and r['price']
                         else core.money(r['price'], r['price_currency']))
               + (f" on {r['price_date']}" if r.get('price_date') else ''))
    st.dataframe(pd.DataFrame([{'Check': n, 'Result': result(r, k), 'Value': v(r), 'Threshold': t, 'Step': s}
                               for k, s, n, v, t in CHECKS]), hide_index=True,
                 column_config={'Result': st.column_config.TextColumn('Result', width='large')})
    st.caption('"Reasonable price": the growth today\'s price assumes (reverse DCF at 9%) should be no more than the '
               'cautious base growth (the lower of cash-flow and recent revenue growth, kept between 2% and 12%), not '
               'the best years\' growth.')
    core.show_notes(r['data_flags'], st)
    analyse_buttons(r)

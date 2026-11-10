"""Journal: every decision and every change, newest first. Entries are added, never edited."""
import pandas as pd
import streamlit as st

import core
from views import data
from views.candidates import journal_form, newest_first


def render():
    d = data.dashboard()
    entries = newest_first(d['journal'])
    st.title('Journal')
    st.caption('Why you bought, waited or passed, written at the time. Reading it back later is how you learn which '
               'of your judgements held up. Entries are never edited: write a new one when you change your mind. '
               + core.DISCLAIMER)
    who = st.segmented_control('Written by', ['Everyone', 'You', 'The program'], default='Everyone', required=True)
    if who == 'You':
        entries = [e for e in entries if e.get('author') == 'You']
    elif who == 'The program':
        entries = [e for e in entries if e.get('author') != 'You']
    if entries:
        st.dataframe(pd.DataFrame([{
            'Date': e['date'], 'Company': e['company'], 'Decision': e['decision'],
            'Price': core.money(e['price'], e['currency']), 'Base value': core.money(e.get('base'), e['currency']),
            'Growth the price assumed': core.pct(e.get('implied_growth')), 'Why': e['why'],
            'What would change my mind': e.get('change_mind', ''), 'Next check': e.get('next_check', ''),
            'By': e.get('author', '')} for e in entries]), hide_index=True,
            column_config={'Company': st.column_config.TextColumn('Company', pinned=True),
                           'Why': st.column_config.TextColumn(width='large')})
    else:
        st.info('No entries yet.')
    claims_part()
    cands = d['candidates']
    if cands:
        st.divider()
        name = st.selectbox('Write an entry about', [c['company'] for c in cands])
        journal_form(next(c for c in cands if c['company'] == name), key='_journal_page')


def claims_part():
    import claims
    allc = claims.load()
    if not allc:
        return
    st.divider()
    st.subheader('Your claims')
    r = claims.report(allc)
    a, b, c = st.columns(3)
    a.metric('Waiting for figures', r['open'])
    a2 = r.get('hit')
    b.metric('Came true', 'n/a' if a2 is None else f"{a2:.0%}", f"of {r['settled']} checked", delta_color='off')
    nh = r.get('naive_hit')
    c.metric('Simple forecast right', 'n/a' if nh is None else f"{nh:.0%}",
             help='The same claims, judged by "the last three years\' trend continues" (for a margin: "it stays where '
                  'it was"). Your research adds something when your claims come true more often than this.')
    if r.get('calibration'):
        st.caption('How sure you were, and how often it came true: ' + '; '.join(
            f"{k}% sure: {v[0]:.0%} of {v[1]}" for k, v in r['calibration'].items())
            + '. A few claims say little; this means something after a few dozen.')
    st.dataframe(pd.DataFrame([{
        'Made': c['made'], 'Company': c['company'], 'Claim': claims.describe(c), 'Sure': f"{c['confidence']}%",
        'Result': ('waiting' if c.get('outcome') is None else ('✅ came true' if c['outcome'] else '❌ did not'))
                  + (f" ({c['actual']:.1%})" if c.get('actual') is not None else ''),
        'Simple forecast': ('says yes' if c.get('naive_says') else 'says no' if c.get('naive_says') is False else 'n/a'),
        'Why': c['why']} for c in reversed(allc)]), hide_index=True,
        column_config={'Company': st.column_config.TextColumn('Company', pinned=True),
                       'Claim': st.column_config.TextColumn(width='large')})

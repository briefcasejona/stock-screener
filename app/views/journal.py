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
            'Price': core.money(e['price'], e['currency']), 'Base value': core.money(e['base'], e['currency']),
            'Growth the price assumed': core.pct(e.get('implied_growth')), 'Why': e['why'],
            'What would change my mind': e.get('change_mind', ''), 'Next check': e.get('next_check', ''),
            'By': e.get('author', '')} for e in entries]), hide_index=True,
            column_config={'Why': st.column_config.TextColumn(width='large')})
    else:
        st.info('No entries yet.')
    cands = d['candidates']
    if cands:
        st.divider()
        name = st.selectbox('Write an entry about', [c['company'] for c in cands])
        journal_form(next(c for c in cands if c['company'] == name), key='_journal_page')

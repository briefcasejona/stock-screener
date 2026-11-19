"""Journal: every decision and every change, newest first. Entries are added, never edited."""
import pandas as pd
import streamlit as st

import commit
import core
from views import data
from views.candidates import journal_form, newest_first


def render():
    d = data.dashboard()
    entries = newest_first(d['journal'])
    st.title('Journal')
    st.caption('Why you bought, waited or said no, written at the time. Reading it back later is how you learn which '
               'of your judgements held up. Entries are never edited: write a new one when you change your mind. '
               + core.DISCLAIMER)
    who = st.segmented_control('Written by', ['Everyone', 'You', 'The program'], default='Everyone', required=True)
    if who == 'You':
        entries = [e for e in entries if e.get('author') == 'You']
    elif who == 'The program':
        entries = [e for e in entries if e.get('author') != 'You']
    # before your own estimate of a company, the program's notes on it would give its valuation away
    wl = {w['ticker']: w for w in core.watchlist()}
    open_book = {c['company'] for c in d['candidates']
                 if (wl.get(c['ticker']) or {}).get('worked_example') or commit.get(c['ticker'])}
    known = {c['company'] for c in d['candidates']}
    hidden = lambda e: e.get('author') != 'You' and e['company'] in known and e['company'] not in open_book
    companies = sorted({e['company'] for e in entries})
    pick = st.multiselect('Company', companies, placeholder='All companies', key='jr_companies')
    if pick:
        entries = [e for e in entries if e['company'] in pick]
    if entries:
        why = lambda e: 'shown once you have locked in your own estimate' if hidden(e) else e['why']
        # your own words come first, so they stay in view on a small screen; click a row to read the entry in full
        ev = st.dataframe(pd.DataFrame([{
            'Date': e['date'], 'Company': e['company'], 'Decision': core.word(e.get('decision')), 'Why': why(e),
            'What would change my mind': e.get('change_mind', ''), 'Next check': e.get('next_check', ''),
            'Price': '' if e.get('price') is None else core.price_text(e),
            'By': e.get('author', '')} for e in entries]), hide_index=True, on_select='rerun',
            selection_mode=['single-row', 'single-cell'], key=f"jr_table_{who}_{'|'.join(pick)}",
            column_config={'Company': st.column_config.TextColumn('Company', pinned=True),
                           'Why': st.column_config.TextColumn(width='large')})
        i = core.picked(ev, len(entries), st.session_state.get('jr_open'),
                        st.session_state.setdefault(f"pick_jr_{who}_{'|'.join(pick)}", {}))
        st.session_state['jr_open'] = i
        if i is not None:
            e = entries[i]
            with st.container(border=True):
                st.markdown(f"**{core.md(e['company'])}** · {e['date']} · {core.md(core.word(e.get('decision')))}"
                            + (f" · price {core.md(core.price_text(e))}" if e.get('price') is not None
                               else '') + f" · by {core.md(e.get('author', ''))}")
                st.markdown(core.md(why(e)))
                if e.get('change_mind'):
                    st.markdown('**What would change my mind:** ' + core.md(e['change_mind']))
                if e.get('next_check'):
                    st.markdown('**Next check:** ' + core.md(e['next_check']))
        else:
            st.caption('Click or tap a row to read the entry in full.')
    else:
        st.info('No entries yet.')
    claims_part()
    cands = d['candidates']
    if cands:
        st.divider()
        focus = next((i for i, c in enumerate(cands) if c['ticker'] == st.session_state.get('cand_ticker')), 0)
        name = st.selectbox('Write an entry about', [c['company'] for c in cands], index=focus)
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
    b.metric(f"Came true (of {r['settled']} checked)", 'n/a' if a2 is None else f"{a2:.0%}")
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

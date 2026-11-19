"""Start here: one card with the one next step, and a short "since last time" strip. Not a dashboard (testers asked for
one card and one button, 19 Nov 2026 review, idea I1)."""
import re

import streamlit as st

import commit
import core
from views import data

EVENT_WORDS = {'annual report': 'new annual report, analysis re-run', 'interim report': 'new quarterly or half-year report',
               'price crossed buy-below': 'price crossed your buy-below price', 'Claim checked': 'a claim of yours was checked'}


def open_book(d):
    """The companies whose program notes may be shown: your own estimate is written down (or it is the worked example).
    Before that, a note would give the program's valuation away."""
    wl = {w['ticker']: w for w in core.watchlist()}
    return {c['company'] for c in d['candidates']
            if (wl.get(c['ticker']) or {}).get('worked_example') or commit.get(c['ticker'])}


def next_step(d):
    """The one thing to do now: (title, why, button label, action). The action is a page key, ('focus', ticker) for a
    company on the Candidates page, or 'check' to run the monthly check here."""
    s = core.settings()
    if not core.data_ready():
        return ('Wait for today\'s prices', core.NOT_READY, None, None)
    if not s.get('sec_contact'):
        return ('Add your email address for the SEC',
                'The SEC, where the US company figures come from, asks for a contact address with every download. It '
                'is sent to the SEC only.', 'Open Update data', 'update')
    if core.check_due() and any(e['mode'] == 'watch' and not e.get('hidden') for e in core.watchlist()):
        return ('Run the monthly check',
                'A month has passed: fresh figures and prices for the companies you follow, and a journal note for '
                'anything that changed.', 'Run it now', 'check')
    wl = {w['ticker']: w for w in core.watchlist()}
    cands = [c for c in d['candidates'] if not (wl.get(c['ticker']) or {}).get('worked_example')]
    for c in cands:
        if not commit.get(c['ticker']):
            return (f"Write down your own estimate for {c['company']}",
                    'Your growth rate and value first, from the history and the annual report; the program shows its '
                    'own numbers after that, next to yours.', f"Open {c['company']}", ('focus', c['ticker']))
    for c in cands:
        if core.my_decision(c, d['journal'])[0] is None:
            return (f"Decide on {c['company']}",
                    'Your estimate is written down. Read the latest annual report, then write your decision (Buy, '
                    'Wait or No) and what would change your mind in the journal, on its Journal tab.',
                    f"Open {c['company']}", ('focus', c['ticker']))
    try:
        import course
        step, n = course.next_step(course.progress())
    except Exception:
        step, n = 'done', None
    words = {'before': ('Write a "before" write-up', 'Two short write-ups before lesson 1, so you can see later how '
                        'much the course changed the way you look at a company.'),
             'lesson': (f'Do lesson {n} of the course', 'One lesson on a real company, then a write-up of your own.'),
             'solo': ('Write a solo write-up', 'Five on your own, without the lessons open; at least one ends in "No".'),
             'graduate': ('Finish the course', 'Your solo write-ups are done: real-money picks can now be unlocked.')}
    if step in words:
        return (*words[step], 'Open the Course', 'course')
    return ('Look for a new idea', 'Every company you analysed has your estimate and your decision. The companies '
            'that pass all 10 checks are a place to start.', 'Open the Screener', 'screener')


def go(action):
    ss = st.session_state
    if isinstance(action, tuple):
        ss['focus'] = action[1]
        st.switch_page(ss['pages']['candidates'])
    st.switch_page(ss['pages'][action])


def since_last_time(d):
    """What changed since you last opened the program: the program's journal notes, a new version, the next check."""
    last = st.session_state.get('last_seen')
    lines = []
    if st.session_state.get('updated_from'):
        lines.append(f"The program was updated (from version {st.session_state['updated_from']} to "
                     f"{core.program_version()}).")
    if last:
        shown = open_book(d)
        notes = [e for e in d['journal'] if e.get('author') != 'You' and (e.get('date') or '') >= last]
        hidden = [e for e in notes if e['company'] not in shown and e.get('decision') != 'Claim checked']
        for e in [e for e in notes if e not in hidden][:5]:
            # the program's notes all say "Note": their first words say what happened ("Added to the watchlist")
            what = EVENT_WORDS.get(e.get('decision')) or re.split(r'[:.](?:\s|$)', e.get('why') or 'a note', 1)[0][:90]
            lines.append(core.md(f"**{e['company']}**: {what} ({e['date']})."))
        if len(notes) - len(hidden) > 5:
            lines.append(f"And {len(notes) - len(hidden) - 5} more notes in the journal.")
        if hidden:
            lines.append(f"{len(hidden)} note{'s' if len(hidden) != 1 else ''} on companies you haven't written your "
                         'own estimate for yet (shown once you have).')
        if not notes:
            lines.append(f"No new notes from the program since you last opened it ({last}).")
    try:
        import claims
        r = claims.report()
        if r['open']:
            lines.append(f"{r['open']} claim{'s' if r['open'] != 1 else ''} waiting for the figures of the year "
                         'they are about.')
    except Exception:
        pass
    lines.append(f"Next monthly check: {core.next_check_date():%d %b %Y}.")
    return lines


def render():
    d = data.dashboard()
    st.title('Start here')
    title, why, label, action = next_step(d)
    with st.container(border=True):
        st.caption('Your next step')
        st.subheader(title)
        st.write(why)
        if label and st.button(label, type='primary', key='home_go'):
            if action == 'check':
                with st.spinner('Checking the companies you follow...'):
                    out, err = core.run_check()
                data.changed()
                if err:
                    st.error(f'The monthly check could not finish: {err}')
                else:
                    st.session_state['checked'] = True
                    st.rerun()
            else:
                go(action)
    st.markdown('**Since last time**')
    for line in since_last_time(d):
        st.markdown(f'- {line}')
    st.caption('The other pages are in the bar at the top; your own data (portfolio, reports, updates) is under '
               f'"My data". {core.DISCLAIMER}')

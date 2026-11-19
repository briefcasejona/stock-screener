"""Course: six lessons on researching a company, each done on a real company and ending in a write-up."""
import pandas as pd
import streamlit as st

import core
import course as C
import course_text as T
from views import data


def checklist(p):
    step, _ = C.next_step(p)
    a, b, c, d = st.columns(4)
    a.metric('"Before" write-ups', f"{min(p['before'], C.BEFORE)} of {C.BEFORE}")
    b.metric('Lessons done', f"{len(p['lessons'])} of 6")
    c.metric('Solo write-ups', f"{min(p['solo'], C.SOLO)} of {C.SOLO}")
    d.metric('Solo ending in "No"', 'yes' if p['solo_no'] else 'not yet')
    return step


def rule_part(p):
    st.subheader('Your pass/fail rule')
    if p['rule']:
        st.write(f"Written on {p['rule']['date']}, and it stays as it is:")
        st.info(core.md(p['rule']['text']))
        return
    st.caption('Decide now what "the course worked" means, before you know how it goes. The suggestion below is yours '
               'to change. Once saved, it can\'t be changed: that keeps the test honest.')
    with st.form('rule'):
        text = st.text_area('The course worked if...', T.PASS_FAIL, height=100)
        if st.form_submit_button('Lock in my rule', type='primary'):
            do(lambda: C.set_rule(text), 'Your rule is written down.')


def lesson(n, l, open_):
    with st.expander(f"Lesson {n}: {l['title']}", expanded=open_):
        t = st.tabs(['What to find', 'Where to find it', 'Why GARP cares', 'What the classics teach'])
        for tab, k in zip(t, ('find', 'where', 'why', 'classics')):
            tab.markdown(l[k])
        st.markdown(f"**Now do it:** {l['do']}")


def writeup_form(step, n):
    label = {'before': '"before" write-up', 'lesson': f'write-up for lesson {n}', 'solo': 'solo write-up'}[step]
    st.subheader(f'Record your {label}')
    if step == 'solo':
        st.caption('Without the lessons open, on a company you have not written up before. At least one of the five '
                   'ends in "No".')
    cands = data.dashboard()['candidates']
    if not cands:
        st.info('Analyse a company on the Screener page first; it then shows up on the Candidates page.')
        return
    ready = [c for c in cands if not C.not_ready(c)]
    if not ready:
        st.info('No company is ready for a write-up yet. On the Candidates page, pick a company (not the worked example), '
                'write down your own estimate for it, then make at least one claim about it (Journal tab there).')
        with st.expander('Why each company is not ready'):
            for c in cands:
                st.markdown(f"- {core.md(C.not_ready(c))}")
        return
    st.caption('Companies listed: the ones with your own estimate and at least one claim. '
               + (f"Not ready yet: {', '.join(core.md(c['company']) for c in cands if C.not_ready(c))}".rstrip('.') + '.'
                  if len(ready) < len(cands) else ''))
    ss = st.session_state
    n_ = ss.setdefault('writeup_n', 0)  # a new key after a recorded write-up empties the form; a refused one keeps it
    with st.form(f'writeup_{n_}'):
        tk = st.selectbox('Company', [c['ticker'] for c in ready],
                          format_func=lambda t: next(c['company'] for c in ready if c['ticker'] == t))
        st.write('Three different figures you checked in the annual report, each with the number and the page (for '
                 'example: revenue 2025, 10.8 bn USD, page 52). The program\'s own figure is put next to yours where '
                 'it has one (revenue, EPS, free cash flow per share, ROIC, gross margin).')
        figs = []
        for i in range(3):
            a, b = st.columns([1, 2])
            figs.append({'name': a.text_input(f'Figure {i + 1}', key=f'fn{i}_{n_}'),
                         'report': b.text_input(f'What the report says, and where ({i + 1})', key=f'fr{i}_{n_}'),
                         'program': ''})
        dec = st.segmented_control('Decision', C.DECISIONS, default='Wait', required=True,
                                   help='"Buy" means a paper buy during the course; record it on the Scoreboard.')
        summary = st.text_area('Your conclusion, in one or two lines', height=80, key=f'ws_{n_}')
        if st.form_submit_button('Record the write-up', type='primary'):
            c = next(x for x in ready if x['ticker'] == tk)
            try:
                C.add(c, dec, figs, summary, data.dashboard().get('history'))
            except ValueError as e:
                st.error(str(e))
                return
            ss['writeup_n'] = n_ + 1
            data.changed()
            st.toast('Recorded, and noted in the journal.')
            st.rerun()


def do(fn, ok):
    try:
        fn()
    except ValueError as e:
        st.error(str(e))
        return
    data.changed()
    st.toast(ok)
    st.rerun()


def render():
    st.title('Course')
    st.caption('Six lessons on researching a company. Each one is done on a real company from your candidates and ends '
               'in a write-up. Done = the six lessons plus five solo write-ups; that unlocks real picks on the Scoreboard. '
               'At 3-5 hours a week, expect about 6-9 months. ' + core.DISCLAIMER)
    p = C.progress()
    step = checklist(p)
    st.divider()
    rule_part(p)
    st.divider()
    st.subheader('Lessons')
    if step == 'before':
        st.markdown(T.BEFORE)
    nxt = C.next_step(p)[1]
    for i, l in enumerate(T.LESSONS, 1):
        lesson(i, l, open_=(i == nxt))
    st.divider()
    if step in ('before', 'lesson', 'solo'):
        writeup_form(step, nxt)
    elif step == 'graduate':
        st.success('Every step is done. Finishing the course unlocks real picks on the Scoreboard. Start small: paper '
                   'money can\'t teach you how you will act after a real 30% fall.')
        if st.button('Finish the course', type='primary'):
            do(C.graduate, 'Course finished. Real picks are unlocked.')
    else:
        st.success(f"You finished the course on {p['graduated']}. Real picks are unlocked on the Scoreboard. Your claims "
                   'keep being checked: they show whether your judgement is good.')
    w = C.load()['writeups']
    if w:
        st.subheader('Your write-ups')
        st.dataframe(pd.DataFrame([{
            'Date': x['date'], 'Company': x['company'],
            'Step': {'before': 'Before', 'lesson': f"Lesson {x['lesson']}", 'solo': 'Solo'}[x['kind']],
            'Decision': x['decision'], 'Conclusion': x['summary'],
            'Your figures (program\'s)': '; '.join(f"{f['name']}: {f['report']}" + (f" ({f['program']})" if f.get('program')
                                                                                   else '') for f in x['figures'])}
            for x in reversed(w)]), hide_index=True,
            column_config={'Conclusion': st.column_config.TextColumn(width='large'),
                           "Your figures (program's)": st.column_config.TextColumn(width='large')})
        st.caption('A figure of yours far from the program\'s means one of you read it wrong: find out which.')

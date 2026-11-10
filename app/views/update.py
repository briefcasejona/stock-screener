"""Update data: the weekly check, fresh prices, a full refresh, and backing up your own work."""
import os
import re
import zipfile
from datetime import date

import streamlit as st

import core
import jobs
from views import data

def tail(path, n=12):
    try:
        return ''.join(open(path, encoding='utf-8', errors='replace').readlines()[-n:])
    except OSError:
        return ''


@st.fragment(run_every=3)
def job_progress():
    """The background job's progress, refreshed every few seconds."""
    s = jobs.status()
    if not s:
        return
    live = jobs.running()
    was = st.session_state.get('job_seen')
    st.session_state['job_seen'] = s['state'] if live or s['state'] != 'running' else 'stopped'
    if live:
        st.info(f"{s['label']}: step {s['step']} of {s['steps']}, {s['step_name']} (started {s['started']}). "
                'It keeps going in the background, even if you switch pages or close the program.')
        st.progress(max(s['step'] - 1, 0) / s['steps'])
        st.code(tail(jobs.LOG), language=None)
    elif s['state'] == 'running':
        st.warning(f"{s['label']} stopped before it finished (was the program or the laptop shut down?). "
                   'Start it again; nothing is lost.')
    elif s['state'] == 'done':
        st.success(f"{s['label']} finished on {s['finished']}.")
    else:
        st.error(f"{s['label']} failed at \"{s['step_name']}\". The last messages:")
        st.code(tail(jobs.LOG), language=None)
    if was == 'running' and not live:  # it just ended: show the new data everywhere
        data.changed()
        st.rerun(scope='app')


def show_check(out):
    if not out:
        return
    st.caption(f"Last weekly check: {out['at']}, {len(out['checked'])} companies followed.")
    for e in out['events']:
        if e['event'] == 'annual report':
            st.success(f"{e['company']}: new annual report (year to {e['year_to']}). The analysis was re-run: base value "
                       f"{core.money(e['base_now'], e['currency'])}, {e['checks_passed']} of 10 checks pass.")
        elif e['event'] == 'interim report':
            st.info(f"{e['company']}: new {e['report']['form']} for the period to {e['report']['period_end']}. "
                    'The analysis uses yearly figures, so read it for news; nothing was re-run.')
        else:
            into = e['into_buy_zone_at_margins']
            st.warning(f"{e['company']}: the price ({core.money(e['price'], e['currency'])}) moved "
                       + ('to or below' if into else 'back above') + ' the buy-below price at a '
                       + ', '.join(f'{m}%' for m in sorted(into or e['out_of_buy_zone_at_margins'])) + ' margin of safety.')
    for p in out['problems']:
        st.error(f"{p['ticker']}: {p['problem']}")
    if not out['events'] and not out['problems']:
        st.caption('Nothing new.')


def render():
    st.title('Update data')
    st.caption('Everything is downloaded from free sources: SEC and ESEF filings for company figures, Yahoo Finance '
               'for prices and exchange rates. You need an internet connection; nothing is sent anywhere except '
               'these requests.')
    job_progress()
    contact = core.settings().get('sec_contact', '')
    with st.expander('Your email address for the SEC' + ('' if contact else ': needed before the first download'),
                     expanded=not contact, icon=':material/mail:'):
        st.write('The SEC, where the US company figures come from, asks every program to send a contact email address '
                 'with its downloads. It is sent only to the SEC and kept on this laptop.')
        new = st.text_input('Email address', value=contact, placeholder='you@example.com').strip()
        if st.button('Save the address', disabled=new == contact):
            if re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', new):
                core.save_setting(sec_contact=new)
                st.success('Saved.')
            else:
                st.error('That doesn\'t look like an email address.')
    st.divider()

    st.subheader('Weekly check')
    st.write('For every company you follow: fresh figures and price, the analysis re-run when a new annual report is '
             'out, and a journal note when the price crosses a buy-below price. It runs by itself when you open the '
             'program and a week has passed.')
    if not core.data_ready():
        st.caption(core.NOT_READY)
    if st.button('Run the weekly check now', type='primary', disabled=not core.data_ready()):
        with st.spinner('Checking the companies you follow...'):
            out, err = core.run_weekly_check()
        data.changed()
        if err:
            st.error(err)
    show_check(core.settings().get('last_check_result'))

    st.divider()
    st.subheader('Prices for the whole screener')
    st.write('Today\'s prices and exchange rates for all ~700 companies, then the 10 checks again (the "reasonable '
             'price" check depends on the price). Takes 5–10 minutes. Your candidates get new prices in the weekly check.')
    busy = jobs.running() is not None
    if st.button('Refresh prices', disabled=busy):
        jobs.start('prices')
        st.rerun()

    st.divider()
    st.subheader('Full refresh')
    st.write('Downloads all company figures again and re-runs everything, so new annual reports show up in the '
             'screener. Worth doing every few months, and after March–April when most annual reports are out. It takes '
             'about an hour. It runs in the background, so you can keep '
             'using the other pages.')
    sure = st.checkbox('Yes, start a full refresh', disabled=busy)
    if st.button('Start the full refresh', disabled=busy or not sure):
        jobs.start('full')
        st.rerun()
    if core.settings().get('last_full_refresh'):
        st.caption(f"Last full refresh: {core.settings()['last_full_refresh']}.")

    st.divider()
    st.subheader('Your work and its backups')
    st.write(f'Your journal, the companies you follow, their analyses and the reports you added are kept in their own '
             f'folder, apart from the program, so a newer version of the program never touches them: '
             f'**{core.DATA}**. The program makes a backup there by itself every day you use it (the last '
             f'{core.KEEP_BACKUPS} are kept, in the "backups" folder). Now and then, also keep a copy somewhere off '
             'this laptop, like a USB stick.')
    st.download_button('Download a backup', core.backup_bytes(), file_name=f'stock-screener-backup-{date.today()}.zip',
                       mime='application/zip', icon=':material/download:')
    up = st.file_uploader('Restore a backup', type=['zip'])
    if up and st.button('Restore it (replaces your current journal and watchlist)'):
        try:
            n, safety = core.restore_backup(up)
            data.changed()
            msg = (f'Restored {n} files. What you had before is saved in the backups folder as '
                   f'"{os.path.basename(safety)}", in case you need it back.')
            if os.listdir(core.USER_REPORTS) and jobs.start('after_restore'):
                st.success(msg + ' Your own reports are being read into the screener (progress at the top of '
                           'this page).')
            else:
                st.success(msg)
        except (ValueError, zipfile.BadZipFile) as e:
            st.error(f'Not restored: {e}')

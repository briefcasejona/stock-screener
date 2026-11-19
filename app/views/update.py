"""Update data: the monthly check, fresh prices, a full refresh, and backing up your own work."""
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
    st.caption(f"Last monthly check: {out['at']}, {len(out['checked'])} compan{'y' if len(out['checked']) == 1 else 'ies'} followed.")
    for e in out['events']:
        if e['event'] == 'annual report':
            st.success(core.md(f"{e['company']}: new annual report (year to {e['year_to']}). The analysis was re-run: base value "
                       f"{core.money(e['base_now'], e['currency'])}, {e['checks_passed']} of 10 checks pass."))
        elif e['event'] == 'interim report':
            st.info(f"{e['company']}: new {e['report']['form']} for the period to {e['report']['period_end']}. "
                    'The analysis uses yearly figures, so read it for news; nothing was re-run.')
        else:
            into = e['into_buy_zone_at_margins']
            st.warning(core.md(f"{e['company']}: the price ({core.money(e['price'], e['currency'])}) moved "
                       + ('to or below' if into else 'back above') + ' your buy-below price ('
                       + ', '.join(f'{m}%' for m in sorted(into or e['out_of_buy_zone_at_margins'])) + ' margin of safety).'))
    for p in out['problems']:
        st.error(core.md(f"{p['ticker']}: {p['problem']}"))
    zone = out.get('in_buy_zone', [])
    if zone:
        st.info(core.md('At or below your buy-below price now: ' + ', '.join(
            f"{z['company']} ({core.money(z['price'], z['currency'])}, buy-below {core.money(z['buy_below'], z['currency'])})"
            for z in zone) + '. Whether to buy is your decision, after reading the latest annual report.'))
    if not out['events'] and not out['problems'] and not zone:
        st.caption('Nothing new.')


def render():
    st.title('Update data')
    st.caption('Everything is downloaded from free sources: SEC and ESEF filings for company figures, Yahoo Finance '
               'for prices and exchange rates. What leaves this computer: your email address to the SEC only; the '
               'symbols the program asks prices for to Yahoo (on the Portfolio page these are your own holdings, so '
               'Yahoo can see what you hold); and, at each start, a question to GitHub whether a new version exists. '
               'If your data folder is in Google Drive or similar, your data is stored there too.')
    job_progress()
    contact = core.settings().get('sec_contact', '')
    with st.expander('Your email address for the SEC' + ('' if contact else ': needed before the first download'),
                     expanded=not contact, icon=':material/mail:'):
        st.write('The SEC, where the US company figures come from, asks every program to send a contact email address '
                 'with its downloads. It is sent only to the SEC and kept on this laptop.')
        with st.form('sec_email', enter_to_submit=True, border=False):
            new = st.text_input('Email address', value=contact, placeholder='you@example.com')
            saved = st.form_submit_button('Save the address')
        new = (new or '').strip()
        if saved and new == contact:
            st.info('That address is already saved.')
        elif saved:
            if re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', new):
                core.save_setting(sec_contact=new)
                st.success('Saved.')
            else:
                st.error('That doesn\'t look like an email address.')
    st.divider()

    st.subheader('Monthly check')
    st.write('For every company you follow: fresh figures and price, the analysis re-run when a new annual report is '
             'out, and a journal note when the price crosses your buy-below price. It runs when you open the program '
             f'and a month has passed (next: {core.next_check_date():%d %b %Y}); you see it run at the top of the page.')
    if not core.data_ready():
        st.caption(core.NOT_READY)
    if st.button('Run the monthly check now', type='primary', disabled=not core.data_ready()):
        with st.spinner('Checking the companies you follow...'):
            out, err = core.run_check()
        data.changed()
        if err:
            st.error(err)
    show_check(core.settings().get('last_check_result'))

    st.divider()
    st.subheader('Prices for the whole screener')
    n = len(core.load_screen())
    st.write(f'Today\'s prices and exchange rates for all {n or "the"} companies in the screener, then the 10 checks '
             'again (the "reasonable price" check depends on the price). Takes 5–10 minutes. Your candidates show the '
             'same new prices.')
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
             f'{core.KEEP_BACKUPS} are kept, {core.KEEP_BACKUPS_SYNCED} when the folder is in Google Drive or similar, '
             f'in the "backups" folder). Now and then, also keep a copy somewhere off '
             'this laptop, like a USB stick.')
    st.download_button('Download a backup', core.backup_bytes,  # made only when pressed, not on every page load
                       file_name=f'stock-screener-backup-{date.today()}.zip',
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

    st.divider()
    data_folder_part()
    st.divider()
    summary_part()
    st.divider()
    quit_button('quit_update')
    st.caption('Closing the program\'s last window stops it too.')


def quit_button(key):
    """Stop the program (closing its last window does that too)."""
    if st.button('Quit the program', icon=':material/power_settings_new:', key=key):
        import signal
        import threading
        import datafolder
        st.info('The program has stopped. You can close this window.')
        datafolder.release(core.DATA)
        threading.Timer(1.0, lambda: os.kill(os.getpid(), signal.SIGTERM)).start()


def data_folder_part():
    import datafolder
    st.subheader('Your data on two computers')
    st.write(f'Your work is in **{core.DATA}**. To use it on a second computer, keep it in a folder that Google Drive '
             'for desktop (or OneDrive, Dropbox) syncs, and point the program on both computers at it.')
    with st.expander('How it works, step by step'):
        st.markdown(
            '1. On **both** computers, install **Google Drive for desktop** (google.com/drive/download) and sign in '
            'with the same Google account. It adds a "Google Drive" drive (on Windows usually **G:**, with a folder '
            '"My Drive"; on a Mac under Locations in Finder).\n'
            '2. On the computer that has your data now: below, pick the Google Drive folder and press **Move my data '
            'there**. Then restart the program.\n'
            '3. Wait until Google Drive has synced (its icon in the taskbar or menu bar stops turning).\n'
            '4. On the other computer: install this program, pick the same Google Drive folder below, press **Use the '
            'data that is already there**, and restart the program.\n\n'
            'Use the program on **one computer at a time**, and quit it (the Quit button at the bottom of this page) before switching. If '
            'the other computer still has it open, the program warns you at the top of the page.')
    found = datafolder.cloud_folders()
    opts = [p for _, p in found] + ['Another folder...']
    labels = {p: label for label, p in found}
    pick = st.selectbox('Folder to keep your data in', opts, format_func=lambda p: labels.get(p, p),
                        help='The program makes a "StockScreener data" folder inside it.')
    folder = st.text_input('Folder', placeholder=r'for example G:\My Drive') if pick == 'Another folder...' else pick
    if not found:
        st.caption('No Google Drive, OneDrive or Dropbox folder found on this computer. Install Google Drive for '
                   'desktop first, or type a folder.')
    a, b = st.columns(2)
    if a.button('Move my data there', type='primary', disabled=not folder):
        try:
            dst = datafolder.move(folder)
            core.RESTART_NEEDED = (f'Your data is copied to {dst}. The old folder ({core.DATA}) stays as a spare copy; '
                                   'you can delete it once all works.')
            st.rerun()
        except (ValueError, OSError) as e:
            st.error(str(e))
    if b.button('Use the data that is already there', disabled=not folder):
        try:
            dst = datafolder.use(folder)
            core.RESTART_NEEDED = (f'This computer now uses {dst}. The data that was on this computer stays in '
                                   f'{core.DATA}, untouched, as a spare copy.')
            st.rerun()
        except (ValueError, OSError) as e:
            st.error(str(e))
    if core.DATA != datafolder.DEFAULT:
        if st.button('Go back to the folder on this computer only'):
            datafolder.back_to_default()
            core.RESTART_NEEDED = (f'After a restart this computer uses {datafolder.DEFAULT} again. Your data in '
                                   f'{core.DATA} stays where it is; copy it back with a backup if you need it.')
            st.rerun()


def summary_part():
    import phone_view
    st.subheader('A summary to read elsewhere')
    st.write('A PDF of your candidates, scoreboard, course progress and latest journal entries, as of now. It is made '
             'only when you press the button and saved only where you choose. Your real holdings and amounts are left '
             'out unless you tick the box.')
    real = st.checkbox('Include my real holdings and amounts')
    if st.button('Make the summary', icon=':material/picture_as_pdf:'):
        with st.spinner('Making the summary (it fetches today\'s prices)...'):
            try:
                st.session_state['summary_pdf'] = phone_view.pdf_bytes(include_real=real)
            except Exception as e:
                st.error(f'Could not make it: {e}')
    if st.session_state.get('summary_pdf'):
        st.download_button('Download the summary', st.session_state['summary_pdf'],
                           file_name=f'stock-screener-summary-{date.today()}.pdf', mime='application/pdf',
                           icon=':material/download:')

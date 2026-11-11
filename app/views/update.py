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

    st.divider()
    data_folder_part()
    st.divider()
    phone_part()


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
            'Use the program on **one computer at a time**, and quit it (button on the left) before switching. If '
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
            st.success(f'Your data is copied to {dst}. Quit the program (button on the left) and start it again to use it. '
                       f'The old folder ({core.DATA}) stays as a spare copy; you can delete it once all works.')
        except (ValueError, OSError) as e:
            st.error(str(e))
    if b.button('Use the data that is already there', disabled=not folder):
        try:
            dst = datafolder.use(folder)
            st.success(f'This computer now uses {dst}. Quit the program (button on the left) and start it again.')
        except (ValueError, OSError) as e:
            st.error(str(e))
    if core.DATA != datafolder.DEFAULT:
        if st.button('Go back to the folder on this computer only'):
            datafolder.back_to_default()
            st.success(f'After a restart this computer uses {datafolder.DEFAULT} again. Your data in {core.DATA} stays '
                       'where it is; copy it back with a backup (above) if you need it.')


def phone_part():
    import phone
    import phone_view
    from streamlit import config
    st.subheader('On your phone')
    st.write('Two private ways, nothing is put on the internet: the **full program** over Tailscale (a free private '
             'network of only your own devices) while this computer is on, and a **read-only phone view** (a PDF) in '
             'your data folder that you can open in the Google Drive app, also when the computer is off.')

    st.markdown('**The full program on your phone**')
    ip = phone.address()
    listening = config.get_option('server.address')
    if ip and listening == ip:
        full, plain = phone.phone_link()
        st.success(f'Your phone can open the program now. In Safari on your phone (with Tailscale on), go to '
                   f'**{full}**' + (f' (or **{plain}**)' if plain != full else '') + '.', icon=':material/smartphone:')
    elif phone.enabled() and not ip:
        st.warning('Phone use is on, but Tailscale is not running or not signed in on this computer. Start Tailscale, '
                   'then quit the program and start it again.', icon=':material/wifi_off:')
    elif phone.enabled():
        st.info('Phone use is on. Quit the program (button on the left) and start it again to open it to your phone.')
    on = st.toggle('Let my phone open the program (over Tailscale only)', value=phone.enabled(),
                   help='Kept per computer. Takes effect when you start the program again.')
    if on != phone.enabled():
        phone.set_enabled(on)
        st.rerun()
    with st.expander('How to set it up, step by step'):
        st.markdown(
            '1. On this computer, install **Tailscale** (tailscale.com/download) and sign in. Use an account only you '
            'use: every device signed in to it can open the program.\n'
            '2. On your iPhone, install the **Tailscale** app from the App Store and sign in with the **same** account. '
            'Allow it to add a VPN configuration when iOS asks.\n'
            '3. Turn on the switch above, then quit the program (button on the left) and start it again.\n'
            '4. If Windows asks whether to allow the program on networks, tick **both** boxes (private and public) and '
            'allow it. Tailscale\'s network can count as "public" on Windows. The program listens only on its '
            'Tailscale address, so your Wi-Fi and the internet still can\'t reach it.\n'
            '5. On your iPhone: switch Tailscale on, open Safari, go to the address shown above, then Share → '
            '**Add to Home Screen**, so it opens like an app.\n\n'
            'The computer must be **on and awake** with the program running. With phone use on, closing the window '
            'here does not stop the program; use **Quit** on the left. To use it while you are away, set this '
            'computer not to sleep (Windows: Settings → System → Power → Sleep: Never, when plugged in).')

    st.markdown('**The read-only phone view**')
    pdf = phone_view.path()
    try:
        from datetime import datetime
        made = datetime.fromtimestamp(os.path.getmtime(pdf))
        st.write(f'**{phone.PDF_NAME}** in your data folder, last made {made:%d %b %Y, %H:%M}. A fresh copy is made '
                 'every 10 minutes while the program runs. It shows your candidates, the scoreboard, your No and Wait '
                 'decisions, course progress and the latest journal entries, with prices as of when it was made.')
    except OSError:
        st.write(f'**{phone.PDF_NAME}** is made in your data folder every 10 minutes while the program runs.')
    import datafolder
    if core.DATA == datafolder.DEFAULT:
        st.caption('Your data folder is on this computer only, so your phone can\'t see the PDF yet. Move your data to '
                   'Google Drive (above) to read it in the Google Drive app.')
    else:
        st.caption(f'On your phone: Google Drive app → the "{datafolder.NAME}" folder → {phone.PDF_NAME}. Tip: star it '
                   '(⋯ → Add to Starred) to find it quickly.')
    if st.button('Make the phone view now', icon=':material/picture_as_pdf:'):
        with st.spinner('Making the phone view (it fetches today\'s prices)...'):
            try:
                phone_view.write()
                st.success('Done.')
            except Exception as e:
                st.error(f'Could not make it: {e}')

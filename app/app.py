"""The Stock Screener, as a program on your laptop. The installed app starts it through desktop.py."""
import os
from datetime import date

import streamlit as st

import core
from views import candidates, course, guide, home, journal, portfolio_page, reports, scoreboard, screener, update

# the sidebar starts closed: it holds only the monthly check's date and Quit, and the pages get the full width
st.set_page_config(page_title='Stock Screener', page_icon=':material/query_stats:', layout='wide',
                   initial_sidebar_state='collapsed')
st.html('<style>' + open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'style.css'), encoding='utf-8').read()
        + '</style>')

PAGES = {
    'home': st.Page(home.render, title='Start here', icon=':material/home:', url_path='home', default=True),
    # second, so it stays in view when the bar folds pages into "more" (a small screen, or zoomed in)
    'guide': st.Page(guide.render, title='How to use it', icon=':material/school:', url_path='guide'),
    'candidates': st.Page(candidates.render, title='Candidates', icon=':material/star:', url_path='candidates'),
    'screener': st.Page(screener.render, title='Screener', icon=':material/filter_alt:', url_path='screener'),
    'journal': st.Page(journal.render, title='Journal', icon=':material/edit_note:', url_path='journal'),
    'course': st.Page(course.render, title='Course', icon=':material/menu_book:', url_path='course'),
    'scoreboard': st.Page(scoreboard.render, title='Scoreboard', icon=':material/scoreboard:', url_path='scoreboard'),
    # your own data: what you hold, the reports you add, and getting fresh data
    'portfolio': st.Page(portfolio_page.render, title='Portfolio', icon=':material/account_balance:', url_path='portfolio'),
    'reports': st.Page(reports.render, title='Add a report', icon=':material/upload_file:', url_path='reports'),
    'update': st.Page(update.render, title='Update data', icon=':material/sync:', url_path='update'),
}
MY_DATA = ('portfolio', 'reports', 'update')
st.session_state['pages'] = PAGES

# Only this program's own window may drive it: Streamlit trusts any page on this computer ("localhost" on any port),
# so a page served by another program on this computer is stopped here.
_origin = (st.context.headers or {}).get('Origin') or ''
_port = st.get_option('server.port')
if _origin and _origin not in (f'http://127.0.0.1:{_port}', f'http://localhost:{_port}'):
    st.error('This program only answers its own window.')
    st.stop()
# the pages you use for picking stay in the top bar ("How to use it" second, so always in view); your own data is one menu
page = st.navigation({'': [p for k, p in PAGES.items() if k not in MY_DATA],
                      'My data': [PAGES[k] for k in MY_DATA]}, position='top')

# after the data folder moved, nothing may be written to the old one: every page waits for the restart
if core.RESTART_NEEDED:
    from views import update as _u
    st.warning(core.RESTART_NEEDED + ' Quit the program now and start it again; until then nothing can be changed, so '
               'nothing is written to the old folder.', icon=':material/restart_alt:')
    _u.quit_button('quit_restart')
    st.stop()

# The first start counts as a check (the data in the download is fresh, and a company you add is analysed there and
# then).
if 'last_check' not in core.settings():
    core.save_setting(last_check=date.today().isoformat())

with st.sidebar:
    # the margin of safety is set on the Candidates page, next to the prices it changes
    st.markdown('### Monthly check')
    st.caption(f"Keeps the companies you follow up to date. Next: when you open the program on or after "
               f"{core.next_check_date():%d %b %Y}. You can also run it now: My data, Update data, Refresh now.")
    st.divider()
    update.quit_button('quit_side')
    st.caption(core.DISCLAIMER)

@st.fragment(run_every=5)
def first_download_banner():
    """While the first start fetches prices: where it is, and the whole page refreshes once it is done."""
    import jobs
    s = jobs.running()
    if s and s.get('kind') == 'first':
        st.info(f"Getting today's prices and the second-source figures from Yahoo Finance: step {s['step']} of "
                f"{s['steps']}, {s['step_name']}. This happens only the first time and takes a while; the screener "
                'shows the figures that came with the program meanwhile. Analysing a company waits until it is done.',
                icon=':material/download:')
        st.session_state['first_seen'] = True
    elif st.session_state.pop('first_seen', False):
        from views import data
        data.changed()
        st.rerun(scope='app')
    elif core.first_download_needed():
        st.warning('Getting today\'s prices stopped before it finished (no internet?). It starts again the next time '
                   'you open the program, or now:', icon=':material/wifi_off:')
        if st.button('Try again', key='first_retry'):
            jobs.start('first')
            st.rerun(scope='app')


def one_computer_at_a_time():
    """With your data in Google Drive (or similar): when the other computer has it open, nothing can be changed here
    until it is closed there (used on both at once, changes from one overwrite the other). Otherwise this computer notes
    that it has the data open, every 5 minutes for as long as the program runs."""
    import datafolder
    if st.session_state.get('took_over'):
        datafolder.keep_marked(core.DATA)
        return
    other = datafolder.other_user(core.DATA)
    if not other:
        datafolder.mark_in_use(core.DATA)
        datafolder.keep_marked(core.DATA)
        return
    st.title('Your data is open on another computer')
    st.warning(f"**{other[0]}** has had your data open, last seen {other[1]:%d %B at %H:%M}. Used on two computers at once, "
               'changes from one overwrite the other, so nothing can be changed here until it is closed there.',
               icon=':material/devices:')
    st.write('Close the program on the other computer (Quit), wait a minute for Google Drive to sync, and press **Check '
             'again**. If that computer is off or the program there crashed, take over: its note expires by itself '
             'after 15 minutes anyway.')
    a, b, c = st.columns(3)
    if a.button('Check again', type='primary'):
        st.rerun()
    if b.button('Take over: it is closed there'):
        datafolder.mark_in_use(core.DATA)
        st.session_state['took_over'] = True
        st.rerun()
    with c:
        update.quit_button('quit_other')
    st.stop()


one_computer_at_a_time()

# once per session: a backup a day, and after an update, your own reports are read into the new version's screener
if not st.session_state.get('started'):
    st.session_state['started'] = True
    core.backup_if_due()
    version = core.program_version()
    before = core.settings()
    # for Start here: when you were last here, and whether the program was updated since
    st.session_state['last_seen'] = before.get('last_seen')
    if before.get('program_version') and before['program_version'] != version:
        st.session_state['updated_from'] = before['program_version']
    core.save_setting(last_seen=date.today().isoformat())
    import jobs
    if core.first_download_needed() and not jobs.running() and not os.environ.get('STOCK_NO_FIRST_DOWNLOAD'):
        jobs.start('first')  # it reads your own reports in too
    elif core.settings().get('program_version') != version and os.listdir(core.USER_REPORTS):
        jobs.start('after_restore')
    core.save_setting(program_version=version)
    core.migrate()  # one-time fixes to data saved by older versions
    try:  # claims whose target year's figures have come in are checked now
        import claims
        if claims.check_all():
            st.cache_data.clear()
    except Exception as e:
        print('checking claims:', e)

if not core.data_ready():
    first_download_banner()
# the monthly check: once per session, when a month has passed and something is being followed
if (not st.session_state.get('checked') and core.data_ready() and core.check_due()
        and any(e['mode'] == 'watch' and not e.get('hidden') for e in core.watchlist())):
    st.session_state['checked'] = True
    with st.status('Monthly check: updating the companies you follow...', expanded=True) as box:
        out, err = core.run_check()
        if err:
            box.update(label=f'Monthly check could not finish: {err}. It will try again next time.', state='error')
        else:
            n = len(out['events'])
            box.update(label=f"Monthly check done: {len(out['checked'])} companies checked, "
                             f"{n} change{'s' if n != 1 else ''} noted in the journal.", state='complete')
            core.show_check_result(out, box)
            st.cache_data.clear()

page.run()

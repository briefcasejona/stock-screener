"""The Stock Screener, as a program on your laptop. The installed app starts it through desktop.py."""
import os
from datetime import date, timedelta

import streamlit as st

import core
from views import candidates, course, guide, journal, reports, scoreboard, screener, update

st.set_page_config(page_title='Stock Screener', page_icon=':material/query_stats:', layout='wide')
st.html('<style>' + open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'style.css'), encoding='utf-8').read()
        + '</style>')

PAGES = {
    'candidates': st.Page(candidates.render, title='Candidates', icon=':material/star:', url_path='candidates', default=True),
    'scoreboard': st.Page(scoreboard.render, title='Scoreboard', icon=':material/scoreboard:', url_path='scoreboard'),
    'screener': st.Page(screener.render, title='Screener', icon=':material/filter_alt:', url_path='screener'),
    'course': st.Page(course.render, title='Course', icon=':material/menu_book:', url_path='course'),
    'journal': st.Page(journal.render, title='Journal', icon=':material/edit_note:', url_path='journal'),
    'reports': st.Page(reports.render, title='Add a report', icon=':material/upload_file:', url_path='reports'),
    'update': st.Page(update.render, title='Update data', icon=':material/sync:', url_path='update'),
    'guide': st.Page(guide.render, title='How to use it', icon=':material/school:', url_path='guide'),
}
st.session_state['pages'] = PAGES
page = st.navigation(list(PAGES.values()), position='top')

with st.sidebar:
    st.markdown('### Margin of safety')
    m = st.segmented_control('Margin of safety', core.MARGINS, default=core.margin(), format_func=lambda v: f'{v}%',
                             key='margin_pick', label_visibility='collapsed', required=True)
    if m != core.margin():
        core.save_setting(margin=m)
    st.caption('Buy-below = base value minus this margin. A bigger margin protects you more when your growth '
               'rates turn out too hopeful.')
    st.divider()
    s = core.settings()
    st.markdown('### Weekly check')
    nxt = date.fromisoformat(s['last_check']) + timedelta(days=7) if s.get('last_check') else date.today()
    st.caption(f"Keeps the companies you follow up to date. Next: when you open the program on or after "
               f"{nxt:%d %b %Y}. You can also run it on the Update data page.")
    st.divider()
    if st.button('Quit the program', icon=':material/power_settings_new:'):
        import signal
        import threading
        st.info('The program has stopped. You can close this window.')
        threading.Timer(1.0, lambda: os.kill(os.getpid(), signal.SIGTERM)).start()
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


# once per session: a backup a day, and after an update, your own reports are read into the new version's screener
if not st.session_state.get('started'):
    st.session_state['started'] = True
    core.backup_if_due()
    version = core.program_version()
    import jobs
    if core.first_download_needed() and not jobs.running() and not os.environ.get('STOCK_NO_FIRST_DOWNLOAD'):
        jobs.start('first')  # it reads your own reports in too
    elif core.settings().get('program_version') != version and os.listdir(core.USER_REPORTS):
        jobs.start('after_restore')
    core.save_setting(program_version=version)
    try:  # claims whose target year's figures have come in are checked now
        import claims
        if claims.check_all():
            st.cache_data.clear()
    except Exception as e:
        print('checking claims:', e)

# The first start counts as a weekly check (the data in the download is fresh, and a company you add is analysed
# there and then).
if 'last_check' not in core.settings():
    core.save_setting(last_check=date.today().isoformat())
if not core.data_ready():
    first_download_banner()
# the weekly check: once per session, when a week has passed and something is being followed
if (not st.session_state.get('checked') and core.data_ready() and core.weekly_check_due()
        and any(e['mode'] == 'watch' for e in core.watchlist())):
    st.session_state['checked'] = True
    with st.status('Weekly check: updating the companies you follow...', expanded=False) as box:
        out, err = core.run_weekly_check()
        if err:
            box.update(label=f'Weekly check could not finish: {err}. It will try again next time.', state='error')
        else:
            n = len(out['events'])
            box.update(label=f"Weekly check done: {len(out['checked'])} companies checked, "
                             f"{n} change{'s' if n != 1 else ''} noted in the journal.", state='complete')
            st.cache_data.clear()

page.run()

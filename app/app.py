"""The Stock Screener, as a program on your laptop. The installed app starts it through desktop.py."""
import os
from datetime import date, timedelta

import streamlit as st

import core
from views import candidates, guide, journal, reports, screener, update

st.set_page_config(page_title='Stock Screener', page_icon=':material/query_stats:', layout='wide')

PAGES = {
    'candidates': st.Page(candidates.render, title='Candidates', icon=':material/star:', url_path='candidates', default=True),
    'screener': st.Page(screener.render, title='Screener', icon=':material/filter_alt:', url_path='screener'),
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

# once per session: a backup a day, and after an update, your own reports are read into the new version's screener
if not st.session_state.get('started'):
    st.session_state['started'] = True
    core.backup_if_due()
    version = core.program_version()
    if core.settings().get('program_version') != version:
        if os.listdir(core.USER_REPORTS):
            import jobs
            jobs.start('after_restore')
        core.save_setting(program_version=version)

# The first start counts as a weekly check (the data in the download is fresh, and a company you add is analysed
# there and then).
if 'last_check' not in core.settings():
    core.save_setting(last_check=date.today().isoformat())
# the weekly check: once per session, when a week has passed and something is being followed
if not st.session_state.get('checked') and core.weekly_check_due() and any(e['mode'] == 'watch' for e in core.watchlist()):
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

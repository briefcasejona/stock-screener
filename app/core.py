"""Everything the pages share: where the data lives, reading it, and running the screener's and playbook's code.

The program folder holds app/ (this code), screener/ and playbook/ (the same code and data as in the project),
and cache/ (downloads that can always be fetched again). Nothing here talks to Claude: it is all local.
"""
import argparse
import contextlib
import io
import json
import os
import re
import subprocess
import sys
from datetime import date

APP = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get('STOCK_ROOT', os.path.dirname(APP))
SCREENER = os.path.join(ROOT, 'screener')
PLAYBOOK = os.path.join(ROOT, 'playbook')
CACHE = os.path.join(ROOT, 'cache')
# Your own work lives outside the program folder, so replacing the program with a newer version can't touch it
DATA = os.environ.get('STOCK_DATA', os.path.join(os.path.expanduser('~'), 'StockScreener data'))
JOURNAL_DIR = os.path.join(DATA, 'journal')
USER_REPORTS = os.path.join(DATA, 'user_reports')
PDF_MAPS = os.path.join(DATA, 'pdf_maps')
ADDED = os.path.join(DATA, 'added_companies.csv')
SETTINGS = os.path.join(DATA, 'settings.json')
BACKUPS = os.path.join(DATA, 'backups')
KEEP_BACKUPS = 20
MARGINS = (5, 10, 20, 30)
DISCLAIMER = 'Educational, not personal financial advice.'

# these must be set before the screener's code is imported (and the scripts it runs inherit them)
os.environ.setdefault('SEC_CACHE', os.path.join(CACHE, 'sec'))
os.environ.setdefault('ESEF_CACHE', os.path.join(CACHE, 'esef'))
os.environ.setdefault('WATCHLIST_AUTHOR', 'The program')
os.environ['WATCHLIST_DIR'] = JOURNAL_DIR
os.environ['USER_REPORTS_DIR'] = USER_REPORTS
os.environ['PDF_MAPS_DIR'] = PDF_MAPS
os.environ['ADDED_COMPANIES'] = ADDED
for p in (os.path.join(PLAYBOOK, 'code'), os.path.join(SCREENER, 'code')):
    if p not in sys.path:
        sys.path.insert(0, p)
import localdata  # noqa: E402


def prepare_data():
    """The first time: start your data folder from the journal and watchlist that come with the program
    (the worked example). After that the folder is yours and a newer program version never changes it."""
    import shutil
    if not os.path.isdir(JOURNAL_DIR):
        tmp = JOURNAL_DIR + '.new'
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.copytree(os.path.join(PLAYBOOK, 'journal'), tmp,
                        ignore=lambda d, names: [n for n in names if n == 'app_settings.json'])
        os.replace(tmp, JOURNAL_DIR)
    for d in (os.path.join(JOURNAL_DIR, 'analyses'), USER_REPORTS, PDF_MAPS, BACKUPS):
        os.makedirs(d, exist_ok=True)


prepare_data()


def program_version():
    """When this copy of the program was put together (make_package.py writes it)."""
    try:
        return open(os.path.join(APP, 'VERSION'), encoding='utf-8').read().strip()
    except OSError:
        return 'development'


# ---------- settings ----------

def settings():
    try:
        return json.load(open(SETTINGS, encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def save_setting(**kw):
    localdata.write_json(SETTINGS, settings() | kw, indent=1)
    if 'sec_contact' in kw:  # the scripts started from now on send it to the SEC
        os.environ['SEC_CONTACT'] = kw['sec_contact']


if settings().get('sec_contact'):
    os.environ['SEC_CONTACT'] = settings()['sec_contact']


def margin():
    m = settings().get('margin', 30)
    return m if m in MARGINS else 30


# ---------- data ----------

def mtime(*paths):
    """A number that changes whenever one of the files changes (for caching)."""
    return sum(os.path.getmtime(p) for p in paths if os.path.exists(p))


def data_stamp():
    j = JOURNAL_DIR
    files = [f'{j}/watchlist.json', f'{j}/journal.json', f'{PLAYBOOK}/output/asml_example.json']
    if os.path.isdir(f'{j}/analyses'):
        files += [f'{j}/analyses/{f}' for f in os.listdir(f'{j}/analyses')]
    return mtime(*files)


def load_dashboard():
    """candidates, scenarios, checks, history, journal: the same five datasets as the online dashboard."""
    import build_dashboard_data
    return build_dashboard_data.build()


def load_screen():
    path = f'{SCREENER}/dashboard/screen.json'
    return json.load(open(path, encoding='utf-8')) if os.path.exists(path) else []


def watchlist():
    path = f'{JOURNAL_DIR}/watchlist.json'
    return json.load(open(path, encoding='utf-8')) if os.path.exists(path) else []


def reviewed(cand):
    """Growth rates someone chose after reading the annual report (the worked example's were)."""
    src = cand.get('assumptions_source', '')
    return 'reviewed' in src or 'worked example' in src


def buy_below(cand, m):
    return cand['base'] * (1 - m / 100)


def decision(cand, m):
    """The playbook's decision at a margin of safety: buy only with reviewed growth rates."""
    if cand['price'] <= buy_below(cand, m):
        return 'Buy' if reviewed(cand) else 'Deep dive'
    return 'Wait'


def money(v, cur):
    if v is None:
        return 'n/a'
    sym = {'EUR': '€', 'USD': '$', 'GBP': '£'}.get(cur)
    txt = f'{v:,.2f}' if abs(v) < 100 else f'{v:,.0f}'
    return f'{sym}{txt}' if sym else f'{cur} {txt}'


def data_notes(text):
    """The screener's notes on a company's data as separate sentences ("a; b; c" in the files), readable in full."""
    out = []
    for part in (text or '').split('; '):
        part = part.strip()
        if not part:
            continue
        if out and part.startswith('the larger is used'):  # one note that itself contains "; "
            out[-1] += '; ' + part
            continue
        part = re.sub(r'\b1 years\b', '1 year', part)
        out.append(part[:1].upper() + part[1:])
    return out


def show_notes(text, st):
    """Show the notes as a short list under a heading, or nothing when there are none."""
    notes = data_notes(text)
    if notes:
        st.markdown('**Notes on the data**\n\n' + '\n'.join(f'- {n}' for n in notes))


def pct(v, nd=1):
    return 'n/a' if v is None else f'{v:.{nd}%}'


def add_journal_entry(entry):
    """Append one entry to the decision journal (entries are never edited)."""
    path = f'{JOURNAL_DIR}/journal.json'
    entries = json.load(open(path, encoding='utf-8')) if os.path.exists(path) else []
    base_id = f"{entry['date']}-{entry['ticker']}"
    n = sum(1 for e in entries if e['id'].startswith(base_id))
    entry = {'id': base_id if not n else f'{base_id}-{n + 1}', **{k: v for k, v in entry.items() if k != 'ticker'}}
    entries.append(entry)
    localdata.write_json(path, entries, indent=1)
    return entry


# ---------- the watchlist (playbook/code/watchlist.py, called directly) ----------

def _ns(**kw):
    base = dict(ticker=None, bear=None, base=None, bull=None, normalised=False, average=False, reviewed=False,
                once=False, name=None)
    return argparse.Namespace(**(base | kw))


def wl(cmd, **kw):
    """Run a watchlist command. Returns (result, error message). Its printed output is kept out of the way."""
    if cmd in ('add', 'set', 'check') and not data_ready():
        return None, NOT_READY
    import watchlist as w
    fn = {'add': w.cmd_add, 'set': w.cmd_set, 'remove': w.cmd_remove, 'check': w.cmd_check,
          'watch': lambda a: w.cmd_mode(a, 'watch'), 'once': lambda a: w.cmd_mode(a, 'once')}[cmd]
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            return fn(_ns(**kw)), None
    except SystemExit as e:
        return None, str(e)
    except Exception as e:  # shown to the user as it is
        return None, f'{type(e).__name__}: {e}'


def weekly_check_due():
    last = settings().get('last_check')
    return not last or (date.today() - date.fromisoformat(last)).days >= 7


def run_weekly_check():
    out, err = wl('check')
    if out is not None:
        save_setting(last_check=out['at'], last_check_result=out)
        try:  # new annual reports may settle claims
            import claims
            claims.check_all()
        except Exception as e:
            print('checking claims:', e)
    return out, err


# ---------- running the screener's scripts ----------

python_cmd = localdata.python_cmd


def stream(cmd):
    """Run a command and yield its output line by line; the last item is its exit code."""
    env = os.environ | {'PYTHONUNBUFFERED': '1'}
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8',
                         errors='replace', env=env, cwd=ROOT, **localdata.hidden())
    for line in p.stdout:
        yield line.rstrip('\n')
    yield p.wait()


S = lambda name: os.path.join(SCREENER, 'code', name)
# the screener's steps, in the order the screener's README gives
STEPS = {
    'prices_us': ('US share prices', python_cmd(S('prices.py'), 'us')),
    'prices_eu': ('European share prices', python_cmd(S('prices.py'), 'eu')),
    'fetch_sec': ('US company figures from the SEC', python_cmd(S('fetch_sec.py'))),
    'extract_us': ('US yearly figures', python_cmd(S('extract_sec.py'), 'us')),
    'extract_eu': ('European yearly figures', python_cmd(S('extract_esef.py'))),
    'fx_eu': ('Exchange rates', python_cmd(S('fx.py'), 'eu')),
    'cross_us': ('Second-source check, US', python_cmd(S('crosscheck_yahoo.py'), 'us')),
    'cross_eu': ('Second-source check, Europe', python_cmd(S('crosscheck_yahoo.py'), 'eu')),
    'screen_us': ('The 10 checks, US', python_cmd(S('screen.py'), 'us')),
    'screen_eu': ('The 10 checks, Europe', python_cmd(S('screen.py'), 'eu')),
    'build': ('Screener table', python_cmd(S('build_screen_data.py'))),
}
PRICES_ONLY = ['prices_us', 'prices_eu', 'fx_eu', 'screen_us', 'screen_eu', 'build']
FULL = ['fetch_sec', 'prices_us', 'extract_us', 'cross_us', 'screen_us',
        'prices_eu', 'extract_eu', 'fx_eu', 'cross_eu', 'screen_eu', 'build']
AFTER_REPORT = ['prices_eu', 'extract_eu', 'fx_eu', 'cross_eu', 'screen_eu', 'build']
# Prices, exchange rates and the second-source figures come from Yahoo, so they are not in the download: each copy of
# the program fetches them on its first start (and keeps them when it updates itself, see desktop.program_root).
FIRST_DOWNLOAD = ['prices_us', 'prices_eu', 'fx_eu', 'cross_us', 'cross_eu', 'screen_us', 'screen_eu', 'build']
DOWNLOADED = ['raw/prices_us.csv', 'raw/prices_eu.csv', 'raw/splits_us.json', 'raw/splits_eu.json', 'raw/fx.json',
              'raw/yahoo_statements_us.json', 'raw/yahoo_statements_eu.json',
              'output/crosscheck_us.csv', 'output/crosscheck_eu.csv']
NOT_READY = ('The program is still getting today\'s prices and the second-source figures (only the first time it '
             'starts). You can do this as soon as that is done; the progress is on the Update data page.')


def first_download_needed():
    """True when a downloaded file is missing, or the first download stopped before it finished."""
    import jobs
    s = jobs.status() or {}
    if s.get('kind') == 'first' and s.get('state') != 'done':
        return True
    return not all(os.path.exists(os.path.join(SCREENER, f)) for f in DOWNLOADED)


def data_ready():
    """Analysing a company and the weekly check need the downloaded prices."""
    import jobs
    live = jobs.running()
    if live and live.get('kind') == 'first':
        return False
    return not first_download_needed()


def clear_for_full_refresh():
    """Make a full refresh fetch what may have changed: company facts older than a week, the ESEF filing
    lists (new reports show up there) and the second-source statements."""
    import time
    sec = os.environ['SEC_CACHE']
    if os.path.isdir(sec):
        for f in os.listdir(sec):
            if time.time() - os.path.getmtime(os.path.join(sec, f)) > 7 * 86400:
                os.remove(os.path.join(sec, f))
    for name in ('raw/esef_filings_eu.json', 'raw/yahoo_statements_us.json', 'raw/yahoo_statements_eu.json'):
        path = os.path.join(SCREENER, name)
        if os.path.exists(path):
            os.replace(path, path + '.previous')


def restore_after_failed_refresh():
    for name in ('raw/esef_filings_eu.json', 'raw/yahoo_statements_us.json', 'raw/yahoo_statements_eu.json'):
        path = os.path.join(SCREENER, name)
        if not os.path.exists(path) and os.path.exists(path + '.previous'):
            os.replace(path + '.previous', path)


# ---------- your own reports (screener/code/user_reports.py) ----------

def universe():
    import csv
    out = {}
    for u in csv.DictReader(open(f'{SCREENER}/raw/universe_us.csv', encoding='utf-8')):
        out[u['ticker']] = {'name': u['name'], 'region': 'us'}
    for u in localdata.eu_universe():
        out[u['ticker']] = {'name': u['name'], 'region': 'eu'}
    return out


def user_report_cmd(*args):
    """Run user_reports.py and return (exit code, output)."""
    lines = list(stream(python_cmd(S('user_reports.py'), *args)))
    return lines[-1], '\n'.join(lines[:-1])


def own_reports():
    import glob
    out = []
    for p in sorted(glob.glob(f'{USER_REPORTS}/*/*.json')):
        d = json.load(open(p, encoding='utf-8'))
        out.append({'Company': d['ticker'], 'Year end': d['period_end'], 'Kind': d['kind'].upper(),
                    'File': d['source_file'], 'Added': d['added'], 'Figures': len(d['facts'])})
    return out


# ---------- backups ----------

BACKUP_PARTS = ['journal', 'user_reports', 'pdf_maps', 'added_companies.csv', 'settings.json', 'portfolio.json',
                'claims.json', 'commitments.json', 'course.json']
MAX_RESTORE = 500 * 2**20  # a backup that unpacks to more than this is not one of ours


def backup_bytes():
    """Your data folder (without the backups themselves) as a zip."""
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        for part in BACKUP_PARTS:
            full = os.path.join(DATA, part)
            if os.path.isfile(full):
                z.write(full, part)
            for d, _, files in os.walk(full):
                for f in files:
                    if not f.endswith('.tmp'):
                        p = os.path.join(d, f)
                        z.write(p, os.path.relpath(p, DATA).replace(os.sep, '/'))
    return buf.getvalue()


def save_backup(why='automatic'):
    """Write a dated backup into the backups folder and keep the newest ones."""
    from datetime import datetime
    name = f"backup {datetime.now().strftime('%Y-%m-%d %H%M%S')} {why}.zip"
    path = os.path.join(BACKUPS, name)
    data = backup_bytes()
    tmp = path + '.tmp'
    with open(tmp, 'wb') as fh:
        fh.write(data)
    os.replace(tmp, path)
    old = sorted(f for f in os.listdir(BACKUPS) if f.startswith('backup ') and f.endswith('.zip'))
    for f in old[:-KEEP_BACKUPS]:
        os.remove(os.path.join(BACKUPS, f))
    return path


def backup_if_due():
    """One automatic backup a day, made when the program starts."""
    today = date.today().isoformat()
    if not any(f.startswith(f'backup {today}') for f in os.listdir(BACKUPS)):
        return save_backup()


def restore_backup(file):
    """Put a backup zip back into the data folder; a safety backup of what is there now is made first.
    Returns (number of files, path of the safety backup)."""
    import zipfile
    z = zipfile.ZipFile(file)
    infos = [i for i in z.infolist() if not i.is_dir()]
    allowed = lambda n: '..' not in n.split('/') and not n.startswith('/') and '\\' not in n and ':' not in n and any(
        n == p or n.startswith(p + '/') for p in BACKUP_PARTS)
    bad = [i.filename for i in infos if not allowed(i.filename)]
    if bad or not infos:
        raise ValueError('this is not a Stock Screener backup' + (f' ({bad[0]})' if bad else ''))
    if sum(i.file_size for i in infos) > MAX_RESTORE or len(infos) > 20000:
        raise ValueError('this backup is far bigger than a Stock Screener backup can be')
    for i in infos:  # read all of it first: a broken zip changes nothing
        z.read(i)
    safety = save_backup('before restore')
    for i in infos:
        dst = os.path.join(DATA, *i.filename.split('/'))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        tmp = dst + '.tmp'
        with open(tmp, 'wb') as out:
            out.write(z.read(i))
        os.replace(tmp, dst)
    return len(infos), safety

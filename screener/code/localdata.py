"""Where the user's own data lives, and saving files so that a crash can never leave half a file.

In the project everything sits in its usual place (playbook/journal, screener/user_reports, screener/pdf_maps,
screener/raw/universe_eu.csv). The laptop program keeps his data outside the program folder, so a newer version
can't delete it; it says where through these environment variables:
  WATCHLIST_DIR     journal, watchlist and analyses
  USER_REPORTS_DIR  annual reports he added
  PDF_MAPS_DIR      the line choices for his PDF reports
  ADDED_COMPANIES   companies he added that are not in the S&P 500 or STOXX 600 (same columns as universe_eu.csv)
"""
import csv
import json
import os
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # screener/
PLAYBOOK = os.path.join(os.path.dirname(BASE), 'playbook')
UNIVERSE_EU = f'{BASE}/raw/universe_eu.csv'
JOURNAL_DIR = os.environ.get('WATCHLIST_DIR', os.path.join(PLAYBOOK, 'journal'))
USER_REPORTS = os.environ.get('USER_REPORTS_DIR', f'{BASE}/user_reports')
PDF_MAPS = os.environ.get('PDF_MAPS_DIR', f'{BASE}/pdf_maps')
ADDED = os.environ.get('ADDED_COMPANIES', UNIVERSE_EU)


def python_cmd(script, *args):
    """The command line that runs one of the scripts: isolated (-I, nothing is imported from the current folder) and
    in UTF-8 mode (Windows would otherwise read the files as cp1252). In the installed app there is no separate
    Python: its helper program runs the script."""
    if getattr(sys, 'frozen', False):
        worker = os.path.join(os.path.dirname(sys.executable), 'stockscreener-worker' + ('.exe' if os.name == 'nt' else ''))
        return [worker if os.path.exists(worker) else sys.executable, '--run-script', script, *args]
    return [sys.executable, '-X', 'utf8', '-I', script, *args]


def hidden():
    """Keyword arguments that keep a started program's window out of sight on Windows."""
    return {'creationflags': 0x08000000} if os.name == 'nt' else {}  # CREATE_NO_WINDOW


def _replace(tmp, path):
    # Windows refuses the swap while another program (a virus scanner, OneDrive) has the file open: try again
    for i in range(20):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if i == 19:
                raise
            time.sleep(0.1)


def write_text(path, text, newline=None):
    """Write the whole file or nothing: a temporary file next to it, flushed to disk, then swapped in."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = f'{path}.{os.getpid()}.tmp'
    try:
        with open(tmp, 'w', encoding='utf-8', newline=newline) as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        _replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def write_json(path, obj, **kw):
    kw.setdefault('ensure_ascii', False)
    write_text(path, json.dumps(obj, **kw))


def write_csv(path, rows, fieldnames):
    import io
    buf = io.StringIO(newline='')
    w = csv.DictWriter(buf, fieldnames=fieldnames)
    w.writeheader()
    w.writerows(rows)
    write_text(path, buf.getvalue(), newline='')


def eu_universe():
    """The European list plus the companies the user added (when those are kept in their own file)."""
    rows = list(csv.DictReader(open(UNIVERSE_EU, encoding='utf-8')))
    if os.path.abspath(ADDED) != os.path.abspath(UNIVERSE_EU) and os.path.exists(ADDED):
        have = {r['ticker'] for r in rows}
        rows += [r for r in csv.DictReader(open(ADDED, encoding='utf-8')) if r['ticker'] not in have]
    return rows


def add_company(row):
    """Add a company to the list of companies the user added."""
    if os.path.abspath(ADDED) == os.path.abspath(UNIVERSE_EU) or os.path.exists(ADDED):
        rows = list(csv.DictReader(open(ADDED, encoding='utf-8')))
    else:
        rows = []
    fields = next(csv.reader(open(UNIVERSE_EU, encoding='utf-8')))
    rows.append({k: row.get(k, '') for k in fields})
    write_csv(ADDED, rows, fields)

"""Where your data lives, and using it from two computers.

Your data folder (journal, analyses, scoreboard, claims, course, settings, backups) is normally "StockScreener data" in
your home folder. You can move it into a folder that Google Drive for desktop (or OneDrive, Dropbox) keeps in sync; the
program on your other computer then points at the same folder.

The choice is kept in a small file in your home folder, outside the data, so each computer remembers its own path.
Use the program on one computer at a time: a note in the data folder ("in use.json") says which computer has it open,
and the other computer warns you.
"""
import glob
import json
import os
import platform
import shutil
from datetime import datetime, timedelta

HOME = os.path.expanduser('~')
DEFAULT = os.path.join(HOME, 'StockScreener data')
POINTER = os.path.join(HOME, '.stockscreener-data-folder')
NAME = 'StockScreener data'
LOCK = 'in use.json'
FRESH = timedelta(minutes=30)  # a note older than this is from a program that has stopped


def current():
    """The data folder this computer uses."""
    if os.environ.get('STOCK_DATA'):
        return os.environ['STOCK_DATA']
    try:
        p = open(POINTER, encoding='utf-8', errors='replace').read().strip()
        if p and os.path.isdir(p):
            return p
    except OSError:
        pass
    return DEFAULT


def cloud_folders():
    """Folders that Google Drive, OneDrive or Dropbox keep in sync on this computer, as [(label, path)]."""
    found = []
    if os.name == 'nt':
        import string
        for d in string.ascii_uppercase:
            for sub in ('My Drive', 'Mijn Drive'):
                p = f'{d}:\\{sub}'
                if os.path.isdir(p):
                    found.append((f'Google Drive ({p})', p))
    for p in sorted(glob.glob(os.path.join(HOME, 'Library', 'CloudStorage', 'GoogleDrive-*'))):
        for sub in ('My Drive', 'Mijn Drive'):
            if os.path.isdir(os.path.join(p, sub)):
                found.append(('Google Drive', os.path.join(p, sub)))
    for p in [os.environ.get('OneDrive')] + glob.glob(os.path.join(HOME, 'Library', 'CloudStorage', 'OneDrive*')):
        if p and os.path.isdir(p):
            found.append(('OneDrive', p))
    for p in (os.path.join(HOME, 'Dropbox'), *glob.glob(os.path.join(HOME, 'Library', 'CloudStorage', 'Dropbox*'))):
        if os.path.isdir(p):
            found.append(('Dropbox', p))
    seen, out = set(), []
    for label, p in found:
        if p not in seen:
            seen.add(p)
            out.append((label, p))
    return out


def has_data(folder):
    return any(os.path.exists(os.path.join(folder, f)) for f in ('journal', 'settings.json', 'portfolio.json'))


def _point(folder):
    tmp = POINTER + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        fh.write(folder)
    os.replace(tmp, POINTER)


def target(parent):
    """The data folder inside a chosen parent folder (the Drive itself, say)."""
    parent = os.path.expanduser(parent.strip().strip('"'))
    return parent if os.path.basename(os.path.normpath(parent)) == NAME else os.path.join(parent, NAME)


def move(parent):
    """Copy your data into `parent`/StockScreener data, check the copy, and use it from now on. The old folder is
    left as it was, as a spare copy you can delete later. Takes effect after a restart."""
    src, dst = current(), target(parent)
    if os.path.normcase(os.path.abspath(src)) == os.path.normcase(os.path.abspath(dst)):
        raise ValueError('Your data is already there.')
    if not os.path.isdir(os.path.dirname(dst)):
        raise ValueError(f'The folder {os.path.dirname(dst)} does not exist.')
    if os.path.exists(dst) and has_data(dst):
        raise ValueError('There is already program data in that folder (from your other computer?). Choose '
                         '"Use the data that is already there" instead.')
    shutil.copytree(src, dst, dirs_exist_ok=True, ignore=shutil.ignore_patterns(LOCK, '*.tmp'))
    for root, _, files in os.walk(src):  # check every file arrived complete
        for f in files:
            if f == LOCK or f.endswith('.tmp'):
                continue
            a = os.path.join(root, f)
            b = os.path.join(dst, os.path.relpath(a, src))
            if not os.path.exists(b) or os.path.getsize(a) != os.path.getsize(b):
                raise ValueError(f'Copying {os.path.relpath(a, src)} failed; your data stays where it was.')
    _point(dst)
    return dst


def use(parent):
    """Point this computer at data that is already in `parent` (put there by your other computer)."""
    dst = target(parent)
    if not has_data(dst):
        raise ValueError(f'No program data found in {dst}. Is Google Drive done syncing? On your first computer, '
                         'choose "Move my data there" first.')
    _point(dst)
    return dst


def back_to_default():
    try:
        os.remove(POINTER)
    except OSError:
        pass


# ---------- one computer at a time ----------

def me():
    return platform.node() or 'this computer'


def mark_in_use(folder):
    """Note that this computer has the data open (refreshed now and then while the program runs)."""
    try:
        path = os.path.join(folder, LOCK)
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as fh:
            json.dump({'computer': me(), 'since': datetime.now().isoformat(timespec='seconds')}, fh)
        os.replace(tmp, path)
    except OSError:
        pass


def other_user(folder):
    """(computer name, last seen) when another computer has had the data open in the last 30 minutes, else None."""
    try:
        d = json.load(open(os.path.join(folder, LOCK), encoding='utf-8', errors='replace'))
        when = datetime.fromisoformat(d['since'])
    except (OSError, ValueError, KeyError):
        return None
    if d.get('computer') != me() and datetime.now() - when < FRESH:
        return d.get('computer'), when
    return None


def release(folder):
    try:
        d = json.load(open(os.path.join(folder, LOCK), encoding='utf-8', errors='replace'))
        if d.get('computer') == me():
            os.remove(os.path.join(folder, LOCK))
    except (OSError, ValueError):
        pass

"""Updates for the installed app: when it starts, it asks GitHub for the newest release. When that is newer than
itself, it ASKS you first, showing what changed: Install now, Not now (asked again in a week), or Skip this version.
Only after "Install now" does it download the release, check it against the release's fingerprints (SHA256SUMS.txt)
and install it. Without a screen to ask on, it never installs. The last two downloaded installers are kept in the
"update" folder, so an older version can be put back by hand.

Windows: the installer runs silently and opens the app again when it is done (the launcher exits first, so its
files are free). Mac: the new "Stock Screener.app" replaces this one in place and is opened again.
Anything that goes wrong (offline, GitHub slow, a bad download) is written to the log and the current version
simply starts, so an update can never stop the program from opening.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.request
from datetime import date, timedelta

REPO = 'briefcasejona/stock-screener'
API = os.environ.get('STOCK_UPDATE_API', f'https://api.github.com/repos/{REPO}/releases/latest')
UA = 'stock-screener-updater'
ASSET = {'nt': 'StockScreener-Setup.exe', 'darwin': 'StockScreener-mac.dmg'}
CHOICES = os.path.join(os.path.expanduser('~'), '.stockscreener-update.json')  # "skip" / "not now", per computer
LATER_DAYS = 7
KEEP_INSTALLERS = 2


def choices():
    try:
        return json.load(open(CHOICES, encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def remember(**kw):
    try:
        with open(CHOICES, 'w', encoding='utf-8') as fh:
            json.dump(choices() | kw, fh)
    except OSError:
        pass


def wanted(version):
    """False when you skipped this version, said "Not now" less than a week ago, or its install failed this week."""
    c = choices()
    today = date.today().isoformat()
    if c.get('skip') == version:
        return False
    if c.get('later', {}).get(version, '') > today:
        return False
    if c.get('failed', {}).get(version, '') > today:
        return False
    return True


def parse(v):
    """'2026.11.10.3' (or 'v2026.11.10.3') -> (2026, 11, 10, 3); anything else, such as a test build, -> ()."""
    m = re.fullmatch(r'v?(\d+(?:\.\d+)*)', (v or '').strip())
    return tuple(int(x) for x in m.group(1).split('.')) if m else ()


def asset_name():
    return ASSET.get('darwin' if sys.platform == 'darwin' else os.name)


def get(url, timeout):
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'application/vnd.github+json'})
    return urllib.request.urlopen(req, timeout=timeout)


def newer(current, timeout=5):
    """The newest release when it is newer than `current`: {'version', 'url', 'sha256', 'size'}, else None."""
    name = asset_name()
    if not name:
        return None
    with get(API, timeout) as r:
        rel = json.load(r)
    if rel.get('draft') or rel.get('prerelease'):
        return None
    version = rel['tag_name'].lstrip('v')
    if not parse(version) or parse(version) <= parse(current):
        return None
    assets = {a['name']: a for a in rel.get('assets', [])}
    if name not in assets or 'SHA256SUMS.txt' not in assets:
        return None
    with get(assets['SHA256SUMS.txt']['browser_download_url'], timeout) as r:
        sums = {}
        for line in r.read().decode().splitlines():  # "<sha256>  <file name>", as sha256sum writes it
            parts = line.split(None, 1)
            if len(parts) == 2:
                sums[parts[1].strip().lstrip('*')] = parts[0].lower()
    sha = sums.get(name, '')
    if not re.fullmatch(r'[0-9a-f]{64}', sha):
        return None
    return {'version': version, 'url': assets[name]['browser_download_url'], 'sha256': sha,
            'size': assets[name].get('size') or 0, 'notes': (rel.get('body') or '').strip()}


def download(info, folder, progress=lambda done, total: None):
    """Download the release into `folder` and check its fingerprint; returns the file's path."""
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{info['version']}-{asset_name()}")
    h = hashlib.sha256()
    done = 0
    with get(info['url'], 60) as r, open(path + '.part', 'wb') as fh:
        while True:
            block = r.read(1 << 20)
            if not block:
                break
            fh.write(block)
            h.update(block)
            done += len(block)
            progress(done, info['size'])
    if h.hexdigest() != info['sha256']:
        os.remove(path + '.part')
        raise ValueError('the download does not match the release\'s fingerprint')
    os.replace(path + '.part', path)
    # keep this one and the one before it; older installers are removed
    old = sorted((f for f in os.listdir(folder) if f.endswith(asset_name()) and f != os.path.basename(path)),
                 key=lambda f: parse(f.split('-')[0]), reverse=True)
    for f in old[KEEP_INSTALLERS - 1:]:
        try:
            os.remove(os.path.join(folder, f))
        except OSError:
            pass
    return path


def ask(current, info):
    """Show what changed and ask: 'install', 'later' or 'skip'. Without a screen: 'later' (never installs unasked)."""
    try:
        import tkinter
        from tkinter import scrolledtext
        root = tkinter.Tk()
    except Exception:
        return 'later'
    answer = {'v': 'later'}
    root.title('Stock Screener: a new version')
    root.resizable(False, False)
    root.attributes('-topmost', True)
    tkinter.Label(root, text=f"Version {info['version']} is available (you have {current}). Install it now?",
                  padx=16, pady=12, anchor='w', justify='left').pack(fill='x')
    notes = scrolledtext.ScrolledText(root, width=70, height=14, wrap='word', padx=8, pady=6)
    notes.insert('1.0', info.get('notes') or 'No notes came with this version.')
    notes.configure(state='disabled')
    notes.pack(padx=16)
    tkinter.Label(root, text='Your journal, candidates and portfolio are kept as they are. The last installers are kept '
                             'in the "update" folder of the program.', padx=16, pady=8, anchor='w', justify='left',
                  wraplength=520).pack(fill='x')
    row = tkinter.Frame(root, padx=16, pady=12)
    row.pack(fill='x')

    def pick(v):
        answer['v'] = v
        root.destroy()
    tkinter.Button(row, text='Install now', default='active', command=lambda: pick('install')).pack(side='right')
    tkinter.Button(row, text=f'Not now (ask again in {LATER_DAYS} days)', command=lambda: pick('later')).pack(
        side='right', padx=8)
    tkinter.Button(row, text='Skip this version', command=lambda: pick('skip')).pack(side='left')
    root.protocol('WM_DELETE_WINDOW', lambda: pick('later'))
    root.mainloop()
    return answer['v']


def mac_app_path():
    """…/Stock Screener.app when this program runs from inside the Mac app."""
    p = os.path.abspath(sys.executable)
    for _ in range(3):
        p = os.path.dirname(p)
    return p if p.endswith('.app') else None


def install(path, log, relaunch=True, wait=False):
    """Install the downloaded release. Returns the installer's process (Windows) or None (Mac, already done)."""
    if os.name == 'nt':
        args = [path, '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/CLOSEAPPLICATIONS', f'/LOG={log}']
        if relaunch:
            args.append('/RELAUNCH=1')
        p = subprocess.Popen(args, creationflags=0x00000008 | 0x00000200)  # DETACHED_PROCESS, NEW_PROCESS_GROUP
        if wait:
            p.wait()
        return p
    app = mac_app_path()
    if not app:
        raise RuntimeError('this copy is not inside "Stock Screener.app"')
    mount = tempfile.mkdtemp(prefix='stockscreener-')
    subprocess.run(['hdiutil', 'attach', path, '-nobrowse', '-readonly', '-noautoopen', '-mountpoint', mount],
                   check=True, capture_output=True)
    try:
        new = os.path.join(mount, 'Stock Screener.app')
        staged, old = app + '.new', app + '.old'
        for p in (staged, old):
            shutil.rmtree(p, ignore_errors=True)
        try:
            subprocess.run(['ditto', new, staged], check=True, capture_output=True)
            os.rename(app, old)  # the running program keeps its open files; the new one takes the name
        except (OSError, subprocess.CalledProcessError):
            # no permission to change the Applications folder: show the new version to drag in by hand
            shutil.rmtree(staged, ignore_errors=True)
            subprocess.Popen(['open', path])
            raise RuntimeError('could not replace the app; the new version is opened to drag into Applications')
        try:
            os.rename(staged, app)
        except OSError:
            os.rename(old, app)  # put the current version back
            raise
        shutil.rmtree(old, ignore_errors=True)
    finally:
        subprocess.run(['hdiutil', 'detach', mount, '-force'], capture_output=True)
        shutil.rmtree(mount, ignore_errors=True)
    if relaunch:
        subprocess.Popen(['open', '-n', app])
    return None


def run_with_window(title, work):
    """Run work(set_text) in the background while a small window says what is happening. Returns what work
    returned, or raises what it raised. Without a screen (or tkinter) it simply runs."""
    result = {}

    def target(set_text):
        try:
            result['value'] = work(set_text)
        except BaseException as e:  # handed to the caller below
            result['error'] = e

    try:
        import tkinter
        root = tkinter.Tk()
    except Exception:
        target(lambda text: None)
    else:
        root.title(title)
        root.resizable(False, False)
        text = tkinter.StringVar(value='Looking for the new version…')
        tkinter.Label(root, textvariable=text, padx=30, pady=24, width=48).pack()
        root.attributes('-topmost', True)
        th = threading.Thread(target=target, args=(lambda t: root.after(0, text.set, t),), daemon=True)
        th.start()

        def poll():
            if th.is_alive():
                root.after(200, poll)
            else:
                root.destroy()
        poll()
        root.mainloop()
        th.join()
    if 'error' in result:
        raise result['error']
    return result.get('value')


def update_if_available(current, base, log=print, relaunch=True, wait=False, window=True, before_install=None,
                        asked=False):
    """The whole update at start-up. Returns True when a newer version is being installed (the caller exits so
    the new version can take over), False when the current version should simply start. `asked`: you already asked
    for it yourself (the --update-only command), so there is no question first."""
    try:
        info = newer(current)
    except Exception as e:
        log(f'update check skipped: {e}')
        return False
    if not info or (not asked and not wanted(info['version'])):
        return False
    choice = 'install' if asked else ask(current, info) if window else 'later'
    if choice == 'skip':
        remember(skip=info['version'])
        log(f'version {info["version"]} skipped')
        return False
    if choice != 'install':
        remember(later={info['version']: (date.today() + timedelta(days=LATER_DAYS)).isoformat()})
        log(f'update to {info["version"]} not now')
        return False
    log(f'updating from {current} to {info["version"]}')
    if before_install:  # e.g. stop the program that was already starting
        before_install()
    folder = os.path.join(base, 'update')

    def work(say):
        def progress(done, total):
            if total:
                say(f'Downloading Stock Screener {info["version"]}: {done * 100 // total}%')
        path = download(info, folder, progress)
        say(f'Installing Stock Screener {info["version"]}…')
        return install(path, os.path.join(base, 'install.log'), relaunch=relaunch, wait=wait)

    try:
        p = run_with_window('Updating Stock Screener', work) if window else work(lambda t: None)
    except Exception as e:
        log(f'update failed, starting the current version: {e}')
        # not tried again on every start (a Mac that can't replace the app would loop); asked again in a week
        remember(failed={info['version']: (date.today() + timedelta(days=LATER_DAYS)).isoformat()})
        return False
    if wait and p is not None and p.returncode:
        log(f'the installer stopped with exit code {p.returncode}')
        remember(failed={info['version']: (date.today() + timedelta(days=LATER_DAYS)).isoformat()})
        return False
    return True

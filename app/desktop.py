"""The Stock Screener as an app on your computer: double-click its icon and it opens in its own window.

The installed app is built from this file (build/stock_screener.spec). Without arguments it is the launcher: it
starts the program in the background, opens its window, and stops the program when the window closes. Opening it
again while it runs just opens another window. The same program file also does the background work:
  --serve PORT                  the program itself (Streamlit), listening on 127.0.0.1 only
  --run-script FILE [ARGS...]   one of the screener's scripts (the installed app has no separate Python)
  --selftest                    start, check every page answers, run a script, stop (for the build machines)
  --update-only                 install a newer release if there is one, wait for it, and stop (for the build machines)
When the installed app starts it first looks for a newer release on GitHub and installs it (updater.py).
It also runs from source (python app/desktop.py), which is how it is tested.
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

FROZEN = getattr(sys, 'frozen', False)
# where the program's files are: inside the installed app, or the folder this file is in
BUNDLE = sys._MEIPASS if FROZEN else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(BUNDLE, 'app')
NAME = 'Stock Screener'


def app_base():
    """A folder of the program's own (not your work): the screener's data, downloads, the window's settings."""
    if os.name == 'nt':
        root = os.environ.get('LOCALAPPDATA') or os.path.expanduser(r'~\AppData\Local')
        return os.path.join(root, 'StockScreener')
    if sys.platform == 'darwin':
        return os.path.expanduser('~/Library/Application Support/StockScreener')
    return os.path.join(os.environ.get('XDG_DATA_HOME') or os.path.expanduser('~/.local/share'), 'StockScreener')


BASE = os.environ.get('STOCK_APP_BASE', app_base())
STATE = os.path.join(BASE, 'running.json')
LOG = os.path.join(BASE, 'program.log')


def version():
    try:
        return open(os.path.join(APP, 'VERSION'), encoding='utf-8').read().strip()
    except OSError:
        return 'development'


def program_root():
    """The installed app's files can't be written to, and the screener writes its results next to its data. So each
    version copies its screener and playbook folders here once; the previous version's copy is removed.
    From source, the program folder itself is used."""
    if not FROZEN:
        return BUNDLE
    v = version().replace(':', '').replace(' ', '_')
    root = os.path.join(BASE, 'program', v)
    if not os.path.exists(os.path.join(root, '.complete')):
        tmp = root + '.tmp'
        shutil.rmtree(tmp, ignore_errors=True)
        for part in ('screener', 'playbook'):
            shutil.copytree(os.path.join(BUNDLE, part), os.path.join(tmp, part))
        open(os.path.join(tmp, '.complete'), 'w').close()
        shutil.rmtree(root, ignore_errors=True)
        os.replace(tmp, root)
        for old in os.listdir(os.path.join(BASE, 'program')):
            if old != v:
                shutil.rmtree(os.path.join(BASE, 'program', old), ignore_errors=True)
    return root


def setup_env():
    os.makedirs(BASE, exist_ok=True)
    os.environ['STOCK_ROOT'] = program_root()
    os.environ['PYTHONUTF8'] = '1'
    try:  # the Mac has no certificates for downloads unless this is set
        import certifi
        os.environ.setdefault('SSL_CERT_FILE', certifi.where())
    except ImportError:
        pass


def log_to_file():
    """The app has no text window: what it would print goes to program.log."""
    fh = open(LOG, 'a', encoding='utf-8', buffering=1)
    sys.stdout = sys.stderr = fh


def worker_cmd(*args):
    if FROZEN:
        worker = os.path.join(os.path.dirname(sys.executable), 'stockscreener-worker' + ('.exe' if os.name == 'nt' else ''))
        return [worker if os.path.exists(worker) else sys.executable, *args]
    return [sys.executable, '-X', 'utf8', os.path.abspath(__file__), *args]


def hidden():
    return {'creationflags': 0x08000000} if os.name == 'nt' else {}  # CREATE_NO_WINDOW


# ---------- the program itself ----------

def serve(port):
    """Run Streamlit in this process (it must have the main thread), as `streamlit run app.py` would."""
    from streamlit import config
    from streamlit.web import bootstrap
    os.chdir(APP)  # Streamlit reads .streamlit/config.toml from here
    script = os.path.join(APP, 'app.py')
    flags = {  # Streamlit's command-line spelling: section_option
        'global_developmentMode': False,  # the installed app is not a developer's copy of Streamlit
        'server_port': port, 'server_address': '127.0.0.1', 'server_headless': True,
        'server_allowedHosts': ['127.0.0.1', 'localhost'], 'server_enableXsrfProtection': True,
        'server_fileWatcherType': 'none', 'server_runOnSave': False, 'server_maxUploadSize': 300,
        'browser_gatherUsageStats': False,
    }
    config._main_script_path = script
    bootstrap.load_config_options(flag_options=flags)
    bootstrap.run(script, False, [], flags)


def run_script(path, args):
    """Run one of the screener's scripts as `python -I script args` would."""
    import runpy
    sys.argv = [path, *args]
    runpy.run_path(path, run_name='__main__')


# ---------- the launcher ----------

def healthy(port, timeout=1.0):
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/_stcore/health', timeout=timeout) as r:
            return r.read().strip() == b'ok'
    except Exception:
        return False


def free_port(start=8501):
    for port in range(start, start + 50):
        with socket.socket() as s:
            if s.connect_ex(('127.0.0.1', port)):
                return port
    raise RuntimeError('no free port between 8501 and 8550')


def running_port():
    try:
        port = json.load(open(STATE, encoding='utf-8'))['port']
    except (OSError, ValueError, KeyError):
        return None
    return port if healthy(port) else None


def find_browser():
    """A browser that can show a page as an app (its own window, no address bar): Edge, Chrome or Brave."""
    if os.environ.get('STOCK_BROWSER'):
        return os.environ['STOCK_BROWSER']
    if os.name == 'nt':
        roots = [os.environ.get(k) for k in ('ProgramFiles(x86)', 'ProgramFiles', 'LOCALAPPDATA')]
        rel = [r'Microsoft\Edge\Application\msedge.exe', r'Google\Chrome\Application\chrome.exe',
               r'BraveSoftware\Brave-Browser\Application\brave.exe']
        paths = [os.path.join(r, p) for p in rel for r in roots if r]
    elif sys.platform == 'darwin':
        apps = ['Google Chrome.app/Contents/MacOS/Google Chrome', 'Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
                'Brave Browser.app/Contents/MacOS/Brave Browser']
        paths = [os.path.join(d, a) for a in apps for d in ('/Applications', os.path.expanduser('~/Applications'))]
    else:
        paths = [shutil.which(n) for n in ('google-chrome', 'chromium', 'chromium-browser', 'microsoft-edge')]
    return next((p for p in paths if p and os.path.exists(p)), None)


def open_window(url):
    """Open the program in its own window. Returns the window's process, or None when it opened in the normal
    browser instead (no Edge or Chrome: then Quit in the program's sidebar stops it)."""
    browser = find_browser()
    if browser:
        profile = os.path.join(BASE, 'window')
        return subprocess.Popen([browser, f'--app={url}', f'--user-data-dir={profile}', '--no-first-run',
                                 '--no-default-browser-check', '--window-size=1400,950'],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    import webbrowser
    webbrowser.open(url)
    return None


def stop_process(p):
    if p and p.poll() is None:
        p.terminate()
        try:
            p.wait(10)
        except subprocess.TimeoutExpired:
            p.kill()


def job_running():
    """A price or full refresh still busy in the background (it outlives the window): don't update under it."""
    try:
        s = json.load(open(os.path.join(os.environ['STOCK_ROOT'], 'cache', 'job.json'), encoding='utf-8'))
    except (OSError, ValueError, KeyError):
        return False
    return s.get('state') == 'running' and time.time() - s.get('beat', 0) < 90


def launch():
    port = running_port()
    if port:  # already running: another window on it
        open_window(f'http://127.0.0.1:{port}')
        return 0
    if FROZEN and os.environ.get('STOCK_NO_UPDATE') != '1' and not job_running():
        import updater
        if updater.update_if_available(version(), BASE):
            return 0  # the new version opens itself when it is installed
    port = free_port()
    server = subprocess.Popen(worker_cmd('--serve', str(port)), stdin=subprocess.DEVNULL, stdout=sys.stdout,
                              stderr=sys.stdout, **hidden())
    for _ in range(240):  # wait until it answers (the first start after installing takes longest)
        if healthy(port):
            break
        if server.poll() is not None:
            raise RuntimeError(f'the program stopped while starting (exit code {server.returncode}); see {LOG}')
        time.sleep(0.5)
    else:
        stop_process(server)
        raise RuntimeError('the program did not start within two minutes')
    with open(STATE, 'w', encoding='utf-8') as fh:
        json.dump({'port': port, 'pid': server.pid}, fh)
    try:
        window = open_window(f'http://127.0.0.1:{port}')
        # stop when the window is closed, or when the program is stopped (Quit in the sidebar)
        while server.poll() is None and (window is None or window.poll() is None):
            time.sleep(1)
    finally:
        stop_process(window if 'window' in locals() else None)
        stop_process(server)
        try:
            os.remove(STATE)
        except OSError:
            pass
    return 0


def selftest():
    """For the build machines: start the program, check it answers and every page loads, run a script, stop."""
    port = free_port(8601)
    server = subprocess.Popen(worker_cmd('--serve', str(port)), **hidden())
    try:
        for _ in range(240):
            if healthy(port):
                break
            if server.poll() is not None:
                print(f'FAIL: the program stopped while starting ({server.returncode})')
                return 1
            time.sleep(0.5)
        else:
            print('FAIL: the program did not answer within two minutes')
            return 1
        page = urllib.request.urlopen(f'http://127.0.0.1:{port}/', timeout=10).read()
        print('page:', len(page), 'bytes')
        r = subprocess.run(worker_cmd('--run-script', os.path.join(os.environ['STOCK_ROOT'], 'playbook', 'code',
                                                                   'watchlist.py'), 'list'),
                           capture_output=True, text=True, timeout=300, **hidden())
        print('watchlist list:', r.returncode, r.stdout.strip()[:200], r.stderr.strip()[-500:])
        if r.returncode:
            return 1
        print('OK')
        return 0
    finally:
        stop_process(server)


def main():
    args = sys.argv[1:]
    if args[:1] == ['--run-script']:
        setup_env()
        return run_script(args[1], args[2:])
    setup_env()
    if args[:1] == ['--serve']:
        if FROZEN and sys.stdout is None:
            log_to_file()
        return serve(int(args[1]))
    if args[:1] == ['--selftest']:
        return selftest()
    if args[:1] == ['--update-only']:
        import updater
        return 0 if updater.update_if_available(version(), BASE, relaunch=False, wait=True, window=False) else 1
    if FROZEN or sys.stdout is None:
        log_to_file()
    print(f'--- {time.strftime("%Y-%m-%d %H:%M:%S")} {NAME} {version()} starting')
    try:
        return launch()
    except Exception as e:
        print(f'Could not start: {e}')
        try:  # tell the person: the app has no text window
            import tkinter
            from tkinter import messagebox
            tkinter.Tk().withdraw()
            messagebox.showerror(NAME, f'{NAME} could not start: {e}\n\nDetails are in {LOG}')
        except Exception:
            pass
        return 1


if __name__ == '__main__':
    sys.exit(main())

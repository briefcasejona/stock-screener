"""Starts the Stock Screener.

The first time, it makes the program's own Python environment in the .venv folder and installs the packages in
requirements.lock (a few minutes, needs internet). Every package is checked against its fingerprint
in that file, and only ready-made packages are accepted (no setup code of a package runs). After that it starts straight away. It then opens the program in
your browser. The program only listens on this computer (127.0.0.1), so nobody else on your network can reach it.
"""
import hashlib
import os
import socket
import subprocess
import sys
import time
import venv
import webbrowser

APP = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(APP)
VENV = os.path.join(ROOT, '.venv')
PY = os.path.join(VENV, 'Scripts', 'python.exe') if os.name == 'nt' else os.path.join(VENV, 'bin', 'python')
REQ = os.path.join(APP, 'requirements.lock')
STAMP = os.path.join(VENV, 'installed-requirements.sha256')


def stop(msg):
    print('\n' + msg)
    input('\nPress Enter to close this window.')
    sys.exit(1)


def install():
    want = hashlib.sha256(open(REQ, 'rb').read()).hexdigest()
    if os.path.exists(PY) and os.path.exists(STAMP) and open(STAMP).read().strip() == want:
        return
    if not os.path.exists(PY):
        print('First start: making the program\'s own Python environment...')
        venv.create(VENV, with_pip=True)
    print('Installing the packages the program needs (a few minutes, only this once)...')
    r = subprocess.run([PY, '-m', 'pip', 'install', '--disable-pip-version-check', '--require-hashes',
                        '--only-binary', ':all:', '-r', REQ])
    if r.returncode:
        stop('Installing the packages failed (see the messages above). Check your internet connection and start '
             'the program again. If it keeps failing, delete the .venv folder and try once more.')
    open(STAMP, 'w').write(want)


def free_port(start=8501):
    for port in range(start, start + 50):
        with socket.socket() as s:
            if s.connect_ex(('127.0.0.1', port)):
                return port
    stop('No free port found between 8501 and 8550.')


def main():
    if sys.version_info < (3, 12):
        stop(f'This program needs Python 3.12 or newer; this is Python {sys.version.split()[0]}.\n'
             'Install Python 3.13 from https://www.python.org/downloads/ and start the program again.')
    install()
    certifi = subprocess.run([PY, '-c', 'import certifi; print(certifi.where())'], capture_output=True, text=True)
    env = os.environ | {'PYTHONUTF8': '1', 'PYTHONUNBUFFERED': '1'}
    if certifi.returncode == 0:  # the Mac python.org installer has no certificates for downloads until this is set
        env['SSL_CERT_FILE'] = certifi.stdout.strip()
    port = free_port()
    url = f'http://127.0.0.1:{port}'
    p = subprocess.Popen([PY, '-m', 'streamlit', 'run', os.path.join(APP, 'app.py'), '--server.headless', 'true',
                          '--server.address', '127.0.0.1', '--server.port', str(port),
                          '--browser.gatherUsageStats', 'false'], cwd=APP, env=env)
    for _ in range(120):  # wait until it answers, then open the browser
        with socket.socket() as s:
            if not s.connect_ex(('127.0.0.1', port)):
                break
        if p.poll() is not None:
            stop('The program stopped while starting (see the messages above).')
        time.sleep(0.5)
    webbrowser.open(url)
    print(f'\nThe Stock Screener is running at {url}\nKeep this window open while you use it. '
          'Close it (or press Ctrl+C) to stop the program.\n')
    try:
        p.wait()
    except KeyboardInterrupt:
        p.terminate()


if __name__ == '__main__':
    main()

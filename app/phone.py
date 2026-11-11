"""Using the program from your phone.

Two ways, both private:
1. The full program over Tailscale, a free private network of only your own devices. When "Use on my phone" is on,
   the program listens on this computer's Tailscale address only (never on your Wi-Fi or the internet), so only a
   device signed in to your own Tailscale account can open it. The computer has to be on and the program running.
2. "Phone view.pdf": a read-only summary saved into your data folder every 10 minutes while the program runs. With your
   data folder in Google Drive, the Google Drive app on your phone shows it, also when the computer is off.

The choice is kept per computer, in a small file in your home folder (each computer has its own Tailscale address).
"""
import ipaddress
import json
import os
import shutil
import subprocess
import sys

SETTING = os.path.join(os.path.expanduser('~'), '.stockscreener-phone.json')
PORT = 8520  # a fixed port, so the bookmark on your phone keeps working
TAILNET = ipaddress.ip_network('100.64.0.0/10')  # the addresses Tailscale hands out
PDF_NAME = 'Phone view.pdf'


def enabled():
    try:
        return bool(json.load(open(SETTING, encoding='utf-8', errors='replace')).get('on'))
    except (OSError, ValueError, AttributeError):
        return False


def set_enabled(on):
    with open(SETTING, 'w', encoding='utf-8') as fh:
        json.dump({'on': bool(on)}, fh)


def _cli():
    """Tailscale's own command-line program, if it is installed."""
    candidates = [shutil.which('tailscale')]
    if os.name == 'nt':
        candidates += [os.path.join(os.environ.get(k, ''), 'Tailscale', 'tailscale.exe')
                       for k in ('ProgramFiles', 'ProgramFiles(x86)') if os.environ.get(k)]
    elif sys.platform == 'darwin':
        candidates += ['/Applications/Tailscale.app/Contents/MacOS/Tailscale']
    return next((p for p in candidates if p and os.path.exists(p)), None)


def _run(args):
    cli = _cli()
    if not cli:
        return None
    try:
        r = subprocess.run([cli, *args], capture_output=True, text=True, timeout=5, encoding='utf-8', errors='replace',
                           creationflags=0x08000000 if os.name == 'nt' else 0)
        return r.stdout if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def _tailnet(ip):
    try:
        return ipaddress.ip_address(ip) in TAILNET
    except ValueError:
        return False


def address():
    """This computer's Tailscale address (100.x.y.z), or None when Tailscale is not installed or not connected."""
    out = _run(['ip', '-4'])
    for line in (out or '').split():
        if _tailnet(line.strip()):
            return line.strip()
    # Only Tailscale's own answer counts: some internet providers and phone hotspots also hand out 100.x addresses,
    # and the program must never open itself to those networks by mistake.
    return None


def names():
    """The names this computer has on your Tailscale network (e.g. 'my-pc' and 'my-pc.tail1234.ts.net')."""
    out = _run(['status', '--json'])
    try:
        dns = json.loads(out)['Self']['DNSName'].rstrip('.') if out else ''
    except (ValueError, KeyError, TypeError):
        dns = ''
    found = [dns, dns.split('.')[0]] if dns else []
    return [n.lower() for n in found if n]


def server_options():
    """(address to listen on, names the program answers to). Only on the Tailscale address when phone use is on and
    Tailscale is connected; otherwise only on this computer itself, as before."""
    if enabled():
        ip = address()
        if ip:
            return ip, [ip, *names()]
    return '127.0.0.1', ['127.0.0.1', 'localhost']


def phone_link(port=PORT):
    ip = address()
    if not ip:
        return None
    n = names()
    return f'http://{n[0] if n else ip}:{port}', f'http://{ip}:{port}'

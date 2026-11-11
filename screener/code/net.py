"""Patient downloads: when a source says "too many requests" (or the network hiccups), wait and try again instead
of failing, waiting longer each time. Used for the SEC, filings.xbrl.org and Yahoo Finance."""
import os
import time
import urllib.error
import urllib.parse
import urllib.request

UA = 'stock-screener research'  # everyone except the SEC gets no address
CONTACT_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'sec_contact.txt')
WAITS = (5, 15, 45, 90)  # seconds between tries


def _wait(i, retry_after=None):
    try:
        w = min(float(retry_after), 300) if retry_after else WAITS[i]
    except ValueError:
        w = WAITS[i]
    print(f'  the source asked us to slow down: waiting {w:.0f} s', flush=True)
    time.sleep(w)


def sec_contact():
    """The email address the SEC asks every program to send with its requests (and that goes nowhere else): the
    laptop program sets SEC_CONTACT from its settings, the project keeps it in screener/sec_contact.txt."""
    c = os.environ.get('SEC_CONTACT', '').strip()
    if not c:
        try:
            c = open(CONTACT_FILE, encoding='utf-8', errors='replace').read().strip()
        except OSError:
            pass
    return c


def headers_for(url):
    host = urllib.parse.urlsplit(url).hostname or ''
    if host == 'sec.gov' or host.endswith('.sec.gov'):
        c = sec_contact()
        if not c:
            raise RuntimeError('The SEC asks every program for a contact email address. Enter yours on the '
                               '"Update data" page (it is only sent to the SEC).')
        return {'User-Agent': f'{UA} {c}'}
    return {'User-Agent': UA}


def fetch(url, timeout=60, headers=None):
    """The body of a URL. Retries on 429 (too many requests), 403 (the SEC's way of saying slow down), server
    errors and network errors; any other HTTP error (such as 404) is raised straight away."""
    req = urllib.request.Request(url, headers={**headers_for(url), **(headers or {})})
    for i in range(len(WAITS) + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            if e.code not in (403, 429) and e.code < 500 or i == len(WAITS):
                raise
            _wait(i, e.headers.get('Retry-After'))
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if i == len(WAITS):
                raise
            _wait(i)


def rate_limited(e):
    return type(e).__name__ == 'YFRateLimitError' or 'Too Many Requests' in str(e) or 'Rate limited' in str(e)


def patient(fn, *args, **kw):
    """Call a Yahoo Finance (yfinance) function, waiting and trying again while Yahoo says too many requests."""
    for i in range(len(WAITS) + 1):
        try:
            return fn(*args, **kw)
        except Exception as e:
            if not rate_limited(e) or i == len(WAITS):
                raise
            _wait(i)

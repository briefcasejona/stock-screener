"""For the build machines: start the built program, open every page in a real browser and check none shows an error.

Run: python build/ui_check.py PATH_TO_stockscreener-worker [SCREENSHOT_FOLDER]
Uses the browser in env BROWSER_PATH, or else the machine's Chrome (Playwright's "chrome" channel).
"""
import os
import socket
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

PAGES = {'candidates': 'Candidates', 'scoreboard': 'Scoreboard', 'screener': 'Screener', 'course': 'Course', 'journal': 'Journal', 'reports': 'Add a report',
         'update': 'Update data', 'guide': 'How to use it'}


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def main():
    worker, shots = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else None)
    port = free_port()
    server = subprocess.Popen([worker, '--serve', str(port)])
    url = f'http://127.0.0.1:{port}'
    problems = []
    try:
        for _ in range(240):
            try:
                if urllib.request.urlopen(f'{url}/_stcore/health', timeout=1).read().strip() == b'ok':
                    break
            except OSError:
                pass
            if server.poll() is not None:
                sys.exit(f'FAIL: the program stopped while starting ({server.returncode})')
            time.sleep(0.5)
        else:
            sys.exit('FAIL: the program did not answer within two minutes')
        with sync_playwright() as p:
            path = os.environ.get('BROWSER_PATH')
            browser = p.chromium.launch(executable_path=path) if path else p.chromium.launch(channel='chrome')
            page = browser.new_page(viewport={'width': 1400, 'height': 1000})
            page.on('pageerror', lambda e: problems.append(f'javascript error: {e}'))
            for slug, title in PAGES.items():
                page.goto(f'{url}/' + ('' if slug == 'candidates' else slug))  # the first page lives at /
                page.wait_for_selector('[data-testid="stSidebar"]', timeout=120000)
                page.wait_for_timeout(1500)
                page.wait_for_function('() => !document.querySelector(\'[data-testid="stStatusWidget"]\')',
                                       timeout=120000)
                page.wait_for_timeout(800)
                errors = [e.inner_text()[:500] for e in page.locator('[data-testid="stException"]').all()]
                heading = page.locator('h1').first.inner_text(timeout=10000) if page.locator('h1').count() else ''
                print(f'{slug}: heading "{heading}", errors {len(errors)}')
                problems += [f'{slug}: {e}' for e in errors]
                if page.get_by_text('Page not found').count():
                    problems.append(f'{slug}: "Page not found"')
                if title.lower() not in heading.lower():
                    problems.append(f'{slug}: expected the heading "{title}", got "{heading}"')
                if shots:
                    os.makedirs(shots, exist_ok=True)
                    page.screenshot(path=os.path.join(shots, f'{slug}.png'), full_page=True)
            page.goto(f'{url}/update')
            page.wait_for_selector('text=Your email address for the SEC', timeout=60000)
            browser.close()
    finally:
        server.terminate()
        try:
            server.wait(15)
        except subprocess.TimeoutExpired:
            server.kill()
    if problems:
        print('FAIL:', *problems, sep='\n  ')
        sys.exit(1)
    print('OK: every page opened without an error')


if __name__ == '__main__':
    main()

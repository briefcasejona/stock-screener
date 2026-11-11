"""Long data jobs (fresh prices, the full refresh) run here, apart from the browser page, so they finish even when you
switch pages or close the tab. Progress goes to cache/job.json and cache/job.log; the Update data page reads them.

Run by the program: python -X utf8 -I app/jobs.py prices|full|after_restore|first
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import core  # noqa: E402

JOBS = {'prices': ('Refreshing prices', core.PRICES_ONLY), 'full': ('Full refresh', core.FULL),
        'after_restore': ('Reading your own reports', core.AFTER_REPORT),
        'first': ('Getting today\'s prices (first start)', core.FIRST_DOWNLOAD)}
STATUS, LOG = os.path.join(core.CACHE, 'job.json'), os.path.join(core.CACHE, 'job.log')


def status():
    try:
        return json.load(open(STATUS, encoding='utf-8', errors='replace'))
    except (OSError, ValueError):
        return None


def running():
    """The running job, if any. A job writes a heartbeat every few seconds; one that stopped writing it ended
    without finishing (the laptop was shut down, for example)."""
    s = status()
    if not s or s['state'] != 'running' or time.time() - s.get('beat', 0) > 60:
        return None
    return s


def start(kind):
    """Start a job in the background unless one is running."""
    import subprocess
    if running():
        return False
    os.makedirs(core.CACHE, exist_ok=True)
    flags = core.localdata.hidden() if os.name == 'nt' else {'start_new_session': True}
    subprocess.Popen(core.python_cmd(os.path.abspath(__file__), kind), cwd=core.ROOT, stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **flags)
    for _ in range(50):  # until the job has written its first status
        if (status() or {}).get('state') == 'running':
            break
        time.sleep(0.1)
    return True


def main(kind):
    label, keys = JOBS[kind]
    os.makedirs(core.CACHE, exist_ok=True)
    if kind == 'first' and os.path.isdir(core.USER_REPORTS) and os.listdir(core.USER_REPORTS):  # your own reports are read in on the way
        keys = keys[:2] + ['extract_eu'] + keys[2:]
    st = {'kind': kind, 'label': label, 'state': 'running', 'step': 0, 'steps': len(keys),
          'step_name': '', 'started': time.strftime('%Y-%m-%d %H:%M'), 'finished': None}

    import threading
    lock = threading.Lock()

    def save():
        with lock:
            st['beat'] = time.time()
            tmp = STATUS + '.tmp'
            json.dump(st, open(tmp, 'w', encoding='utf-8'))
            for _ in range(10):  # never a half-written file for the page; Windows refuses while it is being read
                try:
                    os.replace(tmp, STATUS)
                    return
                except PermissionError:
                    time.sleep(0.2)

    def heartbeat():
        while st['state'] == 'running':
            save()
            time.sleep(5)

    save()
    threading.Thread(target=heartbeat, daemon=True).start()
    with open(LOG, 'w', encoding='utf-8') as log:
        if kind == 'full':
            core.clear_for_full_refresh()
        for i, k in enumerate(keys, 1):
            name, cmd = core.STEPS[k]
            st.update(step=i, step_name=name)
            save()
            log.write(f'--- {name}\n')
            log.flush()
            for item in core.stream(cmd):
                if isinstance(item, int):
                    code = item
                    break
                log.write(item + '\n')
                log.flush()
            if code:
                st.update(state='failed', finished=time.strftime('%Y-%m-%d %H:%M'))
                if kind == 'full':
                    core.restore_after_failed_refresh()
                save()
                return
    st.update(state='done', finished=time.strftime('%Y-%m-%d %H:%M'))
    if kind == 'full':
        core.save_setting(last_full_refresh=time.strftime('%Y-%m-%d'))
    save()


if __name__ == '__main__':
    main(sys.argv[1])

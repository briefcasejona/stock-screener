"""Watchlist and one-time analyses.

Every company the user has analysed is in journal/watchlist.json with a mode:
- 'watch': checked every week. Its figures and price are refreshed; when a new year shows up (a new annual report)
  the 10 checks and the valuation are re-run and noted; a new quarterly or half-year report is noted too (the analysis
  uses yearly figures).
- 'once': a one-time analysis, kept with its date and never updated.
Each analysis is saved in journal/analyses/<ticker>.json (analyse.py's output). Changes that matter (added,
new annual report, price crossing a buy-below price) are appended to journal/journal.json, never edited.

Run (from anywhere):
  python3 -I code/watchlist.py add ADBE [--once] [--name "Adobe"] [--base 0.10 --bear 0.05 --bull 0.15] [--normalised]
  python3 -I code/watchlist.py set ADBE --base 0.09 [--bear ..] [--bull ..] [--normalised|--average] [--reviewed]
  python3 -I code/watchlist.py watch ADBE | once ADBE | remove ADBE | list
  python3 -I code/watchlist.py check            # the weekly check; prints what changed as JSON
Then python3 -I code/build_dashboard_data.py and upload the datasets.
WATCHLIST_DIR overrides the journal folder (for tests).
"""
import argparse
import glob
import json
import os
import sys
import urllib.request
from datetime import date

CODE = os.path.dirname(os.path.abspath(__file__))
PLAYBOOK = os.path.dirname(CODE)
SCREENER = os.path.join(os.path.dirname(PLAYBOOK), 'screener')
sys.path.insert(0, CODE)
sys.path.insert(0, os.path.join(SCREENER, 'code'))
from analyse import analyse  # noqa: E402
from refresh_company import find, refresh  # noqa: E402
import localdata  # noqa: E402
import net  # noqa: E402

STATE = localdata.JOURNAL_DIR
LIST, JOURNAL, ANALYSES = f'{STATE}/watchlist.json', f'{STATE}/journal.json', f'{STATE}/analyses'
MARGINS = (5, 10, 20, 30)
ANNUAL_SEC, INTERIM_SEC = {'10-K', '20-F', '40-F'}, {'10-Q'}


def load():
    return json.load(open(LIST, encoding='utf-8', errors='replace')) if os.path.exists(LIST) else []


def save(entries):
    os.makedirs(STATE, exist_ok=True)
    localdata.write_json(LIST, entries, indent=1)


def entry_of(entries, ticker):
    e = next((e for e in entries if e['ticker'] == ticker), None)
    if not e:
        raise SystemExit(f'{ticker} is not on the list')
    return e


def journal_add(a, why, change_mind='A new annual report, or the price reaching a buy-below price.'):
    c = a['candidate']
    entries = json.load(open(JOURNAL, encoding='utf-8', errors='replace')) if os.path.exists(JOURNAL) else []
    today = date.today().isoformat()
    base_id = f"{today}-{c['ticker']}"
    n = sum(1 for e in entries if e['id'].startswith(base_id))
    entries.append({'id': base_id if not n else f'{base_id}-{n + 1}', 'date': today, 'company': c['company'],
                    'price': c['price'], 'currency': c['currency'], 'decision': c['decision'],
                    'implied_growth': c['implied_growth'], 'bear': c['bear'], 'base': c['base'], 'bull': c['bull'],
                    'why': why, 'change_mind': change_mind, 'next_check': c['next_check'], 'author': os.environ.get('WATCHLIST_AUTHOR', 'Claude (watchlist)')})
    localdata.write_json(JOURNAL, entries, indent=1)


def below(a):
    """For each margin of safety: is today's price at or below the buy-below price?"""
    c = a['candidate']
    return {str(m): c['price'] <= c['base'] * (1 - m / 100) for m in MARGINS}


def money(v, cur):
    return f'{cur} {v:,.2f}' if v < 100 else f'{cur} {v:,.0f}'


def latest_reports(ticker):
    """Newest annual and interim report the free sources show: SEC filings, ESEF filings, or the user's own files."""
    region, u = find(ticker)
    out = {'annual': None, 'interim': None}
    if u['source'] == 'sec':
        rec = json.loads(net.fetch(f"https://data.sec.gov/submissions/CIK{u['cik']}.json"))['filings']['recent']
        for form, filed, period, acc, doc in zip(rec['form'], rec['filingDate'], rec['reportDate'], rec['accessionNumber'],
                                                 rec['primaryDocument']):
            kind = 'annual' if form in ANNUAL_SEC else 'interim' if form in INTERIM_SEC else None
            if kind and (out[kind] is None or filed > out[kind]['filed']):
                url = f"https://www.sec.gov/Archives/edgar/data/{int(u['cik'])}/{acc.replace('-', '')}/{doc}"
                out[kind] = {'form': form, 'filed': filed, 'period_end': period, 'url': url}
    elif u.get('lei'):
        from extract_esef import API, choose, filing_list
        year_end = None
        figs = [r for r in __import__('csv').DictReader(open(f'{SCREENER}/output/figures_{region}.csv', encoding='utf-8', errors='replace')) if r['ticker'] == ticker]
        if figs:
            year_end = max(figs, key=lambda r: r['period_end'])['period_end'][5:]
        for f in choose(filing_list(u['lei'])):
            kind = 'annual' if year_end is None or abs(int(f['period_end'][5:7]) - int(year_end[:2])) % 12 == 0 else 'interim'
            rep = {'form': 'ESEF report', 'filed': (f.get('date_added') or '')[:10], 'period_end': f['period_end'],
                   'url': API + f['viewer_url'] if f.get('viewer_url') else ''}
            if out[kind] is None or rep['filed'] > out[kind]['filed']:  # by date added: some period ends are mislabelled
                out[kind] = rep
    for path in glob.glob(f'{localdata.USER_REPORTS}/{ticker}/*.json'):
        pe = os.path.basename(path)[:10]
        if out['annual'] is None or pe > out['annual']['period_end']:
            filed = date.fromtimestamp(os.path.getmtime(path)).isoformat()
            out['annual'] = {'form': 'your file', 'filed': filed, 'period_end': pe, 'url': ''}
    return out


def run_analysis(e):
    a = analyse(e['ticker'], assumptions=e.get('assumptions'), fcf_basis=e.get('fcf_basis', 'average'),
                follow='Watching' if e['mode'] == 'watch' else 'One-time', analysed=e.get('analysed'),
                company=e.get('company'))
    os.makedirs(ANALYSES, exist_ok=True)
    localdata.write_json(f"{ANALYSES}/{e['ticker']}.json", a, indent=1)
    return a


def cmd_add(args):
    entries = load()
    old = next((e for e in entries if e['ticker'] == args.ticker), None)
    if old and old.get('hidden'):  # analysed again after you removed it: it comes back with a fresh analysis
        entries.remove(old)
    elif old:
        raise SystemExit(f'{args.ticker} is already on the list; use set, watch or once')
    e = {'ticker': args.ticker, 'mode': 'once' if args.once else 'watch', 'added': date.today().isoformat(),
         'analysed': date.today().isoformat(), 'fcf_basis': 'normalised' if args.normalised else 'average'}
    if args.name:
        e['company'] = args.name
    if args.base is not None:
        e['assumptions'] = assumptions_from(args, {})
    a = run_analysis(e)
    e['company'] = a['candidate']['company']
    e['assumptions'] = a['assumptions']
    e['reports'] = latest_reports(args.ticker) if e['mode'] == 'watch' else None
    e['figures_to'] = a['last_period_end']
    e['below'] = below(a)
    entries.append(e)
    save(entries)
    c = a['candidate']
    journal_add(a, f"{'Added to the watchlist' if e['mode'] == 'watch' else 'One-time analysis'}: price "
                   f"{money(c['price'], c['currency'])} against a buy-below of {money(c['base'] * 0.7, c['currency'])} "
                   f"(base value minus 30%). {sum(r['result'] == 'Pass' for r in a['checks'])} of 10 checks pass. "
                   f"Growth assumptions: {a['assumptions'].get('source', 'set by hand')}.")
    out = {'added': args.ticker, 'candidate': c, 'assumptions': a['assumptions']}
    print(json.dumps(out, indent=1, ensure_ascii=False))
    return out


def assumptions_from(args, old):
    a = {k: v for k, v in old.items() if k in ('bear', 'base', 'bull')}
    for k in ('bear', 'base', 'bull'):
        if getattr(args, k) is not None:
            a[k] = getattr(args, k)
    if 'base' not in a:
        raise SystemExit('give at least --base')
    a.setdefault('bear', round(a['base'] / 2, 4))
    a.setdefault('bull', round(a['base'] * 1.5, 4))
    a['source'] = 'set by hand' + (', reviewed' if getattr(args, 'reviewed', False) else '')
    if getattr(args, 'reviewed', False):
        a['reviewed'] = True
    return a


def cmd_set(args):
    entries = load()
    e = entry_of(entries, args.ticker)
    if args.base is not None or args.bear is not None or args.bull is not None or args.reviewed:
        e['assumptions'] = assumptions_from(args, e.get('assumptions', {}))
    if args.normalised:
        e['fcf_basis'] = 'normalised'
    if args.average:
        e['fcf_basis'] = 'average'
    e['analysed'] = date.today().isoformat()
    a = run_analysis(e)
    e['below'] = below(a)
    save(entries)
    c = a['candidate']
    journal_add(a, f"Assumptions changed: growth {e['assumptions']['bear']:.1%} / {e['assumptions']['base']:.1%} / "
                   f"{e['assumptions']['bull']:.1%}, starting cash flow {c['fcf_basis']}. Base value now "
                   f"{money(c['base'], c['currency'])}.")
    out = {'updated': args.ticker, 'candidate': c}
    print(json.dumps(out, indent=1, ensure_ascii=False))
    return out


def cmd_mode(args, mode):
    entries = load()
    e = entry_of(entries, args.ticker)
    e['mode'] = mode
    if mode == 'watch':  # bring it up to date from today
        e['reports'] = latest_reports(args.ticker)
        e['analysed'] = date.today().isoformat()
    if not e.get('worked_example') or mode == 'watch':
        e.pop('worked_example', None)
        a = run_analysis(e)
        e['below'] = below(a)
    save(entries)
    print(f"{args.ticker}: {'watching' if mode == 'watch' else 'one-time analysis, no more updates'}")


def cmd_hide(args, hidden=True):
    """Take a company off the candidates list (hidden=True) or put it back. Its analysis and journal entries stay,
    so it can be put back exactly as it was; a hidden company gets no weekly updates."""
    entries = load()
    e = entry_of(entries, args.ticker)
    if hidden:
        e['hidden'] = date.today().isoformat()
    else:
        e.pop('hidden', None)
    save(entries)
    print(f"{args.ticker} {'removed from' if hidden else 'back on'} the candidates list")


def cmd_remove(args):
    entries = load()
    entry_of(entries, args.ticker)
    save([e for e in entries if e['ticker'] != args.ticker])
    path = f'{ANALYSES}/{args.ticker}.json'
    if os.path.exists(path):
        os.remove(path)
    print(f'{args.ticker} removed (its journal entries stay)')


def cmd_list(_):
    for e in load():
        print(f"{e['ticker']:10s} {e['mode']:5s} added {e['added']}  analysed {e.get('analysed')}  {e.get('company', '')}")


def cmd_check(args):
    """The weekly check. Every watched company gets fresh figures and a fresh price (one-time analyses are skipped);
    a new annual report is one whose year now shows up in the figures. Prints a JSON list of events."""
    import subprocess
    entries = load()
    events, problems, regions = [], [], set()
    for e in entries:
        if e['mode'] != 'watch' or e.get('hidden') or (args.ticker and e['ticker'] != args.ticker):
            continue
        t = e['ticker']
        try:
            old = json.load(open(f'{ANALYSES}/{t}.json', encoding='utf-8', errors='replace')) if os.path.exists(f'{ANALYSES}/{t}.json') else None
            rep = latest_reports(t)
            prev = e.get('reports') or {}
            regions.add(refresh(t, rerun=False)['region'])
            e['analysed'] = date.today().isoformat()
            a = run_analysis(e)
            c = a['candidate']
            if e.get('figures_to') and a['last_period_end'] > e['figures_to']:
                was = old['candidate'] if old else None
                passed = sum(r['result'] == 'Pass' for r in a['checks'])
                events.append({'ticker': t, 'company': c['company'], 'event': 'annual report', 'year_to': a['last_period_end'],
                               'report': rep['annual'], 'base_was': was and was['base'], 'base_now': c['base'],
                               'checks_passed': passed, 'decision': c['decision'], 'price': c['price'], 'currency': c['currency']})
                journal_add(a, f"New annual report (year to {a['last_period_end']}): figures, checks and valuation re-run. "
                               f"Base value {money(was['base'], c['currency']) + ' → ' if was else ''}"
                               f"{money(c['base'], c['currency'])}; {passed} of 10 checks pass.")
            elif rep['annual'] and prev.get('annual') and rep['annual']['filed'] > prev['annual']['filed']:
                problems.append({'ticker': t, 'problem': 'an annual report was filed but the free figures show no new year '
                                 '(a corrected re-filing, or not in the free data yet; the next check looks again)'})
            if rep['interim'] and (not prev.get('interim') or rep['interim']['filed'] > prev['interim']['filed']):
                events.append({'ticker': t, 'company': c['company'], 'event': 'interim report', 'report': rep['interim']})
            e['figures_to'] = a['last_period_end']
            now, then = below(a), e.get('below') or {}
            crossed = [int(m) for m in now if then.get(m) is not None and now[m] != then[m]]
            if crossed:
                into = [m for m in crossed if now[str(m)]]
                events.append({'ticker': t, 'company': c['company'], 'event': 'price crossed buy-below',
                               'into_buy_zone_at_margins': into, 'out_of_buy_zone_at_margins': [m for m in crossed if m not in into],
                               'price': c['price'], 'base': c['base'], 'currency': c['currency']})
                journal_add(a, f"Price {money(c['price'], c['currency'])} moved "
                               + ('to or below' if into else 'back above')
                               + f" the buy-below price at a {', '.join(f'{m}%' for m in sorted(crossed))} margin of safety "
                               f"(base value {money(c['base'], c['currency'])}).")
            e['below'] = now
            e['reports'] = rep
        except Exception as ex:  # one company's problem must not stop the others; it is reported
            problems.append({'ticker': t, 'problem': f'{type(ex).__name__}: {ex}'})
    save(entries)
    # the screener's offline steps, once per region that changed
    code = os.path.join(SCREENER, 'code')
    for region in sorted(regions):
        for script in ('crosscheck_yahoo.py', 'screen.py'):
            subprocess.run(localdata.python_cmd(f'{code}/{script}', region), check=True, capture_output=True, **localdata.hidden())
    if regions:
        subprocess.run(localdata.python_cmd(f'{code}/build_screen_data.py'), check=True, capture_output=True, **localdata.hidden())
    out = {'checked': [e['ticker'] for e in entries if e['mode'] == 'watch'], 'events': events, 'problems': problems,
           'at': date.today().isoformat()}
    print(json.dumps(out, indent=1, ensure_ascii=False))
    return out


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest='cmd', required=True)
    for name in ('add', 'set'):
        s = sub.add_parser(name)
        s.add_argument('ticker')
        for k in ('bear', 'base', 'bull'):
            s.add_argument(f'--{k}', type=float)
        s.add_argument('--normalised', action='store_true')
        s.add_argument('--reviewed', action='store_true', help='growth rates set after reading the annual report')
        if name == 'add':
            s.add_argument('--once', action='store_true')
            s.add_argument('--name')
        else:
            s.add_argument('--average', action='store_true')
    for name in ('watch', 'once', 'remove'):
        sub.add_parser(name).add_argument('ticker')
    sub.add_parser('list')
    sub.add_parser('check').add_argument('--ticker')
    args = p.parse_args()
    {'add': cmd_add, 'set': cmd_set, 'remove': cmd_remove, 'list': cmd_list, 'check': cmd_check,
     'watch': lambda a: cmd_mode(a, 'watch'), 'once': lambda a: cmd_mode(a, 'once')}[args.cmd](args)


if __name__ == '__main__':
    main()

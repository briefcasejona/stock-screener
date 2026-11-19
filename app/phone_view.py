"""A summary PDF of your candidates, scoreboard, course and journal, made only when you ask for it (Update data page)
and handed to you as a download: nothing is saved or synced by itself. Your real holdings and amounts are left out
unless you tick the box. It is a snapshot: prices are as of the moment it was made (shown at the top).
(Until 19 Nov 2026 this was an automatic "Phone view.pdf" in the data folder; the security review removed that.)"""
import html
import io
from datetime import datetime

import core

PAGE = (360, 640)  # a phone-shaped page, in points


def e(x):
    return html.escape('' if x is None else str(x))


def table(head, rows):
    if not rows:
        return ''
    out = '<table><tr>' + ''.join(f'<th>{e(h)}</th>' for h in head) + '</tr>'
    for r in rows:
        out += '<tr>' + ''.join(f'<td>{e(v)}</td>' for v in r) + '</tr>'
    return out + '</table>'


def candidates_part(d):
    import commit
    m = core.margin()
    wl = {x['ticker']: x for x in core.watchlist()}
    rows = []
    for c in d['candidates']:
        if not ((wl.get(c['ticker']) or {}).get('worked_example') or commit.get(c['ticker'])):
            rows.append([c['company'], core.money(c['price'], c['currency']), 'your estimate first', '', ''])
            continue
        bb = core.buy_below(c, m)
        mine, _ = core.my_decision(c, d['journal'])
        rows.append([c['company'], core.money(c['price'], c['currency']), core.money(bb, c['currency']),
                     f"{(c['price'] / bb - 1) * 100:+.0f}%".replace('-', '−'), mine or '—'])
    if not rows:
        return '<h2>Candidates</h2><p>No candidates yet.</p>'
    return (f'<h2>Candidates</h2><p class="s">Buy-below = base value minus your {m}% margin of safety. '
            '"vs" = how far the price is above (+) or below (−) it.</p>'
            + table(['Company', 'Price', 'Buy below', 'vs', 'Your decision'], rows))


def scoreboard_part(include_real=False):
    import portfolio as P
    state = P.load()
    if not state.get('rules') or not state.get('trades'):
        return '<h2>Scoreboard</h2><p>Nothing recorded yet.</p>'
    out = '<h2>Scoreboard</h2>'
    try:
        mk = P.markets(state)
    except Exception as ex:
        return out + f'<p>Prices could not be fetched when this was made ({e(ex)}).</p>'
    eur = lambda v: core.money(v, 'EUR')
    has_real = any(t['kind'] != 'index' and not P.is_paper(t) for t in state['trades'])
    for paper in ([True, False] if has_real and include_real else [True]):
        s = P.score(state, mk, paper=paper)
        out += f"<h3>{'Paper picks' if paper else 'Real picks'}</h3>"
        if not s.get('money_in'):
            out += '<p>No picks yet.</p>'
            continue
        out += table(['', 'Value', 'Return'], [
            ['Your picks', eur(s['picks_value']), f"{s['picks_return']:+.1%}"],
            ['Index fund, same money and days', eur(s['shadow_value']), f"{s['shadow_return']:+.1%}"]])
        out += f"<p>Picking {'added' if s['gap_points'] >= 0 else 'cost'} {abs(s['gap_points']):.1f} percentage points " \
               f"on {eur(s['money_in'])} put in.</p>"
        if s['holdings']:
            out += table(['Holding', 'Value', 'Share of all'],
                         [[h['company'], eur(h['value']), f"{h['share']:.1%}"] for h in s['holdings']])
    try:
        rows = P.passes_report(state)
    except Exception:
        rows = []
    if rows:
        out += '<h3>No and Wait decisions</h3>' + table(
            ['Company', 'Since', 'It did', 'Index fund', 'Kind'],
            [[r['company'], r['date'], f"{r['stock']:+.1%}", f"{r['index']:+.1%}", r['kind']] for r in rows])
    return out


def course_part():
    import course
    p = course.progress()
    step, n = course.next_step(p)
    nxt = {'before': 'two "before" write-ups', 'lesson': f'lesson {n}', 'solo': 'your own write-ups',
           'graduate': 'finish the course', 'done': 'done: real picks are open'}[step]
    return (f"<h2>Course</h2><p>Before write-ups: {p['before']} of 2 · lessons done: {len(p['lessons'])} of 6 · "
            f"own write-ups: {p['solo']} of 5 (with a No: {'yes' if p['solo_no'] else 'not yet'}). "
            f'Next: {e(nxt)}.</p>')


def journal_part(d, n=15):
    import commit
    wl = {w['ticker']: w for w in core.watchlist()}
    known = {c['company'] for c in d['candidates']}
    open_book = {c['company'] for c in d['candidates']
                 if (wl.get(c['ticker']) or {}).get('worked_example') or commit.get(c['ticker'])}
    entries = [x for x in d['journal'] if x.get('author') == 'You' or x['company'] not in known
               or x['company'] in open_book]
    entries = sorted(reversed(entries), key=lambda x: x['date'], reverse=True)[:n]
    if not entries:
        return ''
    out = f'<h2>Journal (latest {len(entries)})</h2>'
    for x in entries:
        out += (f"<p><b>{e(x['date'])} · {e(x['company'])} · {e(core.word(x.get('decision')))}</b> ({e(x.get('author', ''))})<br/>"
                f"{e(x.get('why', ''))}</p>")
    return out


CSS = """
body { font-family: sans-serif; font-size: 9pt; color: #1d1d1f; }
h1 { font-size: 15pt; margin: 0 0 2pt 0; }
h2 { font-size: 12pt; margin: 12pt 0 3pt 0; color: #0071e3; }
h3 { font-size: 10pt; margin: 8pt 0 2pt 0; }
p { margin: 2pt 0 4pt 0; }
.s { font-size: 7.5pt; color: #6e6e73; }
table { border-collapse: collapse; width: 100%; margin: 2pt 0 4pt 0; }
th { text-align: left; font-size: 7.5pt; color: #6e6e73; border-bottom: 0.5pt solid #d2d2d7; padding: 2pt; }
td { font-size: 8pt; border-bottom: 0.3pt solid #ececf0; padding: 2pt; }
"""


def build_html(include_real=False):
    d = core.load_dashboard()
    parts = [candidates_part(d)]
    for fn in (lambda: scoreboard_part(include_real), course_part):
        try:
            parts.append(fn())
        except Exception as ex:
            parts.append(f'<p>(a part could not be made: {e(ex)})</p>')
    parts.append(journal_part(d))
    made = datetime.now()
    head = (f'<h1>Stock Screener</h1><p class="s">Summary made {made:%a %d %b %Y, %H:%M}. Prices are as of then. '
            + ('' if include_real else 'Your real holdings and amounts are left out. ')
            + f'{e(core.DISCLAIMER)}</p>')
    return f'<html><body>{head}{"".join(parts)}</body></html>'


def pdf_bytes(include_real=False):
    """The PDF, in memory."""
    import pymupdf
    story = pymupdf.Story(html=build_html(include_real), user_css=CSS)
    buf = io.BytesIO()  # made in memory: on Windows the PDF library can keep its own file open a while
    writer = pymupdf.DocumentWriter(buf)
    rect = pymupdf.Rect(0, 0, *PAGE)
    where = rect + (18, 22, -18, -22)
    more = True
    while more:
        dev = writer.begin_page(rect)
        more, _ = story.place(where)
        story.draw(dev)
        writer.end_page()
    writer.close()
    return buf.getvalue()

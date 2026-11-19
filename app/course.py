"""The research course: your write-ups, your pass/fail rule, and graduation (which unlocks real picks).

A write-up is one company researched from start to finish: your own estimate written down first (Candidates page), at
least one claim, three figures checked in the annual report, and a decision (Buy, Wait or No).
- 2 "before" write-ups, before lesson 1;
- 1 write-up per lesson (6);
- 5 solo write-ups after the lessons, on companies not used before, at least one ending in "No".

The file is course.json in your data folder. Write-ups can't be edited or removed.
"""
import json
import os
import uuid
from datetime import date

import claims
import commit
import core

PATH = os.path.join(core.DATA, 'course.json')
BEFORE, SOLO = 2, 5
DECISIONS = ('Buy', 'Wait', 'No')


def load():
    try:
        s = json.load(open(PATH, encoding='utf-8', errors='replace'))
    except (OSError, ValueError):
        s = {}
    s.setdefault('writeups', [])
    return s


def save(s):
    core.localdata.write_json(PATH, s, indent=1)


def progress(s=None):
    s = load() if s is None else s
    w = s['writeups']
    lessons = sorted({x['lesson'] for x in w if x['kind'] == 'lesson'})
    solo = [x for x in w if x['kind'] == 'solo']
    return {'before': sum(x['kind'] == 'before' for x in w), 'lessons': lessons, 'solo': len(solo),
            'solo_no': sum(x['decision'] == 'No' for x in solo), 'rule': s.get('rule'),
            'graduated': s.get('graduated')}


def next_step(p):
    """('before' | 'lesson' | 'solo' | 'graduate' | 'done', lesson number or None)."""
    if p['graduated']:
        return 'done', None
    if p['before'] < BEFORE:
        return 'before', None
    for n in range(1, 7):
        if n not in p['lessons']:
            return 'lesson', n
    if p['solo'] < SOLO or p['solo_no'] < 1:
        return 'solo', None
    return 'graduate', None


def set_rule(text):
    s = load()
    if s.get('rule'):
        raise ValueError('Your pass/fail rule is already written down; it stays as it is, so the test stays honest.')
    if not text.strip():
        raise ValueError('Write the rule first.')
    s['rule'] = {'date': date.today().isoformat(), 'text': text.strip()}
    save(s)
    core.add_journal_entry({'date': s['rule']['date'], 'ticker': 'COURSE', 'company': 'The course', 'price': None,
                            'currency': '', 'decision': 'Pass/fail rule', 'why': s['rule']['text'], 'change_mind': '',
                            'next_check': 'After 24 months of claims', 'author': 'You'})


# figure names the program also has, so a write-up can put your figure next to the program's
PROGRAM = [(('free cash flow per share', 'fcf per share', 'fcf/share'), 'fcf_per_share', '{:.2f} per share'),
           (('earnings per share', 'eps'), 'eps', '{:.2f} per share'),
           (('free cash flow', 'fcf'), 'fcf_m', '{:,.0f} million'),
           (('cash from operations', 'operating cash flow', 'cash flow from operations', 'operating activities'),
            'operating_cash_flow_m', '{:,.0f} million'),
           (('operating income', 'operating profit', 'operating result', 'ebit'), 'operating_income_m', '{:,.0f} million'),
           (('net profit', 'net income', 'net earnings', 'profit for the year'), 'net_income_m', '{:,.0f} million'),
           (('capital spending', 'capex', 'capital expenditure'), 'capex_m', '{:,.0f} million'),
           (('revenue', 'sales', 'turnover', 'omzet'), 'revenue_m', '{:,.0f} million'),
           (('roic', 'return on invested capital', 'return on capital'), 'roic', '{:.1%}'),
           (('gross margin',), 'gross_margin', '{:.1%}')]


def program_value(name, history, company):
    """The program's figure for a figure you checked, e.g. 'revenue 2025' -> 'revenue 2025: 10,800 million', or ''."""
    import re
    n = name.lower()
    rows = sorted((h for h in (history or []) if h.get('company') == company), key=lambda h: h['year'])
    if not rows:
        return ''
    y = re.search(r'(19|20)\d\d', n)
    row = next((h for h in rows if y and h['year'] == int(y.group())), rows[-1])
    for words, key, fmt in PROGRAM:
        if any(w in n for w in words) and row.get(key) is not None:
            return f"{row['year']}: {fmt.format(row[key])}"
    return ''


def not_ready(c):
    """Why candidate `c` can't get a write-up yet, or None when it can."""
    if not commit.get(c['ticker']) and any(e['ticker'] == c['ticker'] and e.get('worked_example') for e in core.watchlist()):
        return (f"{c['company']} is the worked example: you have already seen the program's numbers for it, so it can't "
                'be a write-up. Pick another company.')
    if not commit.get(c['ticker']):
        return f"Write down your own estimate for {c['company']} first, on the Candidates page."
    if not any(x['ticker'] == c['ticker'] and x['made'] >= commit.get(c['ticker'])['date'] for x in claims.load()):
        return f"Make at least one claim about {c['company']} first (Candidates page, Journal tab)."
    return None


def add(c, decision, figures, summary, history=None):
    """Record a write-up on candidate `c` for the current step. `figures`: 3 x {'name', 'report', 'program'}; the
    program's own figure is filled in from `history` where the name matches one it has."""
    s = load()
    p = progress(s)
    kind, lesson = next_step(p)
    if kind in ('graduate', 'done'):
        raise ValueError('All write-ups are done.')
    if decision not in DECISIONS:
        raise ValueError('Pick Buy, Wait or No.')
    why = not_ready(c)
    if why:
        raise ValueError(why)
    figures = [{**f, 'name': f['name'].strip(), 'report': f['report'].strip()} for f in figures]
    figures = [f for f in figures if len(f['name']) >= 3 and len(f['report']) >= 6 and any(ch.isdigit() for ch in f['report'])]
    if len(figures) < 3:
        raise ValueError('Check three figures in the annual report: name each one (for example "revenue 2025") and write '
                         'what the report says, with the number and the page (for example "10.8 bn USD, page 52").')
    if len({f['name'].lower() for f in figures}) < 3:
        raise ValueError('Check three different figures.')
    if len(summary.strip()) < 30:
        raise ValueError('Write your conclusion in one or two full lines: what you found and why it leads to your decision.')
    for f in figures:
        f['program'] = f.get('program') or program_value(f['name'], history, c['company'])
    if kind == 'before' and any(x['ticker'] == c['ticker'] for x in s['writeups']):
        raise ValueError('Your two "before" write-ups are on two different companies. Pick another one.')
    if kind == 'lesson' and sum(x['ticker'] == c['ticker'] for x in s['writeups'] if x['kind'] == 'lesson') >= 2:
        raise ValueError(f"You have done two lessons on {c['company']} already. Do this one on another company: "
                         'the skill is in seeing different businesses.')
    if kind == 'solo' and any(x['ticker'] == c['ticker'] for x in s['writeups']):
        raise ValueError('A solo write-up is on a company you have not written up before. Pick another one.')
    if kind == 'solo' and p['solo'] == SOLO - 1 and p['solo_no'] == 0 and decision != 'No':
        raise ValueError('At least one solo write-up ends in "No". This is your last one, so pick a company you would '
                         'say No to, or keep looking. Saying No well is half the skill.')
    w = {'id': uuid.uuid4().hex[:10], 'date': date.today().isoformat(), 'kind': kind, 'lesson': lesson,
         'ticker': c['ticker'], 'company': c['company'], 'decision': decision, 'figures': figures[:3],
         'summary': summary.strip(), 'price': c.get('price'), 'currency': c.get('currency')}
    s['writeups'].append(w)
    save(s)
    label = {'before': 'Before write-up', 'lesson': f'Lesson {lesson} write-up', 'solo': 'Solo write-up'}[kind]
    core.add_journal_entry({'date': w['date'], 'ticker': c['ticker'], 'company': c['company'], 'price': c.get('price'),
                            'currency': c.get('currency', ''), 'decision': label,
                            'why': f"{label}, decision {decision}: {w['summary']} Checked in the annual report: "
                                   + '; '.join(f"{f['name']} {f['report']}" + (f" (program: {f['program']})" if f['program'] else '')
                                             for f in figures[:3]) + '.',
                            'change_mind': '', 'next_check': '', 'author': 'You'})
    if decision in ('No', 'Wait'):
        import portfolio
        try:
            portfolio.add_pass(c, w['summary'], kind=decision,
                               buy_below=core.buy_below(c, core.margin()) if decision == 'Wait' else None)
        except Exception as e:
            print('tracking the decision:', e)
    return w


def graduate():
    """All steps done: mark the course finished and unlock real picks on the Scoreboard."""
    import portfolio
    s = load()
    if next_step(progress(s))[0] != 'graduate':
        raise ValueError('Not all steps are done yet.')
    s['graduated'] = date.today().isoformat()
    save(s)
    state = portfolio.load()
    if state.get('rules'):
        state['rules']['real_unlocked'] = True
        portfolio.save(state)
    core.add_journal_entry({'date': s['graduated'], 'ticker': 'COURSE', 'company': 'The course', 'price': None,
                            'currency': '', 'decision': 'Course finished',
                            'why': 'All six lessons and five solo write-ups done. Real picks are unlocked on the '
                                   'Scoreboard; start small. Whether your judgement is good shows in your claims '
                                   '(after 18-24 months) and the Scoreboard (after 3-5 years).',
                            'change_mind': '', 'next_check': '', 'author': 'The program'})

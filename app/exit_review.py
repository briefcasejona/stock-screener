"""The DeGiro exit review: for each holding at DeGiro, your decision (keep it and move it to IBKR, trim it, or sell it)
and why, written in the journal BEFORE the program shows its price and your gain on it. A price you paid or a gain
you have pulls a decision toward "wait until it is back up"; what counts is only whether you would buy it today.

The decisions are journal entries (author "You", field "exit_review" = the holding's ISIN), never edited.
"""
import json
import os
from datetime import date

import core
import holdings as H

BROKER = 'DeGiro'
CHOICES = ('Keep (move to IBKR)', 'Trim', 'Sell')
WORD = {'Keep (move to IBKR)': 'Keep', 'Trim': 'Trim', 'Sell': 'Sell'}
NO_CGT = ('In the Netherlands there is no tax on a gain when you sell: Box 3 taxes what you own on 1 January, whether '
          'you keep a holding or sell it. So a gain or a loss is no reason by itself to keep or to sell. Selling costs '
          'the broker\'s fee and the difference between the buying and selling price; moving a holding to IBKR may '
          'cost a transfer fee (ask both brokers).')


def holdings_at_degiro(s=None):
    """[(isin, name, units at DeGiro, held since)] for every holding still at DeGiro."""
    s = H.load() if s is None else s
    pos, _ = H.positions(s, broker=BROKER)
    out = []
    for isin, p in pos.items():
        u = p['by_broker'].get(BROKER, 0.0)
        if u > 1e-9:
            out.append((isin, (s['securities'].get(isin) or {}).get('name') or isin, u, p['first']))
    return sorted(out, key=lambda x: x[1].lower())


def journal():
    path = f'{core.JOURNAL_DIR}/journal.json'
    try:
        return json.load(open(path, encoding='utf-8', errors='replace'))
    except (OSError, ValueError):
        return []


def written(entries=None):
    """{isin: your latest exit-review entry}."""
    out = {}
    for e in journal() if entries is None else entries:
        if e.get('exit_review') and e.get('author') == 'You':
            out[e['exit_review']] = e
    return out


def write(isin, company, choice, why, change_mind, trim_pct=None):
    """Your decision on one DeGiro holding, in the journal. Raises ValueError when something is missing."""
    if choice not in CHOICES:
        raise ValueError('Choose keep, trim or sell.')
    if not core.words(why, least=10):
        raise ValueError('Write why in a sentence or two (ten words at least): what the company does for you, and '
                         'whether you would buy it today.')
    if choice == 'Trim' and not (trim_pct and 0 < trim_pct < 100):
        raise ValueError('Say how much of it you would sell (between 1% and 99%).')
    what = WORD[choice] + (f' {trim_pct:.0f}%' if choice == 'Trim' else '')
    return core.add_journal_entry({
        'date': date.today().isoformat(), 'ticker': isin, 'company': company, 'price': None, 'currency': '',
        'decision': WORD[choice], 'why': f'DeGiro exit review, {what}: {why.strip()}',
        'change_mind': (change_mind or '').strip(), 'next_check': '', 'author': 'You', 'exit_review': isin,
        **({'trim_pct': trim_pct} if choice == 'Trim' else {})})

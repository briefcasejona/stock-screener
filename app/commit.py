"""Commit first: for each company, your own growth rate and fair value, written down before the program shows its
valuation and its 10 checks. Locked once written; the program's numbers are then shown next to yours.

The file is commitments.json in your data folder (one entry per company, never changed afterwards).
"""
import json
import os
from datetime import date

import core

PATH = os.path.join(core.DATA, 'commitments.json')


def load():
    try:
        return json.load(open(PATH, encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def get(ticker):
    return load().get(ticker)


def new(c, growth, value, why):
    """Lock in your estimate for candidate `c` (growth in %, value per share in the price's currency)."""
    if not why.strip():
        raise ValueError('Write one line on why.')
    if value <= 0:
        raise ValueError('Fill in what you think one share is worth.')
    allc = load()
    if c['ticker'] in allc:
        raise ValueError('Your estimate for this company is already written down.')
    e = {'date': date.today().isoformat(), 'growth': float(growth), 'value': float(value), 'currency': c['currency'],
         'price': c['price'], 'why': why.strip()}
    allc[c['ticker']] = e
    core.localdata.write_json(PATH, allc, indent=1)
    core.add_journal_entry({'date': e['date'], 'ticker': c['ticker'], 'company': c['company'], 'price': c['price'],
                            'currency': c['currency'], 'decision': 'My estimate',
                            'why': f"Before seeing the program's valuation: free cash flow grows {growth:.1f}% a year, "
                                   f"one share is worth {core.money(value, c['currency'])}. {why.strip()}",
                            'change_mind': '', 'next_check': '', 'author': 'You'})
    return e

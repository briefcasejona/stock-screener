"""Scored claims: dated statements about a company that can turn out wrong, checked by the program itself.

A claim says, for example, "free cash flow per share grows at least 8% a year from FY2025 to FY2027, 70% sure".
It is locked when written. Once the company's figures for the target year are in (the weekly check or a full refresh
fetches them), the program works out what happened from the filed figures and marks the claim true or false.

Each claim is also compared with a simple forecast that needs no research: "the last three years' trend continues"
(for a margin: "it stays where it was"). Over many claims, two questions show whether your research adds something:
- do your claims come true more often than the simple forecast gets them right?
- do your 80%-sure claims come true about 80% of the time (are you as sure as you should be)?

The file is claims.json in your data folder.
"""
import csv
import json
import os
import uuid
from datetime import date

import core

PATH = os.path.join(core.DATA, 'claims.json')
METRICS = {
    'revenue': ('Revenue', 'growth'),
    'fcf_ps': ('Free cash flow per share', 'growth'),
    'op_margin': ('Operating margin', 'level'),
}
CONFIDENCE = (55, 60, 70, 80, 90)


def load():
    try:
        return json.load(open(PATH, encoding='utf-8'))
    except (OSError, ValueError):
        return []


def save(claims):
    core.localdata.write_json(PATH, claims, indent=1)


def years(ticker):
    """{fiscal year: {'revenue', 'fcf_ps', 'op_margin'}} from the screener's figures (filed reports)."""
    from refresh_company import find
    import screen as scr
    region, _ = find(ticker)
    rows = [r for r in csv.DictReader(open(f'{core.SCREENER}/output/figures_{region}.csv', encoding='utf-8'))
            if r['ticker'] == ticker]
    out = {}
    for y in scr.per_year(rows):
        out[y['year']] = {'revenue': y['revenue'], 'fcf_ps': y['fcf_ps'],
                          'op_margin': (y['operating_income'] / y['revenue']
                                        if y['operating_income'] is not None and y['revenue'] else None)}
    return out


def cagr(a, b, n):
    if a is None or b is None or a <= 0 or n <= 0:
        return None
    if b <= 0:
        return -1.0
    return (b / a) ** (1 / n) - 1


def describe(c):
    name, kind = METRICS[c['metric']]
    word = 'at least' if c['direction'] == 'above' else 'at most'
    if kind == 'growth':
        return (f"{name} grows {word} {c['threshold']:.1f}% a year from FY{c['base_year']} to FY{c['target_year']}")
    return f"{name} is {word} {c['threshold']:.1f}% in FY{c['target_year']}"


def holds(c, value):
    """Is the claim true for this value (a growth rate or margin, as a fraction)?"""
    if value is None:
        return None
    t = c['threshold'] / 100
    return value >= t if c['direction'] == 'above' else value <= t


def naive_value(c, ys):
    """The simple forecast: the 3 years before the base year's trend continues (growth); the margin stays (level)."""
    b = c['base_year']
    if METRICS[c['metric']][1] == 'growth':
        return cagr((ys.get(b - 3) or {}).get(c['metric']), (ys.get(b) or {}).get(c['metric']), 3)
    return (ys.get(b) or {}).get(c['metric'])


def new(ticker, company, metric, direction, threshold, target_year, confidence, why, source='journal'):
    """Write a claim. The base year is the last year with figures now; the target 1-3 years after it."""
    ys = years(ticker)
    if not ys:
        raise ValueError(f'No yearly figures for {company} yet.')
    base = max(ys)
    if not base < target_year <= base + 3:
        raise ValueError(f'The target year must be 1 to 3 years after FY{base}, the last year with figures.')
    if METRICS[metric][1] == 'growth' and not (ys[base].get(metric) or 0) > 0:
        raise ValueError(f'{METRICS[metric][0]} in FY{base} is not positive, so a growth rate from it means nothing. '
                         'Pick another measure.')
    if not why.strip():
        raise ValueError('Write one line on why you expect this.')
    c = {'id': uuid.uuid4().hex[:10], 'made': date.today().isoformat(), 'ticker': ticker, 'company': company,
         'metric': metric, 'direction': direction, 'threshold': float(threshold), 'base_year': base,
         'target_year': int(target_year), 'confidence': int(confidence), 'why': why.strip(), 'source': source,
         'base_value': ys[base].get(metric)}
    nv = naive_value(c, ys)
    c['naive_value'], c['naive_says'] = nv, holds(c, nv)
    claims = load()
    claims.append(c)
    save(claims)
    core.add_journal_entry({'date': c['made'], 'ticker': ticker, 'company': company, 'price': None, 'currency': '',
                            'decision': 'Claim', 'why': f"Claim ({c['confidence']}% sure): {describe(c)}. {c['why']}",
                            'change_mind': '', 'next_check': f"When the FY{c['target_year']} figures are in",
                            'author': 'You'})
    return c


def check_all():
    """Mark every open claim whose target year's figures are in. Returns the claims just settled."""
    claims, settled, cache = load(), [], {}
    for c in claims:
        if c.get('outcome') is not None:
            continue
        try:
            ys = cache.setdefault(c['ticker'], years(c['ticker']))
        except Exception:
            continue
        end = (ys.get(c['target_year']) or {}).get(c['metric'])
        if end is None:
            continue
        if METRICS[c['metric']][1] == 'growth':
            actual = cagr((ys.get(c['base_year']) or {}).get(c['metric']), end, c['target_year'] - c['base_year'])
        else:
            actual = end
        if actual is None:
            continue
        c.update(actual=actual, outcome=holds(c, actual), checked=date.today().isoformat())
        settled.append(c)
    if settled:
        save(claims)
        for c in settled:
            core.add_journal_entry({'date': c['checked'], 'ticker': c['ticker'], 'company': c['company'], 'price': None,
                                    'currency': '', 'decision': 'Claim checked',
                                    'why': f"{'Came true' if c['outcome'] else 'Did not come true'}: {describe(c)} "
                                           f"(it was {c['actual']:.1%}; you were {c['confidence']}% sure). The simple "
                                           f"forecast {'got it right' if c['naive_says'] == c['outcome'] else 'got it wrong'}.",
                                    'change_mind': '', 'next_check': '', 'author': 'The program'})
    return settled


def report(claims=None):
    """How your claims are doing: counts, hit rate against the simple forecast, and calibration per confidence."""
    claims = load() if claims is None else claims
    done = [c for c in claims if c.get('outcome') is not None]
    out = {'open': sum(1 for c in claims if c.get('outcome') is None), 'settled': len(done)}
    if done:
        out['hit'] = sum(c['outcome'] for c in done) / len(done)
        known = [c for c in done if c.get('naive_says') is not None]
        out['naive_hit'] = sum(c['naive_says'] == c['outcome'] for c in known) / len(known) if known else None
        bands = {}
        for c in done:
            bands.setdefault(c['confidence'], []).append(c['outcome'])
        out['calibration'] = {k: (sum(v) / len(v), len(v)) for k, v in sorted(bands.items())}
    return out

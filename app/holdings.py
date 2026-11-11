"""Your real portfolio, from your brokers' own records.

Nothing here is typed in by hand: the records come from the exports of your brokers (IBKR, DeGiro), read in on the
Portfolio page, and are checked against each broker's own statement. One record per thing that happened at a broker:

    deposit / withdrawal    money in from your bank, money out to your bank
    buy / sell              shares bought or sold (units, price, currency, costs)
    dividend / tax          a dividend paid, and dividend tax kept abroad (a negative amount)
    fee / interest          broker costs that are not part of a trade, interest paid or received
    adjust                  a small cash difference you accepted, when the broker's own file doesn't add up to its
                            own balance (shown, never hidden)
    fx                      money changed from one currency into another at the broker
    position_in / _out      shares moved between brokers (keeps the original cost)

Every record says what it did to the broker's cash, per currency (`cash`), and, for shares, how many (`units`).
A withdrawal at one broker that is followed by a deposit of the same money at the other is marked `internal`: it is
your own money moving between your brokers, not new money, so it doesn't count in your return.

The file is holdings.json in your data folder. Prices, exchange rates, sectors and dividends come from Yahoo Finance.
"""
import json
import os
import uuid
from datetime import date, timedelta

import core
import portfolio as P

PATH = os.path.join(core.DATA, 'holdings.json')
BROKERS = ('IBKR', 'DeGiro')
EXTERNAL = ('deposit', 'withdrawal')
COST_KINDS = ('fee',)


# ---------- the file ----------

def load():
    try:
        s = json.load(open(PATH, encoding='utf-8', errors='replace'))
    except (OSError, ValueError):
        s = {}
    s.setdefault('events', [])
    s.setdefault('securities', {})  # isin -> {name, symbol, kind ('index' | 'stock'), sector, country}
    s.setdefault('imports', [])
    s.setdefault('checks', [])
    return s


def save(s):
    core.localdata.write_json(PATH, s, indent=1)


def add_events(s, events, broker, source):
    """Add records read from a broker's file. A record already there (same broker and same `ref`) is skipped, so
    reading the same file twice, or two overlapping files, adds nothing twice. Returns how many were new."""
    seen = {(e['broker'], e['ref']) for e in s['events']}
    new = 0
    for e in events:
        e = {**e, 'broker': broker}
        if (broker, e['ref']) in seen:
            continue
        seen.add((broker, e['ref']))
        e['id'] = uuid.uuid4().hex[:10]
        s['events'].append(e)
        new += 1
        if e.get('isin') and e['isin'] not in s['securities']:
            s['securities'][e['isin']] = {'name': e.get('name') or e['isin'], 'symbol': e.get('symbol'),
                                          'kind': None, 'sector': None, 'country': None}
    s['imports'].append({'broker': broker, 'file': source, 'at': date.today().isoformat(), 'new': new})
    s['events'].sort(key=lambda e: (e['date'], e.get('ref', '')))
    return new


def internal_candidates(s, days=10, tolerance=0.01):
    """Withdrawals at one broker matched with a deposit of the same euros at the other within `days`: probably your own
    money moving between your brokers. [(withdrawal, deposit)] not yet marked."""
    outs = [e for e in s['events'] if e['kind'] == 'withdrawal' and not e.get('internal')]
    ins = [e for e in s['events'] if e['kind'] == 'deposit' and not e.get('internal')]
    pairs, used = [], set()
    for w in outs:
        for d in ins:
            if d['id'] in used or d['broker'] == w['broker']:
                continue
            gap = (date.fromisoformat(d['date']) - date.fromisoformat(w['date'])).days
            if 0 <= gap <= days and abs(eur_of(w) + eur_of(d)) <= tolerance * abs(eur_of(w)):
                pairs.append((w, d))
                used.add(d['id'])
                break
    return pairs


def mark_internal(s, ids, on=True):
    for e in s['events']:
        if e['id'] in ids:
            e['internal'] = on
    save(s)


def eur_of(e):
    """The record's cash effect in euros, at the exchange rate the broker used (or Yahoo's of that day)."""
    if e.get('eur') is not None:
        return e['eur']
    total = 0.0
    for cur, amt in e.get('cash', {}).items():
        total += amt * fx_on(cur, e['date'])
    return total


_fx_cache = {}


def fx_on(cur, day):
    if cur in (None, 'EUR'):
        return 1.0
    if cur not in _fx_cache:
        _fx_cache[cur] = P.fx_series(cur, '2000-01-01')
    return P.on(_fx_cache[cur], day)


# ---------- prices ----------

def markets(s, start=None):
    """Prices and dividends for every holding that has a Yahoo symbol, and the exchange rates needed."""
    syms = {v['symbol'] for v in s['securities'].values() if v.get('symbol')}
    first = start or min((e['date'] for e in s['events']), default=date.today().isoformat())
    begin = (date.fromisoformat(first) - timedelta(days=10)).isoformat()
    out = {'start': begin, 'm': {}, 'fx': {}}
    curs = {c for e in s['events'] for c in e.get('cash', {})}
    for sym in syms:
        try:
            out['m'][sym] = P.market(sym, begin)
            curs.add(out['m'][sym]['currency'])
        except Exception as ex:
            out['m'][sym] = {'error': str(ex)}
    for c in curs:
        out['fx'][c] = P.fx_series(c, begin)
    return out


def price_eur(mk, sym, day):
    m = mk['m'].get(sym)
    if not m or 'close' not in m:
        return None
    return P.on(m['close'], day) * P.on(mk['fx'].get(m['currency']), day)


# ---------- folding the records ----------

def positions(s, day=None, broker=None):
    """Per holding (isin): units, costs paid, money paid (incl. costs) and received, dividends net, per broker. And
    cash per broker per currency. As of `day` (iso, default today)."""
    day = day or date.today().isoformat()
    pos, cash = {}, {}
    for e in s['events']:
        if e['date'] > day or (broker and e['broker'] != broker):
            continue
        for cur, amt in e.get('cash', {}).items():
            k = (e['broker'], cur)
            cash[k] = cash.get(k, 0.0) + amt
        isin = e.get('isin')
        if not isin:
            continue
        p = pos.setdefault(isin, {'units': 0.0, 'costs_eur': 0.0, 'paid_eur': 0.0, 'received_eur': 0.0,
                                  'dividends_eur': 0.0, 'by_broker': {}, 'first': e['date']})
        k = e['kind']
        if k in ('buy', 'position_in'):
            u = e['units']
        elif k in ('sell', 'position_out'):
            u = -e['units']
        elif k == 'corp':  # a split, merger or spin-off: the broker's own change in shares, with its sign
            u = e['units']
        else:
            u = 0.0
        p['units'] += u
        p['by_broker'][e['broker']] = p['by_broker'].get(e['broker'], 0.0) + u
        p['costs_eur'] += e.get('costs_eur', 0.0)
        if k == 'buy':
            p['paid_eur'] += -eur_of(e)
        elif k == 'sell':
            p['received_eur'] += eur_of(e)
        elif k == 'position_in':
            p['paid_eur'] += e.get('cost_eur', 0.0)
        elif k in ('dividend', 'tax'):
            p['dividends_eur'] += eur_of(e)
    return pos, cash


def total_value(s, mk, day=None):
    """(holdings value, cash value, missing prices) in euros on `day`."""
    day = day or date.today().isoformat()
    pos, cash = positions(s, day)
    hv, missing = 0.0, []
    for isin, p in pos.items():
        if abs(p['units']) < 1e-9:
            continue
        sym = s['securities'].get(isin, {}).get('symbol')
        px = price_eur(mk, sym, day) if sym else None
        if px is None:
            missing.append(isin)
            continue
        hv += p['units'] * px
    cv = sum(amt * P.on(mk['fx'].get(cur), day) if cur != 'EUR' else amt for (_, cur), amt in cash.items())
    return hv, cv, missing


def flows(s, frm=None, to=None):
    """Money you put in (+) and took out (−) from your bank, in euros, by date. Moves between your brokers are left
    out (internal)."""
    out = []
    for e in s['events']:
        if e['kind'] in EXTERNAL and not e.get('internal') and (frm is None or e['date'] > frm) \
                and (to is None or e['date'] <= to):
            out.append((e['date'], eur_of(e)))
    return out


# ---------- returns ----------

def xirr(cashflows):
    """The yearly rate r at which sum(cf / (1+r)^(years since the first)) = 0. `cashflows` = [(iso date, amount)],
    money you put in negative. None when it can't be found."""
    if len(cashflows) < 2:
        return None
    d0 = date.fromisoformat(min(d for d, _ in cashflows))
    cf = [((date.fromisoformat(d) - d0).days / 365.25, a) for d, a in cashflows]
    if not (any(a < 0 for _, a in cf) and any(a > 0 for _, a in cf)):
        return None
    f = lambda r: sum(a / (1 + r) ** t for t, a in cf)
    lo, hi = -0.9999, 10.0
    flo, fhi = f(lo), f(hi)
    if flo * fhi > 0:
        return None
    for _ in range(200):  # bisection: slow but never wanders off
        mid = (lo + hi) / 2
        fm = f(mid)
        if abs(fm) < 1e-7:
            break
        if flo * fm < 0:
            hi, fhi = mid, fm
        else:
            lo, flo = mid, fm
    return (lo + hi) / 2


def money_weighted(s, mk, today=None):
    """Your real return per year since your first deposit, counting each euro from the day it went in (XIRR), and the
    same for the same euros put into your index fund on the same days."""
    today = today or date.today().isoformat()
    f = flows(s, to=today)
    if not f:
        return None
    hv, cv, missing = total_value(s, mk, today)
    mine = xirr([(d, -a) for d, a in f] + [(today, hv + cv)])
    idx = index_symbol(s)
    shadow = None
    if idx and price_eur(mk, idx, today):
        units = sum(a / price_eur(mk, idx, d) for d, a in f)
        shadow = xirr([(d, -a) for d, a in f] + [(today, units * price_eur(mk, idx, today))])
    return {'yours': mine, 'index': shadow, 'put_in': sum(a for _, a in f), 'value': hv + cv, 'missing': missing}


def period_return(s, mk, start, end):
    """The money-weighted return over one period (a month, a year), not per year: modified Dietz, the standard way to
    leave the money you added out of the result. (start, end) iso dates; start is the day before the period."""
    v0 = sum(total_value(s, mk, start)[:2])
    v1 = sum(total_value(s, mk, end)[:2])
    f = flows(s, frm=start, to=end)
    days = (date.fromisoformat(end) - date.fromisoformat(start)).days or 1
    net = sum(a for _, a in f)
    weighted = sum(a * (date.fromisoformat(end) - date.fromisoformat(d)).days / days for d, a in f)
    base = v0 + weighted
    if base <= 0:
        return None
    return {'return': (v1 - v0 - net) / base, 'gain': v1 - v0 - net, 'start_value': v0, 'end_value': v1,
            'added': net}


def month_and_year(s, mk, today=None):
    """The last full month and the calendar year so far (and the last full year), for your journal."""
    t = date.fromisoformat(today) if today else date.today()
    first_this = t.replace(day=1)
    last_month_end = first_this - timedelta(days=1)
    before_last_month = last_month_end.replace(day=1) - timedelta(days=1)
    jan1 = t.replace(month=1, day=1)
    first = min((e['date'] for e in s['events']), default=None)
    out = {}
    for k, label, start, end in (
            ('month', last_month_end.strftime('%B %Y'), before_last_month, last_month_end),
            ('ytd', f'{t.year} so far', jan1 - timedelta(days=1), t),
            ('last_year', str(t.year - 1), date(t.year - 2, 12, 31), date(t.year - 1, 12, 31))):
        if first is None or first > end.isoformat():
            out[k] = (label, None)
            continue
        # records that start inside the period (your first deposit): from then on, starting at zero
        frm = max(start, date.fromisoformat(first) - timedelta(days=1))
        r = period_return(s, mk, frm.isoformat(), end.isoformat())
        if r is not None and frm > start:
            r['from'] = (frm + timedelta(days=1)).isoformat()
        out[k] = (label, r)
    return out


def box3_value(s, mk, year=None):
    """Your holdings and cash on 1 January (the day Box 3 looks at), both brokers together."""
    y = year or date.today().year
    day = date(y, 1, 1).isoformat()
    hv, cv, missing = total_value(s, mk, day)
    return {'date': day, 'holdings': hv, 'cash': cv, 'total': hv + cv, 'missing': missing}


def index_symbol(s):
    st = P.load()
    return (st.get('rules') or P.DEFAULT_RULES)['index_symbol']


# ---------- what each holding is ----------

def describe(sym):
    """(kind, sector, country) from Yahoo. An ETF or fund is 'index' with no sector or country: a fund owns many
    companies, and Yahoo's labels for funds are not reliable."""
    import yfinance as yf
    info = yf.Ticker(sym).info or {}
    if info.get('quoteType') in ('ETF', 'MUTUALFUND'):
        return 'index', None, None
    return 'stock', info.get('sector'), info.get('country')


def find_symbol(isin):
    """Yahoo symbols for an ISIN, best first: [(symbol, name, exchange)]."""
    import yfinance as yf
    try:
        q = yf.Search(isin, max_results=8).quotes
    except Exception:
        return []
    return [(x['symbol'], x.get('longname') or x.get('shortname') or '', x.get('exchDisp') or x.get('exchange', ''))
            for x in q if x.get('symbol')]


def dividend_outlook(s, mk):
    """Per stock you hold: what it paid per share over the last 12 months (Yahoo), the months it paid in, and what
    that would be on your shares now, before dividend tax. An estimate from last year's payments, not a promise."""
    today = date.today()
    year_ago = (today - timedelta(days=365)).isoformat()
    pos, _ = positions(s)
    out = []
    for isin, p in pos.items():
        sec = s['securities'].get(isin, {})
        m = mk['m'].get(sec.get('symbol') or '')
        if p['units'] < 1e-9 or not m or 'div' not in m:
            continue
        paid = {d: a for d, a in m['div'].items() if d > year_ago}
        if not paid:
            continue
        per_share = sum(paid.values())
        fx = P.on(mk['fx'].get(m['currency']), today.isoformat())
        out.append({'isin': isin, 'name': sec.get('name'), 'currency': m['currency'], 'per_share_12m': per_share,
                    'months': sorted({date.fromisoformat(d).strftime('%b') for d in paid},
                                     key=lambda x: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep',
                                                    'Oct', 'Nov', 'Dec'].index(x)),
                    'yearly_eur': p['units'] * per_share * fx})
    return out


# ---------- checking against the broker ----------

def reconcile(s, broker, statement, mk=None):
    """Compare what the records add up to with the broker's own statement of the same day.
    `statement` = {'date': iso, 'units': {isin: units}, 'cash': {currency: amount}}. Returns the differences (an empty
    list when everything matches to the cent / to the share)."""
    pos, cash = positions(s, statement['date'], broker)
    diffs = []
    for isin in set(statement['units']) | {i for i, p in pos.items() if abs(p['units']) > 1e-9}:
        mine = pos.get(isin, {}).get('units', 0.0)
        theirs = statement['units'].get(isin, 0.0)
        if abs(mine - theirs) > 1e-6:
            diffs.append({'what': s['securities'].get(isin, {}).get('name', isin), 'records': mine, 'broker': theirs})
    mycash = {cur: amt for (b, cur), amt in cash.items() if b == broker}
    for cur in set(statement['cash']) | set(mycash):
        a, b = round(mycash.get(cur, 0.0), 2), round(statement['cash'].get(cur, 0.0), 2)
        if round(a * 100) != round(b * 100):  # whole cents, so 49.99 vs 50.00 is never lost to rounding
            diffs.append({'what': f'cash {cur}', 'records': a, 'broker': b})
    s['checks'].append({'broker': broker, 'date': statement['date'], 'checked': date.today().isoformat(),
                        'ok': not diffs, 'differences': len(diffs), 'details': diffs})
    return diffs


def accept_difference(s, broker, currency, amount, day):
    """Record a small cash difference between the records and the broker's balance as an adjustment, after you
    looked at it. Kept as its own record, so it stays visible."""
    s['events'].append({'id': uuid.uuid4().hex[:10], 'ref': f'adj{day}{currency}{amount:.2f}', 'broker': broker,
                        'date': day, 'kind': 'adjust', 'cash': {currency: round(amount, 2)},
                        'eur': round(amount, 2) if currency == 'EUR' else None})
    s['checks'].append({'broker': broker, 'date': day, 'checked': date.today().isoformat(), 'ok': True,
                        'differences': 0, 'details': [], 'adjusted': f'{currency} {amount:+.2f}'})
    save(s)


def sold_report(s, mk):
    """Holdings you sold completely: how each did after your last sale, against your index fund over the same days
    (prices only, in euros). Like a "No": if it trails the index afterwards, selling was a good call."""
    pos, _ = positions(s)
    idx = index_symbol(s)
    today = date.today().isoformat()
    out = []
    for isin, p in pos.items():
        if abs(p['units']) > 1e-9 or not p['received_eur']:
            continue
        last = max(e['date'] for e in s['events'] if e.get('isin') == isin and e['kind'] in ('sell', 'position_out'))
        sec = s['securities'].get(isin, {})
        a0, a1 = price_eur(mk, sec.get('symbol'), last), price_eur(mk, sec.get('symbol'), today)
        b0, b1 = price_eur(mk, idx, last), price_eur(mk, idx, today)
        out.append({'isin': isin, 'name': sec.get('name', isin), 'sold': last, 'why': sec.get('sold_why', ''),
                    'result_eur': p['received_eur'] + p['dividends_eur'] - p['paid_eur'],
                    'stock_since': a1 / a0 - 1 if a0 and a1 else None,
                    'index_since': b1 / b0 - 1 if b0 and b1 else None})
    return sorted(out, key=lambda r: r['sold'], reverse=True)

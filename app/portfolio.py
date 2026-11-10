"""The scoreboard: a paper portfolio of the companies you pick, measured against your index fund.

Every euro you put into a pick is, on the same day and after the same broker fee, also put into your index fund in a
"shadow" portfolio. Selling a pick sells the same euros of the shadow. So both get exactly the same money at the same
times, and the difference between them is what your picking added or cost: total return in euros, after broker and
currency costs and after dividend tax kept abroad. Box 3 taxes both the same way, so it is left out.

Your index fund buys are recorded too (as "index"), so the program knows how big your whole portfolio is and can keep
the caps: at most `company_cap`% in one company and `picking_cap`% in all picks together.

The file is portfolio.json in your data folder. Prices, dividends and exchange rates come from Yahoo Finance.
"""
import json
import os
import uuid
from datetime import date, datetime, timedelta

import core

PATH = os.path.join(core.DATA, 'portfolio.json')
INDEX_CHOICES = {
    'VWCE.DE': 'Vanguard FTSE All-World (accumulating), Xetra',
    'VWRL.AS': 'Vanguard FTSE All-World (distributing), Euronext Amsterdam',
    'IWDA.AS': 'iShares Core MSCI World (accumulating), Euronext Amsterdam',
}
DEFAULT_RULES = {'index_symbol': 'VWCE.DE', 'index_name': INDEX_CHOICES['VWCE.DE'], 'index_currency': 'EUR',
                 'picking_cap': 20, 'company_cap': 10, 'stop_years': 3, 'stop_behind': 5,
                 'broker_fee': 3.0, 'fx_cost': 0.25, 'withholding': 15}
BACKDATE_DAYS = 7  # a trade can be recorded up to a week late, never further back: no picking with hindsight
UNDO_HOURS = 24  # a trade recorded by mistake can be removed the same day; after that it stays


# ---------- the file ----------

def load():
    try:
        return json.load(open(PATH, encoding='utf-8'))
    except (OSError, ValueError):
        return {'rules': None, 'trades': [], 'rule_changes': []}


def save(state):
    core.localdata.write_json(PATH, state, indent=1)


def set_rules(state, rules, why=''):
    """Write the rules; a change to rules already written is kept in rule_changes and noted in the journal."""
    old = state.get('rules')
    today = date.today().isoformat()
    if old:
        changed = {k: [old.get(k), v] for k, v in rules.items() if old.get(k) != v and k != 'written'}
        if not changed:
            return state
        state['rule_changes'].append({'date': today, 'changed': changed, 'why': why})
        core.add_journal_entry({'date': today, 'ticker': 'RULES', 'company': 'My rules', 'price': None,
                                'currency': 'EUR', 'decision': 'Rule change',
                                'why': 'Changed my scoreboard rules: ' + '; '.join(
                                    f'{LABELS.get(k, k)} from {a} to {b}' for k, (a, b) in changed.items())
                                       + (f'. Why: {why}' if why else ''),
                                'change_mind': '', 'next_check': '', 'author': 'You'})
    state['rules'] = {**rules, 'written': old.get('written', today) if old else today}
    save(state)
    return state


LABELS = {'index_symbol': 'index fund', 'picking_cap': 'cap on all picks (%)', 'company_cap': 'cap per company (%)',
          'stop_years': 'stop rule: years', 'stop_behind': 'stop rule: points behind', 'broker_fee': 'broker fee (€)',
          'fx_cost': 'currency cost (%)', 'withholding': 'dividend tax kept abroad (%)', 'index_name': 'index fund name',
          'index_currency': 'index fund currency'}


# ---------- prices from Yahoo ----------

def market(symbol, start):
    """{'close': {iso date: price}, 'div': {iso date: amount per share}, 'currency'} from `start` (iso) to today.
    Prices in pence (London) are turned into pounds."""
    import yfinance as yf
    t = yf.Ticker(symbol)
    h = t.history(start=start, auto_adjust=False, actions=True)
    if h.empty:
        raise RuntimeError(f'Yahoo Finance has no prices for {symbol}')
    h = h.dropna(subset=['Close'])
    try:
        cur = t.fast_info['currency']
    except Exception:
        cur = None
    k = 0.01 if cur in ('GBp', 'GBX') else 1.0
    cur = 'GBP' if cur in ('GBp', 'GBX') else cur
    close = {str(d.date()): float(v) * k for d, v in h['Close'].items()}
    div = {str(d.date()): float(v) * k for d, v in h.get('Dividends', {}).items() if v}
    return {'close': close, 'div': div, 'currency': cur}


def fx_series(currency, start):
    """{iso date: euros for one unit of `currency`}."""
    if currency in (None, 'EUR'):
        return None
    return market(f'{currency}EUR=X', start)['close']


def on(series, day):
    """The value on `day` or the last one before it (markets are closed at weekends); else the first one after."""
    if series is None:
        return 1.0
    keys = sorted(series)
    before = [k for k in keys if k <= day]
    if before:
        return series[before[-1]]
    return series[keys[0]]


# ---------- recording trades ----------

def check_date(day):
    today = date.today()
    if day > today:
        return 'A trade can\'t be dated in the future.'
    if day < today - timedelta(days=BACKDATE_DAYS):
        return (f'A trade can be recorded up to {BACKDATE_DAYS} days late, not more: with an older date you would '
                'already know how it went, and the scoreboard would no longer be fair.')
    return None


def costs(rules, amount, currency):
    fee = float(rules['broker_fee'])
    fx = amount * float(rules['fx_cost']) / 100 if currency != 'EUR' else 0.0
    return round(fee + fx, 2)


def quote(symbol, day):
    """(price, currency, euros per unit) on a day."""
    m = market(symbol, (day - timedelta(days=10)).isoformat())
    d = day.isoformat()
    fx = fx_series(m['currency'], (day - timedelta(days=10)).isoformat())
    return on(m['close'], d), m['currency'], on(fx, d)


def new_trade(state, kind, day, amount=None, units=None, ticker=None, company=None, symbol=None, price=None, why='',
              snapshot=None):
    """A buy (`amount` euros, costs included) or a sell (`units`). Returns the trade; raises ValueError with a reason
    when it breaks a rule (the caps, the date, selling more than you have)."""
    rules = state['rules']
    err = check_date(day)
    if err:
        raise ValueError(err)
    if kind == 'index':
        symbol, ticker, company = rules['index_symbol'], 'INDEX', rules['index_name']
    p, cur, eur = quote(symbol, day)
    if price:  # the price you actually paid, in the share's own currency
        p = float(price)
    t = {'id': uuid.uuid4().hex[:10], 'recorded': datetime.now().isoformat(timespec='seconds'), 'date': day.isoformat(),
         'kind': kind, 'ticker': ticker, 'company': company, 'symbol': symbol, 'currency': cur, 'price': p,
         'eur_per_unit': eur, 'why': why}
    if kind in ('index', 'buy'):
        amount = float(amount)
        c = costs(rules, amount, cur)
        if amount <= c:
            raise ValueError(f'The amount must be more than the costs ({c:.2f} euros).')
        t.update(amount_eur=amount, costs_eur=c, units=(amount - c) / (p * eur))
        if kind == 'buy':
            check_caps(state, t)
    else:
        held = units_held(state, ticker, day.isoformat())
        units = float(units)
        if units <= 0 or units > held + 1e-9:
            raise ValueError(f'You hold {held:.4f} shares of {company}; you can sell up to that.')
        gross = units * p * eur
        c = costs(rules, gross, cur)
        t.update(units=units, amount_eur=round(gross - c, 2), costs_eur=c)
    state['trades'].append(t)
    save(state)
    if kind != 'index':
        core.add_journal_entry({'date': t['date'], 'ticker': ticker, 'company': company, 'price': p, 'currency': cur,
                                'decision': 'Bought' if kind == 'buy' else 'Sold',
                                'why': f"{'Bought' if kind == 'buy' else 'Sold'} on the scoreboard: "
                                       f"{t['amount_eur']:,.2f} euros ({t['units']:.4f} shares at {p:,.2f} {cur}). {why}",
                                'change_mind': '', 'next_check': '', 'author': 'You', **(snapshot or {})})
    return t


def removable(t):
    return datetime.now() - datetime.fromisoformat(t['recorded']) < timedelta(hours=UNDO_HOURS)


def remove(state, trade_id):
    t = next(t for t in state['trades'] if t['id'] == trade_id)
    if not removable(t):
        raise ValueError(f'Only a trade recorded in the last {UNDO_HOURS} hours can be removed.')
    state['trades'] = [x for x in state['trades'] if x['id'] != trade_id]
    save(state)
    if t['kind'] != 'index':
        core.add_journal_entry({'date': date.today().isoformat(), 'ticker': t['ticker'], 'company': t['company'],
                                'price': t['price'], 'currency': t['currency'], 'decision': 'Correction',
                                'why': f"Removed the {t['kind']} of {t['date']} from the scoreboard (recorded by mistake).",
                                'change_mind': '', 'next_check': '', 'author': 'You'})


def units_held(state, ticker, day):
    n = 0.0
    for t in state['trades']:
        if t['ticker'] == ticker and t['date'] <= day:
            n += t['units'] if t['kind'] in ('buy', 'index') else -t['units']
    return n


# ---------- the score ----------

def markets(state):
    """Prices, dividends and exchange rates for everything in the portfolio, from the first trade on."""
    trades = state['trades']
    if not trades:
        return {}
    start = (date.fromisoformat(min(t['date'] for t in trades)) - timedelta(days=10)).isoformat()
    symbols = {t['symbol'] for t in trades} | {state['rules']['index_symbol']}
    out = {'start': start, 'm': {}, 'fx': {}}
    for s in symbols:
        out['m'][s] = market(s, start)
        cur = out['m'][s]['currency']
        if cur not in out['fx']:
            out['fx'][cur] = fx_series(cur, start)
    return out


class Book:
    """Shares and cash of one portfolio as it grows trade by trade, with dividends paid into its cash."""

    def __init__(self, mk, withholding):
        self.mk, self.wh, self.units, self.cash = mk, withholding, {}, 0.0

    def eur(self, symbol, day):
        m = self.mk['m'][symbol]
        return on(m['close'], day) * on(self.mk['fx'][m['currency']], day)

    def dividends(self, frm, to):
        """Dividends with an ex-date after `frm` up to `to`, on the shares held."""
        for s, n in self.units.items():
            m = self.mk['m'][s]
            for d, a in m['div'].items():
                if frm < d <= to and n > 0:
                    self.cash += n * a * on(self.mk['fx'][m['currency']], d) * (1 - self.wh / 100)

    def value(self, day):
        return self.cash + sum(n * self.eur(s, day) for s, n in self.units.items() if n > 1e-12)


def replay(state, mk, until):
    """Walk through the trades up to `until` (iso). Returns (picks, shadow, index, money in, per-company money in)."""
    r = state['rules']
    picks, shadow, index = Book(mk, r['withholding']), Book(mk, 0), Book(mk, 0)
    sym = r['index_symbol']
    money_in, put_in = 0.0, {}
    last = '0000-00-00'
    for t in sorted(state['trades'], key=lambda t: (t['date'], t['recorded'])):
        if t['date'] > until:
            break
        for b in (picks, shadow, index):
            b.dividends(last, t['date'])
        last = t['date']
        s = t['symbol']
        if t['kind'] == 'index':
            index.units[s] = index.units.get(s, 0) + t['units']
            continue
        idx_eur = shadow.eur(sym, t['date'])
        fee = float(r['broker_fee'])
        if t['kind'] == 'buy':
            picks.units[s] = picks.units.get(s, 0) + t['units']
            # the same euros into the index fund, after the same broker fee (no currency cost: it is in euros)
            shadow.units[sym] = shadow.units.get(sym, 0) + max(t['amount_eur'] - fee, 0) / idx_eur
            money_in += t['amount_eur']
            put_in[t['ticker']] = put_in.get(t['ticker'], 0) + t['amount_eur']
        else:
            picks.units[s] -= t['units']
            picks.cash += t['amount_eur']
            # the shadow sells index fund shares for the same euros
            want = (t['amount_eur'] + fee) / idx_eur
            n = min(want, shadow.units.get(sym, 0))
            shadow.units[sym] = shadow.units.get(sym, 0) - n
            shadow.cash += n * idx_eur - (fee if n else 0)
    for b in (picks, shadow, index):
        b.dividends(last, until)
    return picks, shadow, index, money_in, put_in


def score(state, mk, today=None):
    """Everything the scoreboard page shows, as of `today` (iso, default today)."""
    today = today or date.today().isoformat()
    r = state['rules']
    picks, shadow, index, money_in, put_in = replay(state, mk, today)
    pv, sv, iv = picks.value(today), shadow.value(today), index.value(today)
    total = pv + iv
    buys = [t for t in state['trades'] if t['kind'] == 'buy']
    first = min((t['date'] for t in buys), default=None)
    holdings = []
    for s, n in picks.units.items():
        if n <= 1e-9:
            continue
        t = next(t for t in buys if t['symbol'] == s)
        v = n * picks.eur(s, today)
        holdings.append({'company': t['company'], 'ticker': t['ticker'], 'shares': n, 'put_in': put_in.get(t['ticker'], 0),
                         'value': v, 'share': v / total if total else 0})
    out = {'picks_value': pv, 'shadow_value': sv, 'index_value': iv, 'total': total, 'money_in': money_in,
           'picks_cash': picks.cash, 'holdings': holdings, 'first_pick': first,
           'picks_share': (pv - picks.cash) / total if total else 0}
    if money_in:
        out['picks_return'] = pv / money_in - 1
        out['shadow_return'] = sv / money_in - 1
        out['gap_points'] = (out['picks_return'] - out['shadow_return']) * 100
    if first:
        d = date.fromisoformat(first)
        y = d.year + int(r['stop_years'])
        out['stop_date'] = (d.replace(year=y) if (d.month, d.day) != (2, 29) else date(y, 3, 1)).isoformat()
        out['stop_triggered'] = today >= out['stop_date'] and out.get('gap_points', 0) < -float(r['stop_behind'])
    return out


def timeline(state, mk, points=60):
    """[(iso date, picks value, shadow value, money in)] from the first pick to today, for the chart."""
    buys = [t['date'] for t in state['trades'] if t['kind'] == 'buy']
    if not buys:
        return []
    d0, d1 = date.fromisoformat(min(buys)), date.today()
    step = max((d1 - d0).days // points, 1)
    days = [d0 + timedelta(days=i) for i in range(0, (d1 - d0).days + 1, step)]
    if days[-1] != d1:
        days.append(d1)
    out = []
    for d in days:
        p, s, _, m, _ = replay(state, mk, d.isoformat())
        out.append((d.isoformat(), p.value(d.isoformat()), s.value(d.isoformat()), m))
    return out


def check_caps(state, new):
    """Raise ValueError when buying `new` would put more than company_cap% of the whole portfolio in one company, or
    more than picking_cap% in all picks together. The whole portfolio = your index fund buys + your picks."""
    r = state['rules']
    if not any(t['kind'] == 'index' for t in state['trades']):
        raise ValueError('Record your index fund buys first (the Index fund tab): the caps are a share of your whole '
                         'portfolio, so the program needs to know how big it is.')
    trial = {**state, 'trades': state['trades'] + [new]}
    mk = markets(trial)
    s = score(trial, mk, new['date'])
    mine = sum(h['value'] for h in s['holdings'] if h['ticker'] == new['ticker'])
    if s['total'] and mine / s['total'] > r['company_cap'] / 100 + 1e-9:
        raise ValueError(f"After this buy, {new['company']} would be {mine / s['total']:.1%} of your portfolio; your "
                         f"cap is {r['company_cap']}% per company. Buy less, or none.")
    if s['picks_share'] > r['picking_cap'] / 100 + 1e-9:
        raise ValueError(f"After this buy, your picks together would be {s['picks_share']:.1%} of your portfolio; your "
                         f"cap is {r['picking_cap']}%. The rest goes to the index fund.")

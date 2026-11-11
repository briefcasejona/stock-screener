"""Reading your brokers' exports into the Portfolio page's records (holdings.py).

IBKR: an Activity Flex Query as CSV, with the sections Trades, Cash Transactions, Open Positions, Cash Report,
Transfers, Corporate Actions and Financial Instrument Information, "section code and line descriptor" on.
DeGiro: the CSV exports of Transactions, Account statement and Portfolio.

Only the figures are kept: dates, holdings, amounts, costs. The file itself, your name and your account number are
not stored. Reading the same file again adds nothing twice (each record keeps the broker's own transaction number).
"""
import csv
import io
from datetime import date

import holdings as H

# IBKR's exchange codes -> Yahoo Finance's endings for the same exchange
YAHOO_SUFFIX = {'IBIS': '.DE', 'IBIS2': '.DE', 'FWB': '.F', 'FWB2': '.F', 'GETTEX': '.DE', 'LSE': '.L', 'LSEETF': '.L',
                'AEB': '.AS', 'SBF': '.PA', 'BVME': '.MI', 'BVME.ETF': '.MI', 'EBS': '.SW', 'SWX': '.SW',
                'ENEXT.BE': '.BR', 'BM': '.MC', 'SFB': '.ST', 'KFB': '.CO', 'OSE': '.OL', 'HEX': '.HE', 'VSE': '.VI',
                'NASDAQ': '', 'NYSE': '', 'ARCA': '', 'AMEX': '', 'BATS': '', 'TSE': '.TO'}


def num(x):
    try:
        return float(x) if x not in (None, '') else 0.0
    except ValueError:
        return 0.0


def day(x):
    """'20260311' or '20260311;112822' or '2026-03-11' -> '2026-03-11'."""
    x = (x or '').split(';')[0].split(' ')[0].replace('-', '')
    return f'{x[:4]}-{x[4:6]}-{x[6:8]}' if len(x) >= 8 else ''


# ---------- IBKR ----------

def ibkr_sections(text):
    rows = list(csv.reader(io.StringIO(text)))
    heads, out = {}, {}
    for r in rows:
        if len(r) < 2:
            continue
        if r[0] == 'HEADER':
            heads[r[1]] = r
        elif r[0] == 'DATA' and r[1] in heads:
            out.setdefault(r[1], []).append(dict(zip(heads[r[1]], r)))
    if not heads:
        raise ValueError('This is not an IBKR Flex Query with "section code and line descriptor" switched on.')
    return out


def parse_ibkr(text):
    """(records, statement, securities) from an IBKR Activity Flex Query CSV."""
    sec = ibkr_sections(text)
    missing = [n for code, n in (('TRNT', 'Trades'), ('CTRN', 'Cash Transactions'), ('POST', 'Open Positions'),
                                  ('CRTT', 'Cash Report')) if code not in sec and code != 'CTRN']
    if missing:
        raise ValueError('The file is missing these sections: ' + ', '.join(missing) + '. Add them to the Flex Query.')
    # ISIN changes (corporate action "IC"): the old ISIN's records count under the new one
    alias = {}
    corp = sec.get('CORP', [])
    for a in corp:
        if a.get('Type') == 'IC' and a.get('LevelOfDetail') == 'DETAIL' and num(a['Quantity']) < 0:
            new = next((b for b in corp if b.get('ActionID') == a.get('ActionID') and b.get('LevelOfDetail') == 'DETAIL'
                        and num(b['Quantity']) > 0), None)
            if new:
                alias[a['ISIN']] = new['ISIN']
    isin = lambda x: alias.get(x, x)
    securities = {}

    def note(r):
        i = isin(r.get('ISIN', ''))
        if not i:
            return
        info = securities.setdefault(i, {})
        if r.get('ISIN') == i or not info:  # the current listing's details, not the old ISIN's
            ex = r.get('ListingExchange', '')
            sym = (r.get('Symbol') or '').split('.')[0]
            info.update(name=r.get('Description') or sym, ticker=sym, exchange=ex, currency=r.get('CurrencyPrimary'),
                        fund=r.get('SubCategory') == 'ETF',
                        symbol=(sym.replace(' ', '-') + YAHOO_SUFFIX[ex]) if ex in YAHOO_SUFFIX and sym else None)

    for r in sec.get('SECU', []):
        note(r)
    events = []
    for r in sec.get('TRNT', []):
        if r.get('LevelOfDetail') != 'EXECUTION':
            continue
        cur, ccur = r['CurrencyPrimary'], r.get('IBCommissionCurrency') or r['CurrencyPrimary']
        rate = num(r.get('FXRateToBase')) or 1.0
        to_eur = lambda c: 1.0 if c == 'EUR' else rate  # IBKR's own rate of that day (base currency euro)
        ref = r.get('TransactionID') or r.get('TradeID')
        if r['AssetClass'] == 'CASH':  # changing money: EUR.GBP, quantity in the first currency, proceeds in the second
            base, quote = (r['Symbol'].split('.') + [''])[:2]
            cash = {}
            for c, a in ((base, num(r['Quantity'])), (quote, num(r['Proceeds'])), (ccur, num(r['IBCommission']))):
                if a:
                    cash[c] = cash.get(c, 0.0) + a
            if base != 'EUR' and quote != 'EUR':
                continue  # not seen with a euro account; left out rather than guessed
            fxr = num(r['TradePrice'])
            eur = sum(a if c == 'EUR' else (a / fxr if c == quote else a * fxr) for c, a in cash.items()) if fxr else None
            events.append({'ref': f'fx{ref}', 'date': day(r['TradeDate']), 'kind': 'fx', 'cash': cash,
                           'costs_eur': -num(r['IBCommission']) * to_eur(ccur), 'eur': eur})
            continue
        if r['AssetClass'] != 'STK':
            continue
        note(r)
        q = num(r['Quantity'])
        cash = {cur: num(r['Proceeds']) + num(r['Taxes'])}
        cash[ccur] = cash.get(ccur, 0.0) + num(r['IBCommission'])
        costs = -num(r['IBCommission']) * to_eur(ccur) - num(r['Taxes']) * to_eur(cur)
        events.append({'ref': f't{ref}', 'date': day(r['TradeDate']), 'kind': 'buy' if q > 0 else 'sell',
                       'isin': isin(r['ISIN']), 'name': r['Description'], 'units': abs(q),
                       'price': num(r['TradePrice']), 'currency': cur, 'cash': cash, 'costs_eur': costs,
                       'eur': sum(a * to_eur(c) for c, a in cash.items())})
    kinds = {'Deposits/Withdrawals': None, 'Dividends': 'dividend', 'Payment In Lieu Of Dividends': 'dividend',
             'Withholding Tax': 'tax', 'Broker Interest Received': 'interest', 'Broker Interest Paid': 'interest',
             'Bond Interest Received': 'interest', 'Other Fees': 'fee', 'Commission Adjustments': 'fee'}
    for r in sec.get('CTRN', []):
        if r.get('LevelOfDetail') != 'DETAIL':
            continue
        t, a, cur = r.get('Type', ''), num(r['Amount']), r['CurrencyPrimary']
        if t not in kinds:
            raise ValueError(f'A cash record of a kind the import doesn\'t know yet: "{t}". Nothing was read in.')
        k = kinds[t] or ('deposit' if a > 0 else 'withdrawal')
        e = {'ref': f"c{r.get('TransactionID') or r.get('ActionID')}{k}", 'date': day(r['Date/Time']), 'kind': k,
             'cash': {cur: a}, 'eur': a * (1.0 if cur == 'EUR' else num(r.get('FXRateToBase')) or 1.0)}
        if r.get('ISIN'):
            e.update(isin=isin(r['ISIN']), name=r.get('Description', ''))
            note(r)
        if k == 'fee':
            e['costs_eur'] = -e['eur']
        events.append(e)
    for r in corp:
        if r.get('LevelOfDetail') != 'DETAIL' or r.get('Type') == 'IC':
            continue
        e = {'ref': f"a{r.get('TransactionID')}", 'date': day(r['Date/Time']), 'kind': 'corp',
             'isin': isin(r['ISIN']), 'name': r.get('Description', ''), 'units': num(r['Quantity'])}
        if num(r.get('Proceeds')):
            e['cash'] = {r['CurrencyPrimary']: num(r['Proceeds'])}
        events.append(e)
        note(r)
    for r in sec.get('TRFR', []):
        if r.get('LevelOfDetail') not in ('TRANSFER', 'DETAIL', '') or not r.get('ISIN'):
            continue
        q = num(r['Quantity'])
        events.append({'ref': f"x{r.get('TransactionID')}", 'date': day(r.get('Date') or r.get('DateTime')),
                       'kind': 'position_in' if q > 0 else 'position_out', 'isin': isin(r['ISIN']),
                       'name': r.get('Description', ''), 'units': abs(q),
                       'cost_eur': num(r.get('CostBasis')) * (num(r.get('FXRateToBase')) or 1.0)})
        note(r)
    pos = [r for r in sec.get('POST', []) if r.get('LevelOfDetail') == 'SUMMARY']
    cash = [r for r in sec.get('CRTT', []) if r.get('LevelOfDetail') == 'Currency']
    when = day((pos or cash or [{}])[0].get('ReportDate') or (cash or [{}])[0].get('ToDate'))
    statement = {'date': when, 'units': {}, 'cash': {r['CurrencyPrimary']: num(r['EndingCash']) for r in cash},
                 'value': {}}
    for r in pos:
        i = isin(r['ISIN'])
        statement['units'][i] = statement['units'].get(i, 0.0) + num(r['Quantity'])
        statement['value'][i] = num(r['PositionValue']) * (num(r.get('FXRateToBase')) or 1.0)
        note(r)
    return events, statement, securities


# ---------- DeGiro (Dutch or English exports) ----------

def dnum(x):
    """DeGiro's numbers: '1.004,89' or '-3,90' or '1740,0000'."""
    x = (x or '').strip()
    if not x:
        return 0.0
    return float(x.replace('.', '').replace(',', '.')) if ',' in x else float(x)


def dday(x):
    """'23-10-2026' -> '2026-10-23'."""
    d, m, y = x.strip().split('-')
    return f'{y}-{m}-{d}'


def degiro_kind(text):
    """Which DeGiro export this is, from its first row."""
    head = next(csv.reader(io.StringIO(text)), [])
    h = [x.strip().lower() for x in head]
    if 'order id' in h and ('aantal' in h or 'quantity' in h) and ('koers' in h or 'price' in h):
        return 'transactions'
    if ('omschrijving' in h or 'description' in h) and ('mutatie' in h or 'change' in h):
        return 'account'
    if h[:2] in (['product', 'symbool/isin'], ['product', 'symbol/isin']):
        return 'portfolio'
    return None


def _refs():
    seen = {}

    def ref(*key):
        k = '|'.join(str(x) for x in key)
        seen[k] = seen.get(k, 0) + 1
        return f'{k}#{seen[k]}'
    return ref


def parse_degiro_transactions(text):
    """Buys and sells. DeGiro settles foreign trades in euros (AutoFX), so the euro total is the cash that moved; the
    AutoFX charge and the transaction fee are the costs."""
    rows = [r for r in csv.reader(io.StringIO(text))][1:]
    ref = _refs()
    events, securities = [], {}
    rows = [r for r in rows if len(r) >= 17 and r[0]]
    # a product change (the same shares moved to another listing): two rows without an order, cancelling out
    skip = set()
    for i, a in enumerate(rows):
        for j, b in enumerate(rows):
            if i < j and not a[16] and not b[16] and a[0] == b[0] and a[3] == b[3] \
                    and dnum(a[6]) == -dnum(b[6]) and abs(dnum(a[15]) + dnum(b[15])) < 0.01:
                skip |= {i, j}
    for i, r in enumerate(rows):
        if i in skip:
            continue
        q, total = dnum(r[6]), dnum(r[15])
        costs = -(dnum(r[13]) + dnum(r[14]))
        events.append({'ref': ref('t', r[16], r[0], r[1], r[3], r[5], r[6], r[9]), 'date': dday(r[0]),
                       'kind': 'buy' if q > 0 else 'sell', 'isin': r[3], 'name': r[2], 'units': abs(q),
                       'price': dnum(r[7]), 'currency': r[8], 'cash': {'EUR': total}, 'costs_eur': costs,
                       'eur': total})
        securities.setdefault(r[3], {'name': r[2], 'exchange': r[4], 'currency': r[8]})
    return events, securities


ACCOUNT = [  # (start of the description, what it is); everything else is ignored, see below
    ('ideal deposit', 'deposit'), ('storting', 'deposit'), ('deposit', 'deposit'),
    ('flatex terugstorting', 'withdrawal'), ('sepa instant terugstorting', 'withdrawal'), ('terugstorting', 'withdrawal'),
    ('withdrawal', 'withdrawal'),
    ('dividendbelasting', 'tax'), ('dividend tax', 'tax'), ('dividend', 'dividend'),
    ('degiro aansluitingskosten', 'fee'), ('degiro connection fee', 'fee'), ('degiro exchange connection', 'fee'),
    ('flatex interest', 'interest'), ('rente', 'interest'), ('interest', 'interest'),
]
# Left out on purpose: trades and their fees and currency lines (they have an order id; the Transactions file has
# them), iDEAL reservations (a temporary credit, reversed when the deposit arrives), cash sweeps between DeGiro and
# its flatex bank account (both are your cash at DeGiro), "Processed Flatex Withdrawal" (pairs that cancel out) and
# product changes (shares moved to another listing).
IGNORE = ('reservation ideal', 'degiro cash sweep', 'overboeking', 'processed flatex withdrawal', 'productwijziging',
          'product change', 'cash sweep transfer')


def parse_degiro_account(text):
    """Deposits, withdrawals, dividends and their tax, connection fees, interest, and money changed outside trades."""
    rows = [r for r in csv.reader(io.StringIO(text))][1:]
    ref = _refs()
    events, unknown, fx = [], [], {}
    for r in rows:
        if len(r) < 12 or not r[0]:
            continue
        desc, cur, amt, order = r[5].strip(), r[7].strip(), dnum(r[8]), r[11].strip()
        low = desc.lower()
        if order or not cur or any(low.startswith(x) for x in IGNORE):
            continue
        if low.startswith(('valuta creditering', 'valuta debitering', 'fx credit', 'fx debit')):
            fx.setdefault((r[0], r[1]), {})[cur] = fx.get((r[0], r[1]), {}).get(cur, 0.0) + amt
            continue
        kind = next((k for start, k in ACCOUNT if low.startswith(start)), None)
        if kind is None:
            unknown.append(desc)
            continue
        e = {'ref': ref('a', r[0], r[1], desc, cur, r[8]), 'date': dday(r[0]), 'kind': kind, 'cash': {cur: amt}}
        if cur == 'EUR':
            e['eur'] = amt
        if r[4]:
            e.update(isin=r[4], name=r[3])
        if kind == 'fee':
            e['costs_eur'] = -amt if cur == 'EUR' else None
        events.append(e)
    for (d, t), cash in fx.items():
        events.append({'ref': ref('fx', d, t, *sorted(cash.items())), 'date': dday(d), 'kind': 'fx', 'cash': cash,
                       'costs_eur': 0.0, 'eur': cash.get('EUR')})
    if unknown:
        raise ValueError('Lines of a kind the import doesn\'t know yet: ' + '; '.join(sorted(set(unknown))[:5])
                         + '. Nothing was read in.')
    return events


def parse_degiro_portfolio(text):
    """DeGiro's own figures of today, to check against: {'units': {isin: n}, 'cash': {EUR: amount}}."""
    rows = [r for r in csv.reader(io.StringIO(text))][1:]
    st = {'date': date.today().isoformat(), 'units': {}, 'cash': {}, 'value': {}}
    for r in rows:
        if len(r) < 7 or not r[0]:
            continue
        if not r[1]:  # the cash line
            st['cash'][r[4] or 'EUR'] = st['cash'].get(r[4] or 'EUR', 0.0) + dnum(r[5])
            continue
        st['units'][r[1]] = st['units'].get(r[1], 0.0) + dnum(r[2])
        st['value'][r[1]] = dnum(r[6])
    return st


# ---------- reading a file in ----------

def read_in(s, broker, text, source):
    """Parse, add new records, update what each holding is, and check against the statement in the same file.
    Returns (new records, differences)."""
    statement, securities, events = None, {}, []
    if broker == 'IBKR':
        events, statement, securities = parse_ibkr(text)
    else:
        kind = degiro_kind(text)
        if kind == 'transactions':
            events, securities = parse_degiro_transactions(text)
        elif kind == 'account':
            events = parse_degiro_account(text)
        elif kind == 'portfolio':
            statement = parse_degiro_portfolio(text)
        else:
            raise ValueError('Not a DeGiro Transactions, Account or Portfolio export (CSV).')
    new = H.add_events(s, events, broker, source) if events else 0
    for i, info in securities.items():
        cur = s['securities'].setdefault(i, {'name': info.get('name') or i, 'symbol': None, 'kind': None,
                                             'sector': None, 'country': None})
        cur['name'] = info.get('name') or cur['name']
        if not cur.get('symbol') and info.get('symbol'):
            cur['symbol'] = info['symbol']
        if info.get('fund') and not cur.get('kind'):
            cur['kind'] = 'index'
    for i, cur in s['securities'].items():  # no symbol from the broker (DeGiro): Yahoo's own match for the ISIN
        if not cur.get('symbol'):
            found = H.find_symbol(i)
            if found:
                cur['symbol'] = found[0][0]
    diffs = H.reconcile(s, broker, statement) if statement and statement.get('date') else None
    H.save(s)
    return new, diffs


def render(s):
    """The upload part of the Portfolio page."""
    import streamlit as st
    st.caption('IBKR: the Activity Flex Query (CSV), each year\'s file. DeGiro: Transactions, Account and Portfolio '
               '(CSV); read the Portfolio file last, it is the check. Reading a file twice adds nothing twice. '
               'Only the figures are kept, not the file, your name or your account number.')
    broker = st.segmented_control('Broker', H.BROKERS, default='IBKR', required=True, key='imp_broker')
    for kind, text in st.session_state.pop('import_notes', []):
        (st.success if kind == 'success' else st.error)(text)
    files = st.file_uploader('Export file(s)', type=['csv'], accept_multiple_files=True,
                             key=f"imp_files_{st.session_state.get('imp_gen', 0)}")
    if files and st.button('Read them in', type='primary'):
        texts = [(f.name, f.getvalue().decode('utf-8-sig', errors='replace')) for f in files]
        texts.sort(key=lambda x: degiro_kind(x[1]) == 'portfolio')  # the check comes after the records
        notes = []
        for name, text in texts:
            try:
                new, diffs = read_in(s, broker, text, name)
            except ValueError as e:
                notes.append(('error', f'{name}: {e}'))
                continue
            if diffs is None:
                notes.append(('success', f'{name}: {new} new records.'))
            elif not diffs:
                notes.append(('success', f'{name}: {new} new records. Matches {broker}\'s own figures to the cent and '
                                         'the share.'))
            else:
                notes.append(('error', f'{name}: {new} new records, but {len(diffs)} difference(s) with {broker}\'s '
                                       'own figures: see "Checked against your brokers" above.'))
        # start the page again, so everything above shows the new records and the check
        st.session_state['import_notes'] = notes
        st.session_state['imp_open'] = True  # keep this part open for the next file
        st.session_state['imp_gen'] = st.session_state.get('imp_gen', 0) + 1
        st.rerun()

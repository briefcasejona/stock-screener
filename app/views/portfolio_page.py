"""Portfolio: your real money at your brokers, read from their own records. Nothing is typed in here."""
from datetime import date, timedelta

import pandas as pd
import streamlit as st

import core
import holdings as H

EUR = lambda v: core.money(v, 'EUR')


@st.cache_data(ttl=900, show_spinner='Getting prices from Yahoo Finance...')
def markets(key, _s):
    return H.markets(_s)


def signed(v, nd=1):
    return f'{v:+.{nd}%}'.replace('-', '−')


def symbols_part(s):
    """Holdings whose Yahoo symbol is not known yet: pick it once."""
    todo = [(i, v) for i, v in s['securities'].items() if not v.get('symbol')]
    if not todo:
        return False
    st.warning(f"{len(todo)} holding{'s' if len(todo) > 1 else ''} still need{'s' if len(todo) == 1 else ''} a price "
               'source. Pick the right listing once (the exchange where you bought it, or any listing in the same '
               'currency).', icon=':material/link:')
    for isin, v in todo:
        found = H.find_symbol(isin)
        opts = [f'{sym} · {name} · {ex}' for sym, name, ex in found] + ['Type it myself']
        a, b, c = st.columns([3, 2, 1], vertical_alignment='bottom')
        pick = a.selectbox(f"{v['name']} ({isin})", opts, key=f'sym_{isin}')
        typed = b.text_input('Yahoo symbol', key=f'symt_{isin}', placeholder='e.g. VWCE.DE') \
            if pick == 'Type it myself' else pick.split(' · ')[0]
        if c.button('Use it', key=f'symok_{isin}', disabled=not typed):
            v['symbol'] = typed.strip().upper()
            try:
                v['kind'], v['sector'], v['country'] = H.describe(v['symbol'])
            except Exception:
                pass
            H.save(s)
            st.rerun()
    return True


def internal_part(s):
    pairs = H.internal_candidates(s)
    if not pairs:
        return
    st.info('These look like your own money moving between your brokers (out of one, into the other within a few '
            'days). Marked as such, they are not counted as new money in your return.', icon=':material/swap_horiz:')
    for w, d in pairs:
        a, b = st.columns([4, 1], vertical_alignment='center')
        a.write(f"{w['date']} out of {w['broker']}: {EUR(-H.eur_of(w))} → {d['date']} into {d['broker']}: "
                f"{EUR(H.eur_of(d))}")
        if b.button('Yes, a move', key=f"int_{w['id']}"):
            H.mark_internal(s, [w['id'], d['id']])
            st.rerun()


def headline(s, mk):
    mw = H.money_weighted(s, mk)
    pos, cash = H.positions(s)
    costs = sum(p['costs_eur'] for p in pos.values()) + sum(
        -H.eur_of(e) for e in s['events'] if e['kind'] in H.COST_KINDS)
    if not mw:
        st.info('No deposits found in your records yet.')
        return
    gain = mw['value'] - mw['put_in']
    a, b, c, d = st.columns(4)
    a.metric('Worth today', EUR(mw['value']))
    b.metric('Put in from your bank', EUR(mw['put_in']),
             help='Deposits minus withdrawals. Money moving between your brokers is not counted.')
    c.metric('Gain', EUR(gain), signed(gain / mw['put_in']) if mw['put_in'] > 0 else None)
    d.metric('All costs paid', EUR(costs), help='Broker fees and currency costs on trades, plus other broker fees.')
    if mw['yours'] is not None:
        x, y = st.columns(2)
        x.metric('Your real return, per year', signed(mw['yours']),
                 help='Money-weighted: each euro counts from the day you put it in, so your monthly deposits don\'t '
                      'make it look better or worse than it is. Over less than a year this figure jumps around.')
        if mw['index'] is not None:
            y.metric('Same money in your index fund, per year', signed(mw['index']),
                     f"{(mw['yours'] - mw['index']) * 100:+.1f} percentage points for you".replace('-', '−'),
                     help='Every euro you deposited, put into your index fund on the same day instead.')
    if mw['missing']:
        st.caption('Not yet counted (no price source picked): ' + ', '.join(
            s['securities'][i]['name'] for i in mw['missing']))


def split_part(s, mk, rows, cash_eur, total):
    idx = sum(r['Value'] for r in rows if r['_kind'] == 'index')
    stk = sum(r['Value'] for r in rows if r['_kind'] != 'index')
    a, b, c = st.columns(3)
    a.metric('Funds (ETFs)', f'{idx / total:.0%}' if total else 'n/a')
    b.metric('Single stocks', f'{stk / total:.0%}' if total else 'n/a')
    c.metric('Cash', f'{cash_eur / total:.0%}' if total else 'n/a')
    import portfolio as P
    rules = P.load().get('rules') or P.DEFAULT_RULES
    cap, ccap = float(rules['picking_cap']), float(rules['company_cap'])
    if total:
        share = stk / total * 100
        if share > cap:
            st.caption(f'Single stocks are {share:.0f}% of your portfolio; your target is at most {cap:.0f}%. New '
                       'money going into your funds brings this down month by month.')
        else:
            st.caption(f'Single stocks are {share:.0f}%, within your target of at most {cap:.0f}%.')
        over = [r['Holding'] for r in rows if r['_kind'] != 'index' and r['Value'] / total * 100 > ccap]
        if over:
            st.caption(f'Above your {ccap:.0f}% cap per company: ' + ', '.join(over) + '.')


def holdings_rows(s, mk):
    pos, _ = H.positions(s)
    today = date.today().isoformat()
    rows = []
    for isin, p in pos.items():
        if abs(p['units']) < 1e-9:
            continue
        sec = s['securities'].get(isin, {})
        px = H.price_eur(mk, sec.get('symbol'), today) if sec.get('symbol') else None
        if px is None:
            continue
        v = p['units'] * px
        gain = v + p['received_eur'] + p['dividends_eur'] - p['paid_eur']
        kind = sec.get('kind') or 'stock'
        rows.append({'Holding': sec.get('name', isin), 'Kind': 'Fund (ETF)' if kind == 'index' else 'Stock',
                     'At': ', '.join(b for b, u in p['by_broker'].items() if abs(u) > 1e-9),
                     'Value': v, 'Gain €': gain, 'Gain %': gain / p['paid_eur'] * 100 if p['paid_eur'] else None,
                     'Costs paid': p['costs_eur'], 'Dividends (net)': p['dividends_eur'],
                     'Held since': p['first'], 'Sector': 'Fund: many companies' if kind == 'index' else (sec.get('sector') or ''),
                     'Country': '' if kind == 'index' else (sec.get('country') or ''),
                     '_kind': kind, '_units': p['units'], '_paid': p['paid_eur'], '_isin': isin})
    return sorted(rows, key=lambda r: -r['Value'])


def review_part(s, mk):
    st.subheader('Month and year, for your journal')
    st.caption('Money-weighted: what your investments did, with the money you added left out. Short periods are '
               'mostly noise; they are here as a record, not as a reason to act.')
    r = H.month_and_year(s, mk)
    cols = st.columns(3)
    for col, k in zip(cols, ('month', 'ytd', 'last_year')):
        label, v = r[k]
        if v is None:
            col.metric(label, 'n/a', help='Your records don\'t cover this period.')
        else:
            col.metric(label, signed(v['return']), f"{EUR(v['gain'])}".replace('€-', '−€'), delta_color='normal',
                       help=f"Worth {EUR(v['start_value'])} at the start, {EUR(v['end_value'])} at the end, "
                            f"{EUR(v['added'])} added." + (f" From your first record on {v['from']}." if v.get('from')
                                                          else ''))


def render():
    st.title('Portfolio')
    st.caption('Your real money at your brokers, read from their own records and checked against their statements. '
               'Nothing is typed in here. Paper picks are on the Scoreboard. ' + core.DISCLAIMER)
    s = H.load()
    if not s['events']:
        st.info('No broker records yet. Read in your exports below.', icon=':material/account_balance:')
        import_part(s)
        return
    if symbols_part(s):
        st.divider()
    internal_part(s)
    unknown = [v for v in s['securities'].values() if v.get('symbol') and not v.get('kind')]
    if unknown:  # what each holding is (fund or stock, sector, country): asked once, then kept
        with st.spinner('Looking up what your holdings are...'):
            for v in unknown:
                try:
                    v['kind'], v['sector'], v['country'] = H.describe(v['symbol'])
                except Exception:
                    pass
        H.save(s)
    key = (len(s['events']), tuple(sorted((i, v.get('symbol')) for i, v in s['securities'].items())), date.today())
    try:
        mk = markets(key, s)
    except Exception as e:
        st.error(f'Could not get prices from Yahoo Finance ({e}). Try again in a while.')
        import_part(s)
        return
    headline(s, mk)
    rows = holdings_rows(s, mk)
    hv, cv, _ = H.total_value(s, mk)
    st.divider()
    split_part(s, mk, rows, cv, hv + cv)
    if rows:
        total = hv + cv
        table = [{**{k: v for k, v in r.items() if not k.startswith('_')},
                  'Weight': r['Value'] / total * 100 if total else None} for r in rows]
        if abs(cv) >= 0.005:  # cash counts in the weights, so it gets its own row
            _, cash_now = H.positions(s)
            table.append({'Holding': 'Cash', 'Kind': 'Cash',
                          'At': ', '.join(sorted({b for (b, c), a in cash_now.items() if abs(a) >= 0.005})),
                          'Value': cv, 'Weight': cv / total * 100 if total else None})
        show = pd.DataFrame(table)
        money = st.column_config.NumberColumn(format='€%,.2f')
        st.dataframe(show, hide_index=True, use_container_width=True, column_config={
            'Holding': st.column_config.TextColumn(pinned=True), 'Value': money, 'Gain €': money, 'Costs paid': money,
            'Dividends (net)': money, 'Gain %': st.column_config.NumberColumn(format='%+.1f%%'),
            'Weight': st.column_config.NumberColumn(format='%.1f%%')})
        st.caption('Gain = what it is worth + what you got back from selling and dividends − what you paid, costs '
                   'included. Sector and country: Yahoo Finance, for single stocks only (a fund owns thousands of '
                   'companies), and they can be wrong.')
        with st.expander('What you paid per share', icon=':material/history:'):
            st.caption('Shown only on request: the price you paid says nothing about what a share is worth today, '
                       'and it pulls your decisions toward "waiting to get back to it". Use it to check your broker '
                       'statements.')
            st.dataframe(pd.DataFrame([{'Holding': r['Holding'], 'Shares': r['_units'],
                                        'Paid per share, costs included': EUR(r['_paid'] / r['_units'])}
                                       for r in rows if r['_units'] > 0]), hide_index=True)
    _, cash = H.positions(s)
    if cash:
        st.caption('Cash: ' + '; '.join(f'{b} {core.money(a, c)}' for (b, c), a in sorted(cash.items())
                                        if abs(a) >= 0.005) or 'none')
    st.divider()
    review_part(s, mk)
    st.divider()
    b3 = H.box3_value(s, mk)
    st.subheader('For Box 3')
    st.write(f"On **{date.fromisoformat(b3['date']):%d %B %Y}** your investments were worth **{EUR(b3['holdings'])}** "
             f"and your cash at the brokers **{EUR(b3['cash'])}**: **{EUR(b3['total'])}** in total, both brokers "
             'together. Your tax return asks for the value on 1 January; your brokers\' own year statements are the '
             'official figures, this is to check them.')
    dividends_part(s, mk)
    sold_part(s, mk)
    st.divider()
    checks_part(s)
    import_part(s)


def dividends_part(s, mk):
    year_ago = (date.today() - timedelta(days=365)).isoformat()
    got = sum(H.eur_of(e) for e in s['events'] if e['kind'] in ('dividend', 'tax') and e['date'] > year_ago)
    out = H.dividend_outlook(s, mk)
    if not got and not out:
        return
    st.subheader('Dividends')
    st.write(f'Received in the last 12 months, after dividend tax: **{EUR(got)}**.')
    if out:
        st.dataframe(pd.DataFrame([{'Holding': o['name'], 'Pays in': ', '.join(o['months']),
                                    'Last 12 months per share': core.money(o['per_share_12m'], o['currency']),
                                    'On your shares now, per year': EUR(o['yearly_eur'])} for o in out]),
                     hide_index=True)
        st.caption('An estimate: last year\'s dividends on the shares you hold now, before dividend tax. Companies '
                   'change their dividends; a fund that reinvests them (accumulating) pays none.')


def checks_part(s):
    st.subheader('Checked against your brokers')
    if not s['checks']:
        st.caption('Not checked yet. Read in a portfolio statement from each broker (below) to compare.')
        return
    last = {}
    for c in s['checks']:
        last[c['broker']] = c
    for b, c in last.items():
        if c['ok']:
            st.success(f"{b}: matches the broker's statement of {c['date']} to the cent.", icon=':material/verified:')
            if c.get('adjusted'):
                st.caption(f"After you accepted a difference of {c['adjusted']} in {b}'s own figures.")
        else:
            st.error(f"{b}: {c['differences']} difference(s) with the statement of {c['date']}. The figures above "
                     'are not reliable until this is fixed.', icon=':material/error:')
            details = c.get('details') or []
            st.dataframe(details, hide_index=True)
            small = [d for d in details if d['what'].startswith('cash ') and abs(d['broker'] - d['records']) < 1]
            if small and len(small) == len(details):
                st.caption('Only a few cents of cash differ. That happens when the broker\'s own export doesn\'t add '
                           'up to its own balance (rounding, or interest it books later). You can accept it: it is '
                           'kept as a separate "adjustment" record, so it stays visible.')
                if st.button(f'Accept the difference for {b}', key=f'adj_{b}'):
                    for d in small:
                        H.accept_difference(s, b, d['what'][5:], d['broker'] - d['records'], c['date'])
                    st.rerun()


def import_part(s):
    with st.expander('Read in your broker exports', icon=':material/upload_file:', expanded=not s['events'] or st.session_state.get('imp_open', False)):
        try:
            import broker_import
        except ImportError:
            broker_import = None
        if broker_import is None:
            st.caption('Reading your IBKR and DeGiro exports is being added in the next update.')
            return
        broker_import.render(s)


def sold_part(s, mk):
    rows = H.sold_report(s, mk)
    if not rows:
        return
    st.subheader('What you sold')
    st.caption('Selling is a decision too. Since your last sale, prices only, in euros: if a company you sold then '
               'trails your index fund, selling was a good call.')
    pct = lambda v: signed(v) if v is not None else 'n/a'
    st.dataframe(pd.DataFrame([{'Holding': r['name'], 'Sold on': r['sold'], 'Your result': EUR(r['result_eur']),
                                'It did since': pct(r['stock_since']), 'Index fund since': pct(r['index_since']),
                                'So far': '' if r['stock_since'] is None or r['index_since'] is None else
                                ('good call' if r['stock_since'] <= r['index_since'] else 'it did better'),
                                'Why you sold': r['why']} for r in rows]), hide_index=True)
    todo = [r for r in rows if not r['why']]
    if todo:
        with st.form('sold_why'):
            pick = st.selectbox('Write down why you sold', [r['name'] for r in todo])
            why = st.text_input('Why', placeholder='e.g. bought without research; freeing money for the index fund')
            if st.form_submit_button('Save') and why.strip():
                r = next(r for r in todo if r['name'] == pick)
                s['securities'][r['isin']]['sold_why'] = why.strip()
                H.save(s)
                core.add_journal_entry({'date': date.today().isoformat(), 'ticker': r['isin'], 'company': r['name'],
                                        'price': None, 'currency': 'EUR', 'decision': 'Sold (real)',
                                        'why': f"Sold on {r['sold']}: {why.strip()}", 'change_mind': '',
                                        'next_check': '', 'author': 'You'})
                st.rerun()

"""Scoreboard: your picks against your index fund, with your stop rule and your caps (portfolio.py does the sums)."""
from datetime import date, timedelta

import altair as alt
import pandas as pd
import streamlit as st

import core
import portfolio as P
from views import data


@st.cache_data(ttl=15 * 60, show_spinner='Getting prices and dividends from Yahoo Finance...')
def markets(key, _state):
    """Cached for a few hours; `key` changes when the trades or the index fund change."""
    return P.markets(_state)


def symbol_of(ticker):
    from refresh_company import find
    return find(ticker)[1]['yahoo']


def eur(v):
    return f'€{v:,.0f}' if abs(v) >= 100 else f'€{v:,.2f}'


def rules_form(state, first):
    r = state.get('rules') or P.DEFAULT_RULES
    with st.form('rules'):
        if first:
            st.markdown('**Write your rules down before your first pick.** They are yours to choose; the numbers filled '
                        'in are only a start (the 20% cap is the council\'s suggestion). Later changes are kept and noted '
                        'in the journal, so you can always see what you decided first.')
        choices = list(P.INDEX_CHOICES) + ['Other']
        pick = st.selectbox('Your index fund (the one you actually buy)', choices,
                            index=choices.index(r['index_symbol']) if r['index_symbol'] in choices else len(choices) - 1,
                            format_func=lambda s: f'{s}: {P.INDEX_CHOICES[s]}' if s in P.INDEX_CHOICES else 'Another fund')
        other = st.text_input('Another fund: its Yahoo Finance symbol (for example VUSA.AS)',
                              value='' if r['index_symbol'] in P.INDEX_CHOICES else r['index_symbol'])
        st.markdown('**Caps**')
        a, b = st.columns(2)
        cap = a.number_input('All picks together, at most (% of your whole portfolio)', 1, 100, int(r['picking_cap']))
        one = b.number_input('One company, at most (% of your whole portfolio)', 1, 100, int(r['company_cap']))
        st.markdown('**Stop rule**: when do you go back to 100% index fund?')
        a, b = st.columns(2)
        years = a.number_input('Judge my picks after this many years', 1, 10, int(r['stop_years']))
        behind = b.number_input('...and stop if they are behind the index fund by more than (percentage points)', 0, 100,
                                int(r['stop_behind']))
        st.markdown('**Costs** (your broker\'s; they are taken off every trade)')
        a, b, c = st.columns(3)
        fee = a.number_input('Fee per trade (€)', 0.0, 50.0, float(r['broker_fee']), 0.5)
        fx = b.number_input('Currency exchange cost (% of a non-euro trade)', 0.0, 2.0, float(r['fx_cost']), 0.05)
        wh = c.number_input('Dividend tax kept abroad (%)', 0.0, 50.0, float(r['withholding']), 1.0,
                            help='The US keeps 15% of dividends for Dutch residents; the Netherlands also keeps 15%. '
                                 'You can usually set it off against your Dutch tax, but it is money that leaves the '
                                 'portfolio, so it counts here. Your index fund\'s own taxes are in its price.')
        why = '' if first else st.text_input('Why are you changing them? (goes in the journal)')
        if st.form_submit_button('Save my rules', type='primary'):
            symbol = (other.strip().upper() if pick == 'Other' else pick)
            if not symbol:
                st.error('Fill in the symbol of your index fund.')
                return
            if one > cap:
                st.error('The cap for one company can\'t be bigger than the cap for all picks together.')
                return
            if not first and not why.strip():
                st.error('Write a line on why you change your rules.')
                return
            try:
                cur = P.market(symbol, (date.today() - timedelta(days=10)).isoformat())['currency']
            except Exception as e:
                st.error(f'Could not find {symbol} on Yahoo Finance: {e}')
                return
            name = P.INDEX_CHOICES.get(symbol, symbol)
            P.set_rules(state, {'index_symbol': symbol, 'index_name': name, 'index_currency': cur or 'EUR',
                                'picking_cap': cap, 'company_cap': one, 'stop_years': years, 'stop_behind': behind,
                                'broker_fee': fee, 'fx_cost': fx, 'withholding': wh}, why.strip())
            data.changed()
            st.rerun()


def headline(state, s, paper):
    r = state['rules']
    if not s.get('money_in'):
        st.info('No paper picks yet. While you have none, the scoreboard has nothing to compare: all your money is in '
                'the index fund, which is the default anyway.' if paper else 'No real picks yet.')
        return
    a, b, c = st.columns(3)
    a.metric('Your paper picks' if paper else 'Your real picks', eur(s['picks_value']), f"{s['picks_return']:+.1%} on {eur(s['money_in'])} put in")
    b.metric(f"Index fund, same money and days", eur(s['shadow_value']),
             f"{s['shadow_return']:+.1%} on {eur(s['money_in'])} put in")
    diff = s['picks_value'] - s['shadow_value']
    c.metric('What picking added' if diff >= 0 else 'What picking cost', eur(abs(diff)),
             f"{s['gap_points']:+.1f} percentage points", delta_color='normal')
    st.caption('Total return in euros: price changes plus dividends (after dividend tax kept abroad), minus broker and '
               'currency costs. Every euro you put into a pick also went into your index fund on the same day in the '
               '"same money" column, so the two can be compared fairly. Box 3 taxes both the same way, so it is left '
               'out. A year or two says little: about 50 decisions over 4 years still can\'t tell skill from luck.')
    if s.get('stop_triggered'):
        st.error(f"**Your stop rule has fired.** After {r['stop_years']} years your picks are {abs(s['gap_points']):.1f} "
                 f"points behind the index fund (your limit: {r['stop_behind']}). You decided in advance that this "
                 'means going back to 100% index fund.', icon=':material/flag:')
    else:
        where = ('ahead of' if s['gap_points'] >= 0 else 'behind')
        st.markdown(f":material/flag: **Stop rule** (written {date.fromisoformat(r['written']):%d %b %Y}): on **{date.fromisoformat(s['stop_date']):%d %b %Y}** "
                    f"({r['stop_years']} years after your first pick), if your picks are more than {r['stop_behind']} "
                    f"points behind the index fund, you go back to 100% index fund. Today they are "
                    f"{abs(s['gap_points']):.1f} points {where} it.")


def chart(state, mk, paper):
    pts = P.timeline(state, mk, paper=paper)
    if len(pts) < 2:
        return
    rows = [{'Date': d, 'Value': v, 'Line': 'Your picks'} for d, v, _, _ in pts]
    rows += [{'Date': d, 'Value': v, 'Line': 'Index fund, same money'} for d, _, v, _ in pts]
    rows += [{'Date': d, 'Value': m, 'Line': 'Money put in'} for d, _, _, m in pts]
    pal = {'dark': ['#0a84ff', '#30d158', '#8e8e93'], 'light': ['#0071e3', '#248a3d', '#8e8e93']}
    colors = pal['dark' if st.context.theme.type == 'dark' else 'light']
    st.altair_chart(alt.Chart(pd.DataFrame(rows)).mark_line(strokeWidth=2.5).encode(
        x=alt.X('Date:T', title=None), y=alt.Y('Value:Q', title=None, axis=alt.Axis(format=',.0f')),
        color=alt.Color('Line:N', scale=alt.Scale(domain=['Your picks', 'Index fund, same money', 'Money put in'],
                                                  range=colors), legend=alt.Legend(orient='top', title=None)),
        strokeDash=alt.condition(alt.datum.Line == 'Money put in', alt.value([4, 4]), alt.value([1, 0])),
        tooltip=['Date:T', 'Line:N', alt.Tooltip('Value:Q', format=',.0f')]).properties(height=280),
        use_container_width=True)


def caps(state, s, paper):
    r = state['rules']
    st.markdown('**Caps**')
    st.write(f"All {'paper' if paper else 'real'} picks together: **{s['picks_share']:.1%}** of your portfolio ({eur(s['total'])}), cap "
             f"{r['picking_cap']}%.")
    st.progress(min(s['picks_share'] / (r['picking_cap'] / 100), 1.0))
    if s['holdings']:
        st.dataframe(pd.DataFrame([{
            'Company': h['company'], 'Shares': round(h['shares'], 4), 'Put in': eur(h['put_in']), 'Worth now': eur(h['value']),
            'Share of portfolio': h['share'] * 100} for h in s['holdings']]), hide_index=True, use_container_width=True,
            column_config={'Company': st.column_config.TextColumn('Company', pinned=True),
                           'Share of portfolio': st.column_config.ProgressColumn(
                               'Share of portfolio', format='%.1f%%', min_value=0, max_value=float(r['company_cap']),
                               help=f"Your cap is {r['company_cap']}% per company.")})


def record(state):
    st.subheader('Record a trade')
    st.caption(f'Record a trade on the day you make it, or up to {P.BACKDATE_DAYS} days later; an older date would let '
               'hindsight in. A trade dated today gets the latest price on Yahoo Finance (free, usually about 15 minutes '
               'behind the exchange); an earlier date gets that day\'s closing price. Paper trades always use that '
               'price, so practice can\'t pick a flattering one; for a real trade you can fill in what you paid.')
    t1, t2, t3 = st.tabs(['Index fund', 'Buy a candidate', 'Sell'])
    today = date.today()
    lo = today - timedelta(days=P.BACKDATE_DAYS)
    with t1, st.form('index_buy', clear_on_submit=True):
        st.write(f"Your monthly buy of {state['rules']['index_symbol']}: the default for every month's money.")
        a, b = st.columns(2)
        amount = a.number_input('Amount, costs included (€)', 1.0, 1e7, 1000.0, 50.0)
        day = b.date_input('Date', today, min_value=lo, max_value=today, format='DD-MM-YYYY')
        if st.form_submit_button('Record the index fund buy', type='primary'):
            do(lambda: P.new_trade(state, 'index', day, amount=amount), 'Recorded.')
    cands = data.dashboard()['candidates']
    with t2:
        if not cands:
            st.info('Only companies you analysed can be bought here: analyse one on the Screener page first.')
        else:
            with st.form('pick_buy', clear_on_submit=True):
                names = {c['ticker']: c['company'] for c in cands}
                cand = {c['ticker']: c for c in cands}
                tk = st.selectbox('Company (from your candidates)', list(names), format_func=names.get)
                a, b, c = st.columns(3)
                amount = a.number_input('Amount, costs included (€)', 1.0, 1e7, 500.0, 50.0)
                day = b.date_input('Date', today, min_value=lo, max_value=today, format='DD-MM-YYYY', key='bd')
                price = c.number_input('Price you paid per share (real trades only, optional)', 0.0, 1e7, 0.0)
                why = st.text_input('Why this company, at this price? (one line, goes in the journal)')
                unlocked = bool(state['rules'].get('real_unlocked'))
                kind = st.segmented_control('Money', ['Paper', 'Real'] if unlocked else ['Paper'], default='Paper',
                                            required=True, key='buy_kind')
                if not unlocked:
                    st.caption(P.REAL_LOCKED)
                if st.form_submit_button('Record the buy', type='primary'):
                    if not why.strip():
                        st.error('Write one line on why. It is the line you will check yourself against later.')
                    else:
                        do(lambda: P.new_trade(state, 'buy', day, amount=amount, ticker=tk, company=names[tk],
                                               symbol=symbol_of(tk), price=price or None, why=why.strip(),
                                               snapshot={k: cand[tk].get(k) for k in
                                                         ('implied_growth', 'bear', 'base', 'bull')},
                                               paper=kind == 'Paper'),
                           'Recorded, and noted in the journal.')
    held = {}  # (ticker, paper): a trade of it
    for t in state['trades']:
        if t['kind'] != 'index':
            held.setdefault((t['ticker'], P.is_paper(t)), t)
    held = {k: t for k, t in held.items() if P.units_held(state, k[0], today.isoformat(), k[1]) > 1e-9}
    with t3:
        if not held:
            st.info('Nothing to sell.')
        else:
            with st.form('pick_sell', clear_on_submit=True):
                key = st.selectbox('Company', list(held), format_func=lambda k: held[k]['company']
                                   + (' (paper)' if k[1] else ' (real)'))
                tk, on_paper = key
                a, b, c = st.columns(3)
                units = a.number_input('Shares to sell', 0.0, 1e9, 0.0, help='Fractions are fine.')
                day = b.date_input('Date', today, min_value=lo, max_value=today, format='DD-MM-YYYY', key='sd')
                price = c.number_input('Price you got per share (real trades only, optional)', 0.0, 1e7, 0.0)
                why = st.text_input('Why sell? (one line, goes in the journal)')
                if st.form_submit_button('Record the sale', type='primary'):
                    if not why.strip():
                        st.error('Write one line on why.')
                    else:
                        t = held[key]
                        do(lambda: P.new_trade(state, 'sell', day, units=units, ticker=tk, company=t['company'],
                                               symbol=t['symbol'], price=price or None, why=why.strip(),
                                               paper=on_paper),
                           'Recorded, and noted in the journal.')


def do(fn, ok):
    try:
        with st.spinner('Getting the price...'):
            fn()
    except ValueError as e:
        st.error(str(e))
        return
    except Exception as e:
        st.error(f'Could not record it: {e}')
        return
    data.changed()
    st.toast(ok)
    st.rerun()


def trades(state):
    if not state['trades']:
        return
    st.subheader('Every trade')
    rows = [{'Date': t['date'], 'What': {'index': 'Index fund buy', 'buy': 'Buy', 'sell': 'Sell'}[t['kind']]
             + (' (paper)' if P.is_paper(t) else ''),
             'Company': t['company'], 'Euros': t['amount_eur'], 'Costs': t['costs_eur'],
             'Price': f"{t['price']:,.2f} {t['currency']}" + (f" ({t['price_time'][-5:]})" if t.get('price_time') else ''), 'Shares': round(t['units'], 4)}
            for t in sorted(state['trades'], key=lambda t: (t['date'], t['recorded']), reverse=True)]
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True,
                 column_config={'Euros': st.column_config.NumberColumn(format='€%.2f'),
                                'Costs': st.column_config.NumberColumn(format='€%.2f')})
    recent = [t for t in state['trades'] if P.removable(t)]
    if recent:
        with st.expander('Recorded something by mistake?'):
            st.caption(f'A trade can be removed within {P.UNDO_HOURS} hours of recording it. After that it stays, like '
                       'the journal: the scoreboard is only honest if the bad trades stay on it too.')
            pick = st.selectbox('Trade', [t['id'] for t in recent], format_func=lambda i: next(
                f"{t['date']} {t['kind']} {t['company']} {eur(t['amount_eur'])}" for t in recent if t['id'] == i))
            if st.button('Remove this trade'):
                P.remove(state, pick)
                data.changed()
                st.rerun()


@st.cache_data(ttl=15 * 60, show_spinner=False)
def _passes(key, _state):
    return P.passes_report(_state)


def passes(state):
    if not state.get('passes'):
        return
    st.subheader('Companies you said No to')
    st.caption('Saying no is a decision too. If a company you passed on then trails your index fund, staying away was '
               'a good call. Prices only, in euros, since the day of your "No".')
    rows = _passes((tuple((p['ticker'], p['date']) for p in state['passes']), date.today()), state)
    st.dataframe(pd.DataFrame([{'Company': r['company'], 'Said no on': r['date'], 'The company since': r['stock'] * 100,
                                'Your index fund since': r['index'] * 100,
                                'Verdict so far': 'good call' if r['stock'] <= r['index'] else 'it did better'}
                               for r in rows]), hide_index=True, use_container_width=True,
                 column_config={'The company since': st.column_config.NumberColumn(format='%+.1f%%'),
                                'Your index fund since': st.column_config.NumberColumn(format='%+.1f%%')})


def render():
    st.title('Scoreboard')
    st.caption('Do your picks beat simply buying your index fund? Record your index fund buys and the companies you '
               'pick. While you learn, picks are on paper: as if part of your monthly money had gone into the company '
               f'instead of the index fund, without risking it. The program keeps score. {core.DISCLAIMER}')
    state = P.load()
    if not state.get('rules'):
        rules_form(state, first=True)
        return
    mk = {}
    if state['trades']:
        key = (state['rules']['index_symbol'], tuple((t['id'], t['date']) for t in state['trades']), date.today(),
               st.session_state.get('price_refresh', 0))
        try:
            mk = markets(key, state)
        except Exception as e:
            st.error(f'Could not get prices from Yahoo Finance ({e}). The score shows again when it answers.')
        a, b = st.columns([4, 1], vertical_alignment='center')
        a.caption('Prices: Yahoo Finance, free and usually about 15 minutes behind the exchange; on a trading day the '
                  'score uses the latest price, and it fetches again every 15 minutes or when you press Refresh.')
        if b.button('Refresh prices', icon=':material/refresh:'):
            st.session_state['price_refresh'] = st.session_state.get('price_refresh', 0) + 1
            st.rerun()
    if mk:
        has_real = any(t['kind'] != 'index' and not P.is_paper(t) for t in state['trades'])
        for paper in ([True, False] if has_real else [True]):
            if has_real:
                st.subheader('Paper picks' if paper else 'Real picks')
            s = P.score(state, mk, paper=paper)
            headline(state, s, paper)
            chart(state, mk, paper)
            caps(state, s, paper)
    elif not state['trades']:
        st.info('Start by recording your index fund buys (below), so the caps know how big your portfolio is.')
    record(state)
    trades(state)
    passes(state)
    st.divider()
    with st.expander('Your rules', icon=':material/rule:'):
        rules_form(state, first=False)
        for c in reversed(state['rule_changes']):
            st.caption(f"{c['date']}: " + '; '.join(f"{P.LABELS.get(k, k)} {a} → {b}" for k, (a, b) in c['changed'].items())
                       + (f" ({c['why']})" if c.get('why') else ''))

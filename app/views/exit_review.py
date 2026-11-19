"""The DeGiro exit review on the Journal page: your reason first, the price and your gain second."""
import streamlit as st

import core
import exit_review as X
import holdings as H


def gain_after(s, isin):
    """What the holding at DeGiro is worth today and what it gained, shown only once your decision is written."""
    from views.portfolio_page import markets
    from datetime import date
    key = (len(s['events']), tuple(sorted((i, v.get('symbol')) for i, v in s['securities'].items())), date.today())
    mk = markets(key, s)
    sym = (s['securities'].get(isin) or {}).get('symbol')
    px = H.price_eur(mk, sym, date.today().isoformat()) if sym else None
    pos, _ = H.positions(s, broker=X.BROKER)
    p = pos.get(isin)
    if px is None or not p:
        return 'no price from Yahoo Finance for it'
    v = p['units'] * px
    g = v + p['received_eur'] + p['dividends_eur'] - p['paid_eur']
    return (f"worth {core.money(v, 'EUR')} today; gain {'−' if g < 0 else '+'}{core.money(abs(g), 'EUR')}"
            + (f" ({g / p['paid_eur']:+.1%})".replace('-', '−') if p['paid_eur'] else '') + ', costs and dividends counted')


def render():
    s = H.load()
    held = X.holdings_at_degiro(s)
    if not held:
        return
    done = X.written()
    todo = [h for h in held if h[0] not in done]
    st.subheader('DeGiro exit review')
    st.caption(f"{len(held) - len(todo)} of {len(held)} DeGiro holdings decided. For each one: keep it (and move it to "
               'IBKR), trim it, or sell it, and why. Write your reason first; its price and your gain on it are shown '
               'only after, so they can\'t pull your decision.')
    st.info(X.NO_CGT, icon=':material/info:')
    if held:  # the ones not decided first; a decided one can get a new entry (the first stays)
        order = todo + [h for h in held if h[0] in done]
        names = {h[0]: f"{H_name(h[1])} ({h[2]:g} shares, since {h[3]})" + (' · decided' if h[0] in done else '')
                 for h in order}
        isin = st.selectbox('Holding', list(names), format_func=lambda i: names[i], key='exit_pick')
        company = H_name(next(h[1] for h in held if h[0] == isin))
        n = st.session_state.get('exit_n', 0)
        with st.form(f'exit_{n}', enter_to_submit=False):
            st.write('**Would you buy it today, at today\'s business (not today\'s price)?** What does the company do '
                     'for you, and does it fit your rules (at most 10% in one company, your index fund as the core)?')
            choice = st.segmented_control('Your decision', X.CHOICES, default=None, key=f'exit_c_{n}')
            pct = st.number_input('If you trim: how much of it to sell (%)', 1, 99, 50, key=f'exit_p_{n}')
            why = st.text_area('Why', height=100, key=f'exit_w_{n}')
            mind = st.text_input('What would change your mind', key=f'exit_m_{n}')
            if st.form_submit_button('Write it in the journal', type='primary'):
                try:
                    X.write(isin, company, choice, why, mind, pct if choice == 'Trim' else None)
                    st.session_state['exit_n'] = n + 1
                    st.session_state['exit_shown'] = isin
                    st.cache_data.clear()
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
    shown = st.session_state.get('exit_shown')
    if done:
        with st.expander('Decided, with the price now shown', expanded=bool(shown), icon=':material/visibility:'):
            for h in held:
                e = done.get(h[0])
                if not e:
                    continue
                try:
                    after = gain_after(s, h[0])
                except Exception as ex:
                    after = f'no price now ({ex})'
                st.markdown(core.md(f"**{H_name(h[1])}**: {e['decision']}"
                                    + (f" {e['trim_pct']:.0f}%" if e.get('trim_pct') else '')
                                    + f" ({e['date']}). Now that it is written: {after}."))
            st.caption('Changed your mind? Write a new entry: the first one stays, so you can see later what you '
                       'thought before you saw the price.')


def H_name(text):
    from views.portfolio_page import name
    return name(text)

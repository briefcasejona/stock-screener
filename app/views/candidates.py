"""Candidates: every company you analysed, its value range, the 10 checks, history, your growth rates and journal."""
from datetime import date

import altair as alt
import pandas as pd
import streamlit as st

import commit
import core
from views import data, quarter

# colours for your own journal decisions; "Note" is what the program writes (it never decides for you)
BADGE = {'Buy': 'green', 'Wait': 'gray', 'No': 'red', 'Sell': 'orange', 'Still researching': 'blue', 'Note': 'gray'}
NAN = float('nan')  # an empty number cell (shown blank, never "None")


def palette():
    """The value line's colours, for the light or the dark look (Apple's system colours)."""
    if (st.context.theme.type or 'light') == 'dark':
        return {'zone': '#1f4d2c', 'band': '#48484a', 'ink': '#e5e5ea', 'price': '#ff453a', 'bars': '#64a8f0'}
    return {'zone': '#d6f0dc', 'band': '#d1d1d6', 'ink': '#3a3a3c', 'price': '#d70015', 'bars': '#7fa6d6'}


def value_line(c, m):
    """Bear-bull range, the buy zone, the three scenario values and today's price on one line."""
    col = palette()
    bb = core.buy_below(c, m)
    lo = min(c['bear'], c['price'], bb) * 0.85
    hi = max(c['bull'], c['price']) * 1.06
    x = alt.X('v:Q', scale=alt.Scale(domain=[lo, hi], nice=False), axis=alt.Axis(format=',.0f', title=None, grid=False))
    zone = alt.Chart(pd.DataFrame([{'v': lo, 'v2': bb}])).mark_bar(height=26, color=col['zone'], cornerRadius=6).encode(x=x, x2='v2:Q')
    band = alt.Chart(pd.DataFrame([{'v': c['bear'], 'v2': c['bull']}])).mark_bar(height=8, color=col['band'],
                                                                                    cornerRadius=4).encode(x=x, x2='v2:Q')
    pts = pd.DataFrame([{'v': c[k], 'label': f"{k.capitalize()} {core.money(c[k], c['currency'])}"}
                        for k in ('bear', 'base', 'bull')])
    dots = alt.Chart(pts).mark_circle(size=110, color=col['ink'], opacity=1).encode(x=x, tooltip=['label'])
    names = alt.Chart(pts).mark_text(dy=-20, fontSize=12, color=col['ink']).encode(x=x, text='label')
    price = pd.DataFrame([{'v': c['price'], 'label': f"Price {core.money(c['price'], c['currency'])}"}])
    tick = alt.Chart(price).mark_tick(thickness=3, size=34, color=col['price']).encode(x=x)
    ptxt = alt.Chart(price).mark_text(dy=28, fontSize=12, fontWeight='bold', color=col['price']).encode(x=x, text='label')
    return alt.layer(zone, band, dots, names, tick, ptxt).properties(height=110).configure_view(stroke=None)


def sensitivity(c, scen):
    """How much the base value moves with one point more or less growth (the sliders were removed: one fixed rate)."""
    from valuation import dcf
    base = next((s for s in scen if s['scenario'] == 'Base'), None)
    if not base or not c.get('fcf0') or c['fcf0'] <= 0:
        return
    g, r, gt, nc = base['growth'], base['discount_rate'], base['long_term_growth'], c.get('net_cash_per_share') or 0
    up, down = (dcf(c['fcf0'], g + d, r, gt, nc)['value'] for d in (0.01, -0.01))
    st.caption(core.md(f"One point more growth a year (base {core.gpct(g + 0.01)}) gives a base value of "
                       f"{core.money(up, c['currency'])}; one point less ({core.gpct(g - 0.01)}) gives "
                       f"{core.money(down, c['currency'])}. Every company is valued at the same {core.pct(r)} discount "
                       f"rate and {core.pct(gt)} growth after year 10, so only the growth is yours to judge."))


def growth_form(c, scen, entry):
    st.markdown('**Your growth rates.** Read the latest annual report first, then set what you believe. Tick the box '
                'only when you did: the Candidates table then shows these rates as reviewed by you.')
    if entry and entry.get('worked_example'):
        st.info('ASML is the hand-made worked example from the playbook. Saving growth rates here replaces it with '
                'the standard analysis, which uses the average cash flow of the last 3 years instead of the hand-made '
                'normalised figure.')
    g = {s['scenario']: s['growth'] for s in scen}
    lo, hi = -10.0, 40.0
    start = {k: round(g.get(k, dflt) * 100, 1) for k, dflt in (('Bear', 0.03), ('Base', 0.06), ('Bull', 0.09))}
    if any(not lo <= v <= hi for v in start.values()):
        st.caption(f'A saved rate is outside {lo:.0f}% to +{hi:.0f}% a year, so the boxes start at the nearest end.')
    start = {k: min(max(v, lo), hi) for k, v in start.items()}
    with st.form(f"growth_{c['ticker']}", enter_to_submit=False):
        a, b, d = st.columns(3)
        bear = a.number_input('Bear growth (%)', lo, hi, start['Bear'], 0.5)
        base = b.number_input('Base growth (%)', lo, hi, start['Base'], 0.5)
        bull = d.number_input('Bull growth (%)', lo, hi, start['Bull'], 0.5)
        normal = 'normalised' in (c.get('fcf_basis') or '')
        basis = st.radio('Starting cash flow', ['Average of the last 3 years', 'Normalised (cyclical companies)'],
                         index=1 if normal else 0, horizontal=True,
                         help='Normalised = the average cash-flow margin times the latest revenue. The playbook uses it '
                              'for cyclical companies, whose cash flow swings with the economy.')
        rev = st.checkbox('I read the latest annual report and chose these growth rates myself', value=core.reviewed(c))
        ok = st.form_submit_button('Save and re-run the analysis', type='primary')
    if ok:
        if not bear <= base <= bull:
            st.error('Bear should be at or below base, and base at or below bull.')
            return
        with st.spinner('Re-running the analysis (downloads the latest price)...'):
            _, err = core.wl('set', ticker=c['ticker'], bear=bear / 100, base=base / 100, bull=bull / 100,
                             normalised=basis.startswith('Normalised'), average=basis.startswith('Average'), reviewed=rev)
        if err:
            st.error(err)
        else:
            data.changed()
            st.toast('Saved, and noted in the journal.')
            st.rerun()


def follow_controls(c, entry):
    if not entry:
        return
    a, b = st.columns([3, 1], vertical_alignment='bottom')
    now = 'Following' if entry['mode'] == 'watch' else 'One-time analysis'
    pick = a.segmented_control('Updates', ['Following', 'One-time analysis'], default=now, required=True,
                               key=f"follow_{c['ticker']}",
                               help='Following: the monthly check refreshes the figures and price, re-runs the analysis '
                                    'when a new annual report is out, and notes it in the journal. One-time: it stays '
                                    'as it was on the day you analysed it.')
    if pick != now:
        with st.spinner('Updating...'):
            _, err = core.wl('watch' if pick == 'Following' else 'once', ticker=c['ticker'])
        if err:
            st.error(err)
        else:
            data.changed()
            st.rerun()


def history_charts(hist, c):
    h = pd.DataFrame(hist).sort_values('year')
    if h.empty:
        st.info('No history.')
        return
    h['Year'] = h['year'].astype(str)
    cur = c['currency']
    a, b = st.columns(2)
    with a:
        st.markdown(f'**Cash flow and earnings per share** ({cur})')
        long = h.melt('Year', ['fcf_per_share', 'eps'], 'kind', 'value').dropna()
        long['kind'] = long['kind'].map({'fcf_per_share': 'Free cash flow', 'eps': 'Earnings'})
        st.altair_chart(alt.Chart(long).mark_bar().encode(
            x=alt.X('Year:N', title=None), xOffset='kind:N', y=alt.Y('value:Q', title=None),
            color=alt.Color('kind:N', title=None, legend=alt.Legend(orient='top')),
            tooltip=['Year', 'kind', alt.Tooltip('value:Q', format=',.2f')]).properties(height=240))
    with b:
        st.markdown('**P/E at each year end**')
        pe = h.dropna(subset=['pe_year_end'])
        chart = alt.Chart(pe).mark_line(point=True).encode(x=alt.X('Year:N', title=None), y=alt.Y('pe_year_end:Q', title=None),
                                                           tooltip=['Year', alt.Tooltip('pe_year_end:Q', title='P/E')])
        if c.get('pe_median_10y'):
            med = alt.Chart(pd.DataFrame([{'m': c['pe_median_10y']}])).mark_rule(strokeDash=[4, 4], color='gray').encode(y='m:Q')
            chart = chart + med
        st.altair_chart(chart.properties(height=240))
        st.caption(f"Dashed line: median {c.get('pe_median_10y')}. Today: {c.get('pe_ltm')} ({c.get('pe_basis', 'P/E')}).")
    a, b = st.columns(2)
    with a:
        st.markdown('**Return on invested capital and gross margin**')
        long = h.melt('Year', ['roic', 'gross_margin'], 'kind', 'value').dropna()
        long['kind'] = long['kind'].map({'roic': 'ROIC', 'gross_margin': 'Gross margin'})
        st.altair_chart(alt.Chart(long).mark_line(point=True).encode(
            x=alt.X('Year:N', title=None), y=alt.Y('value:Q', title=None, axis=alt.Axis(format='%')),
            color=alt.Color('kind:N', title=None, legend=alt.Legend(orient='top')),
            tooltip=['Year', 'kind', alt.Tooltip('value:Q', format='.1%')]).properties(height=240))
    with b:
        st.markdown('**Revenue** (millions, report currency)')
        st.altair_chart(alt.Chart(h.dropna(subset=['revenue_m'])).mark_bar(color=palette()['bars'], cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
            x=alt.X('Year:N', title=None), y=alt.Y('revenue_m:Q', title=None),
            tooltip=['Year', alt.Tooltip('revenue_m:Q', format=',.0f')]).properties(height=240))


def newest_first(entries):
    """The journal file is in the order entries were written: newest first, by date and then by that order."""
    return sorted(reversed(entries), key=lambda e: e['date'], reverse=True)


def journal_part(c, entries, masked=False):
    """The company's journal, newest first. Before your own estimate (masked), the program's notes show only that they
    exist: their values would give its valuation away."""
    mine = newest_first([e for e in entries if e['company'] == c['company']])
    for e in mine:
        with st.container(border=True):
            dec = core.word(e.get('decision'))
            hide = masked and e.get('author') != 'You'
            price = '' if e.get('price') is None else f" · price {core.money(e['price'], e['currency'])}"
            st.markdown(core.md(f"**{e['date']}** · :{BADGE.get(dec, 'gray')}-badge[{dec}]{price} · {e.get('author', '')}"))
            if hide:
                st.caption('A note from the program. Shown in full once you have locked in your own estimate.')
                continue
            st.markdown(core.md(e['why']))
            if e.get('change_mind'):
                st.caption(core.md(f"What would change my mind: {e['change_mind']}"))
    if not mine:
        st.caption('No entries yet.')
    journal_form(c)
    claim_form(c)


def claim_form(c, key=''):
    """A dated claim the program checks itself once the target year's figures are in."""
    import claims
    with st.form(f"claim_{c['ticker']}{key}", clear_on_submit=True):
        st.markdown(f"**Make a claim** about {c['company']}: something that can turn out wrong, checked by the program "
                    'against the filed figures. Say how sure you are; over time the program shows whether your 80% '
                    'claims come true about 80% of the time.')
        a, b, d = st.columns([2, 1, 1])
        metric = a.selectbox('Measure', list(claims.METRICS), format_func=lambda k: claims.METRICS[k][0])
        direction = b.selectbox('Direction', ['above', 'below'], format_func=lambda k: 'at least' if k == 'above' else 'at most')
        thr = d.number_input('% (a year for growth)', -50.0, 100.0, 8.0, 0.5)
        a, b = st.columns(2)
        this_year = date.today().year
        target = a.selectbox('By fiscal year', list(range(this_year - 1, this_year + 4)), index=2)
        conf = b.select_slider('How sure are you?', claims.CONFIDENCE, value=70, format_func=lambda v: f'{v}%')
        why = st.text_input('Why do you expect it? (one line)')
        if st.form_submit_button('Lock in the claim'):
            try:
                cl = claims.new(c['ticker'], c['company'], metric, direction, thr, target, conf, why)
            except ValueError as e:
                st.error(str(e))
                return
            except Exception as e:
                st.error(f'Could not save the claim: {e}')
                return
            data.changed()
            st.toast(f"Locked in: {claims.describe(cl)}.")
            st.rerun()


def journal_form(c, key=''):
    # a fresh form after each saved entry; a refused one keeps what you typed
    n = st.session_state.get(f"jr_n_{c['ticker']}{key}", 0)
    with st.form(f"jr_{c['ticker']}{key}_{n}", enter_to_submit=False):
        st.markdown(f"**Write a journal entry** for {c['company']}")
        dec = st.segmented_control('Your decision', list(core.DECISIONS), default='Wait', required=True,
                                   help='No = you decided not to buy (it used to be called "Pass").')
        why = st.text_area('Why? (in your own words)', placeholder='What the business does well, what the price assumes, '
                                                                  'and why you act or wait.')
        change = st.text_input('What would change my mind?')
        nxt = st.text_input('Next check', value=c.get('next_check', ''))
        if st.form_submit_button('Add to the journal'):
            if not why.strip():
                st.error('Write at least a line on why.')
                return
            core.add_journal_entry({'date': date.today().isoformat(), 'ticker': c['ticker'], 'company': c['company'],
                                    'price': c['price'], 'currency': c['currency'], 'decision': dec,
                                    'implied_growth': c['implied_growth'], 'bear': c['bear'], 'base': c['base'],
                                    'bull': c['bull'], 'why': why.strip(), 'change_mind': change.strip(),
                                    'next_check': nxt.strip(), 'author': 'You'})
            if dec in ('No', 'Wait'):  # a "No" or "Wait" is tracked too: was it right to stay away, or to wait?
                import portfolio
                try:
                    portfolio.add_pass(c, kind=dec,
                                       buy_below=core.buy_below(c, core.margin()) if dec == 'Wait' else None)
                except Exception as e:
                    print('tracking the decision:', e)
            st.session_state[f"jr_n_{c['ticker']}{key}"] = n + 1
            data.changed()
            st.toast('Added to the journal.')
            st.rerun()


def committed(c, entry):
    """The program shows its valuation once you have written down your own (the worked example is shown as is)."""
    return bool((entry or {}).get('worked_example') or commit.get(c['ticker']))


def commit_form(c, scen, hist):
    """Your estimate, step by step: look back, pick a starting point, decide faster or slower and why. You choose the
    growth; the value follows from it with the same sums the program uses for every company."""
    from valuation import dcf
    base = next((s for s in scen if s['scenario'] == 'Base'), {})
    r, gt = base.get('discount_rate', 0.09), base.get('long_term_growth', 0.025)
    h = sorted(hist, key=lambda x: x['year'])
    past = c.get('delivered_growth')
    rev = None
    if len(h) >= 2 and h[0].get('revenue_m') and h[-1].get('revenue_m') and h[0]['revenue_m'] > 0:
        rev = (h[-1]['revenue_m'] / h[0]['revenue_m']) ** (1 / (h[-1]['year'] - h[0]['year'])) - 1
    roic = h[-1].get('roic') if h else None
    st.markdown('#### First, your own estimate')
    st.write('The program has valued this company. Its value range stays hidden until you have written down yours, so '
             'your own judgement comes first. You don\'t need to know the answer: you need a reason. Three steps.')

    st.markdown('**1. Look back.** What the company did, from its filed figures:')
    k = st.columns(3)
    k[0].metric('Free cash flow per share', core.gpct(past) + ' a year' if past is not None else 'n/a',
                help='Free cash flow: the cash the business brings in, minus what it spends on buildings and machines. '
                     'Per share, so new shares or buybacks count.')
    k[1].metric('Revenue', core.gpct(rev) + ' a year' if rev is not None else 'n/a',
                help=f"From {h[0]['year']} to {h[-1]['year']}." if h else None)
    k[2].metric('Return on capital, last year', core.pct(roic) if roic is not None else 'n/a',
                help='Profit on the money invested in the business. Well above 10% for years usually means a moat.')
    st.caption('The History tab below has every year. Lesson 2 and 3 of the Course show what to look for.')

    st.markdown('**2. Pick a starting point** for the next 10 years.')
    choices = {}
    if past is not None:
        choices[f'The past continues ({core.gpct(past)})'] = round(past * 100, 1)
        choices[f'It slows to half ({core.gpct(past / 2)})'] = round(past * 50, 1)
    choices['Like the economy (+3.0%)'] = 3.0
    choices['My own number'] = None
    pick = st.radio('Starting point', list(choices), index=1 if past is not None else 0,
                    key=f"start_{c['ticker']}", label_visibility='collapsed')
    st.caption('A fact to weigh: fast growth rarely lasts. As companies get bigger, their growth usually slows towards '
               'that of the economy; very few keep growing fast ten years in a row (Chan, Karceski and Lakonishok, '
               '"The Level and Persistence of Growth Rates", Journal of Finance, 2003). "The past continues" is the '
               'boldest choice, not the safe one.')

    st.markdown('**3. Faster or slower, and why?** Adjust the number, and write the reason in one line.')
    start = choices[pick]
    if start is not None and not -10 <= start <= 40:
        st.caption(f'{core.gpct(start / 100)} is outside what this form takes (−10% to +40% a year), so it starts at the '
                   'nearest end. Few companies grow that fast for ten years.')
        start = min(max(start, -10.0), 40.0)
    a, b = st.columns([1, 2])
    g = a.number_input('Your growth, per year for 10 years (%)', -10.0, 40.0, start, 0.5,
                       key=f"g_{c['ticker']}_{pick}", placeholder='for example 6')
    why = b.text_input('Why this growth?', key=f"why_{c['ticker']}",
                       placeholder='For example: customers keep moving to its cloud products, but it is already big')
    if g is not None and c.get('fcf0'):
        v = dcf(c['fcf0'], g / 100, r, gt, c.get('net_cash_per_share') or 0)['value']
        st.write(core.md(f"With {core.gpct(g / 100)} a year, one share is worth about **{core.money(v, c['currency'])}** to you. Today's "
                 f"price is {core.money(c['price'], c['currency'])}."))
        st.caption(core.md(f"Same sums as for every company: starting from {core.money(c['fcf0'], c['currency'])} free cash "
                   f"flow per share, discounted at {core.pct(r)} a year, growing {core.pct(gt)} a year after year 10. "
                   'You choose the growth; the arithmetic is the same for everyone.'))
    else:
        v = None
    if st.button('Lock in my estimate and show the program\'s', type='primary', key=f"lock_{c['ticker']}"):
        if g is None:
            st.error('Fill in your growth rate.')
            return
        if v is None or v <= 0:
            st.error('With this growth the value comes out at zero or less. Check the number, or pick another '
                     'starting point.')
            return
        try:
            commit.new(c, g, round(v, 2), why, start=pick)
        except ValueError as e:
            st.error(str(e))
            return
        data.changed()
        st.rerun()


def compare(c, scen):
    mine = commit.get(c['ticker'])
    if not mine:
        return
    base = next((s for s in scen if s['scenario'] == 'Base'), {})
    gap = mine['value'] / c['base'] - 1 if c.get('base') else None
    st.markdown(f"**Your estimate ({mine['date']}) next to the program's**")
    st.dataframe(pd.DataFrame([
        {'': 'Growth a year, next 10 years', 'You': core.gpct(mine['growth'] / 100),
         'The program (base case)': core.gpct(base.get('growth')), 'The price assumes': core.gpct(c['implied_growth'])},
        {'': 'Value of one share', 'You': core.money(mine['value'], mine['currency']),
         'The program (base case)': core.money(c['base'], c['currency']),
         'The price assumes': core.money(c['price'], c['currency'])}]), hide_index=True)
    if c.get('implied_growth') is not None:
        more = mine['growth'] / 100 >= c['implied_growth']
        st.write(core.md(f"**What this tells you:** the price assumes {core.gpct(c['implied_growth'])} growth a year; you expect "
                 f"{core.gpct(mine['growth'] / 100)}. " + ("By your numbers the price is fair or cheap, if your growth comes true."
                                               if more else "By your numbers the price asks for more growth than you "
                                               "expect: you would be paying for a future you don't believe in.")))
        st.caption('Turn your growth into a claim (Journal tab, measure "Free cash flow per share"), and the figures will '
                   'show in a year or two whether you were right. That is how guesses turn into judgement.')
    if gap is not None:
        st.caption(f"Your value is {abs(gap):.0%} {'above' if gap >= 0 else 'below'} the program's base value. Neither "
                   'is the truth: write in the journal what you think explains the gap. Later, the figures show who '
                   'was closer.')


def set_hidden(ticker, hidden):
    with st.spinner('Updating...'):
        _, err = core.wl('hide' if hidden else 'unhide', ticker=ticker)
    if err:
        st.error(err)
        return
    st.session_state['undo_remove'] = ticker if hidden else None
    if not hidden:
        st.session_state['focus'] = ticker
    data.changed()
    st.rerun()


def removed_part():
    gone = [e for e in core.watchlist() if e.get('hidden')]
    undo = st.session_state.get('undo_remove')
    if undo and any(e['ticker'] == undo for e in gone):
        e = next(e for e in gone if e['ticker'] == undo)
        a, b = st.columns([4, 1], vertical_alignment='center')
        a.success(f"{e.get('company', undo)} is off your candidates list. Its analysis, estimate, claims and journal "
                  'entries are kept.')
        if b.button('Undo', icon=':material/undo:', key='undo_btn'):
            set_hidden(undo, False)
    if gone:
        with st.expander(f'Removed companies ({len(gone)})'):
            for e in gone:
                a, b = st.columns([4, 1], vertical_alignment='center')
                a.write(f"{e.get('company', e['ticker'])} · removed {e['hidden']}")
                if b.button('Put back', key=f"unhide_{e['ticker']}"):
                    set_hidden(e['ticker'], False)


def margin_control():
    a, b = st.columns([1, 3], vertical_alignment='center')
    m = a.segmented_control('Margin of safety', core.MARGINS, default=core.margin(), format_func=lambda v: f'{v}%',
                            key='margin_pick', required=True)
    if m != core.margin():
        core.save_setting(margin=m)
        data.changed()
    b.caption('Buy-below = base value minus this margin. A bigger margin protects you more when your growth rates turn '
              'out too hopeful. 20% is the playbook\'s default.')
    return m


def render():
    d = data.dashboard()
    cands = d['candidates']
    st.title('Candidates')
    st.caption(f'Companies you analysed. Whether the price is above or below your buy-below price is a fact; whether to '
               f'buy is your decision, written in the journal. {core.DISCLAIMER}')
    m = margin_control()
    removed_part()
    if not cands:
        st.info('No candidates yet. Pick a company on the Screener page and analyse it.')
        return
    rows = []
    wl = {e['ticker']: e for e in core.watchlist()}
    for c in cands:
        bb = core.buy_below(c, m)
        mine, when = core.my_decision(c, d['journal'])
        yours = f'{mine} ({when})' if mine else '—'
        if not committed(c, wl.get(c['ticker'])):
            rows.append({'Company': c['company'], 'Updates': c.get('follow', ''),
                         'Price': core.money(c['price'], c['currency']), 'Value (bear / base / bull)': 'after your estimate',
                         'Buy below': '', 'Price vs buy-below': NAN, 'Your decision': yours,
                         'Growth rates': '', 'Checks passed': '', 'Analysed': c.get('analysed', '')})
            continue
        gap = core.price_vs_buy_below(c, m)
        rows.append({'Company': c['company'], 'Updates': c.get('follow', ''), 'Price': core.money(c['price'], c['currency']),
                     'Value (bear / base / bull)': ' / '.join(core.money(c[k], c['currency']) for k in ('bear', 'base', 'bull')),
                     'Buy below': core.money(bb, c['currency']), 'Price vs buy-below': NAN if gap is None else gap * 100,
                     'Your decision': yours,
                     'Growth rates': 'reviewed by you' if core.reviewed(c) else 'not reviewed yet',
                     'Checks passed': f"{c['quality_passed'] + c['garp_passed']} of 10",
                     'Analysed': c.get('analysed', '')})
    # the selected company survives reruns; coming from the Screener (focus) selects the company just analysed
    ss = st.session_state
    focus = ss.pop('focus', None)
    if focus:
        ss['cand_ticker'] = focus
        ss['cand_gen'] = ss.get('cand_gen', 0) + 1
    default = next((i for i, c in enumerate(cands) if c['ticker'] == ss.get('cand_ticker')), 0)
    table = pd.DataFrame(rows)
    # each text column as wide as its longest value, so nothing is cut off (about 8 pixels a character)
    widths = {col: st.column_config.TextColumn(col, width=int(max(len(col), *(len(str(v)) for v in table[col])) * 8.5 + 28))
              for col in table.columns if table[col].dtype == object}
    shown = table.style.format({'Price vs buy-below': lambda v: f'{v:+.0f}%'.replace('-', '−')}, na_rep='')
    ev = st.dataframe(shown, hide_index=True, on_select='rerun', selection_mode=['single-row', 'single-cell'],
                      selection_default={'selection': {'rows': [default]}},
                      key=f"cand_table_{ss.get('cand_gen', 0)}_{len(cands)}",
                      column_config=widths | {'Company': st.column_config.TextColumn(
                                         'Company', pinned=True, width=widths['Company']['width']
                                         if isinstance(widths.get('Company'), dict) else None),
                                     'Price vs buy-below': st.column_config.NumberColumn(
                                     help='How far the price is above (+) or below (−) the buy-below price.')})
    picked = list(ev.selection.rows) + [cell[0] for cell in getattr(ev.selection, 'cells', [])]
    sel = picked[0] if picked and picked[0] < len(cands) else default
    c = cands[sel]
    ss['cand_ticker'] = c['ticker']
    entry = next((e for e in core.watchlist() if e['ticker'] == c['ticker']), None)
    scen = [s for s in d['scenarios'] if s['company'] == c['company']]

    st.divider()
    a, b = st.columns([4, 1], vertical_alignment='center')
    a.subheader(f"{c['company']}")
    if entry and b.button('Remove from list', icon=':material/remove_circle:', key=f"hide_{c['ticker']}",
                          help='Takes it off your candidates. You can put it back any time, exactly as it was.'):
        set_hidden(c['ticker'], True)
    st.caption(f"{c['ticker']} · {c.get('exchange', '')} · {c.get('region', '')} · analysed {c.get('analysed', '')} · "
               f"figures up to {c.get('figures_to', '')}")
    if not committed(c, entry):
        st.metric(f"Price, {c.get('price_date', '')}", core.money(c['price'], c['currency']),
                  help='The latest close the program has; the Screener shows the same price.')
        commit_form(c, scen, [h for h in d['history'] if h['company'] == c['company']])
        t = st.tabs(['History', 'Latest quarter', 'Updates', 'Journal'], key='cand_tabs_new')
        with t[0]:
            history_charts([h for h in d['history'] if h['company'] == c['company']], c)
        with t[1]:
            quarter.show(c['ticker'], stamp=c.get('figures_to'))
        with t[2]:
            follow_controls(c, entry)
        with t[3]:
            journal_part(c, d['journal'], masked=True)
        return
    mine, when = core.my_decision(c, d['journal'])
    fact = core.position(c, m)
    st.markdown(core.md(
        f":{'green' if fact.startswith('At or below') else 'gray'}-badge[{fact}] "
        + (f":{BADGE.get(mine, 'gray')}-badge[Your decision: {mine}] on {when}. " if mine else
           'No decision of yours yet: write one in the Journal tab. ')
        + ('' if core.reviewed(c) else 'The growth rates are not reviewed by you yet (Your growth rates tab), so the '
           'value range is the program\'s starting point, not your judgement.')))
    bb = core.buy_below(c, m)
    k = st.columns(4)
    k[0].metric(f"Price, {c.get('price_date', '')}", core.money(c['price'], c['currency']),
                  help='The latest close the program has; the Screener shows the same price.')
    k[1].metric(f'Buy below ({m}% margin)', core.money(bb, c['currency']), f"{c['price'] / bb - 1:+.0%} away",
                delta_color='inverse')
    k[2].metric('Base value', core.money(c['base'], c['currency']))
    k[3].metric('Growth the price assumes', core.gpct(c['implied_growth']),
                f"delivered {core.gpct(c['delivered_growth'])}", delta_color='off',
                help='Reverse DCF: the yearly cash-flow growth for 10 years that makes the value equal today\'s price, '
                     'next to the growth the company delivered.')
    st.altair_chart(value_line(c, m))
    st.caption('Grey bar: bear to bull value. Green: the buy zone, up to the buy-below price. Red: today\'s price.')

    t = st.tabs(['Valuation', '10 checks', 'History', 'Latest quarter', 'Your growth rates', 'Journal'],
                key='cand_tabs')
    with t[0]:
        compare(c, scen)
        st.dataframe(pd.DataFrame([{'Scenario': s['scenario'], 'Growth, years 1–10': core.gpct(s['growth']),
                                    'Discount rate': core.pct(s['discount_rate']),
                                    'Growth after year 10': core.pct(s['long_term_growth']),
                                    'Value': core.money(s['value'], c['currency']),
                                    'Share of value after year 10': core.pct(s['after_year_10'], 0)} for s in scen]),
                     hide_index=True)
        st.caption(f"Growth rates: {c.get('assumptions_source', '')}"
                   f"{'' if core.reviewed(c) else ' (not reviewed by you)'}. Starting cash flow: {c.get('fcf_basis', '')}.")
        core.show_notes(c.get('notes'), st)
        sensitivity(c, scen)
    with t[1]:
        checks = [x for x in d['checks'] if x['company'] == c['company']]
        st.dataframe(pd.DataFrame([{'Step': x['step'], 'Check': x['filter'], 'Value': x['value'],
                                    'Threshold': x['threshold'],
                                    'Result': {'Pass': '✅ Pass', 'Fail': '❌ Fail', 'Ask why': '❓ Ask why'}.get(
                                        x['result'], '— ' + x['result'])}
                                   for x in checks]), hide_index=True)
        st.caption('Six quality checks (is it a great business?) and four GARP checks (is it growing, at a reasonable '
                   'price?). Passing all 10 means worth a deep dive, never "buy".')
    with t[2]:
        history_charts([h for h in d['history'] if h['company'] == c['company']], c)
    with t[3]:
        quarter.show(c['ticker'], stamp=c.get('figures_to'))
    with t[4]:
        follow_controls(c, entry)
        st.divider()
        growth_form(c, scen, entry)
    with t[5]:
        journal_part(c, d['journal'])

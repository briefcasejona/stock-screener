"""Candidates: every company you analysed, its value range, the 10 checks, history, your growth rates and journal."""
from datetime import date

import altair as alt
import pandas as pd
import streamlit as st

import commit
import core
from views import data

BADGE = {'Buy': 'green', 'Deep dive': 'blue', 'Wait': 'gray'}
MEANING = {
    'Buy': 'The price is at or below your buy-below price, and the growth rates were chosen after reading the annual report.',
    'Deep dive': 'The price is at or below the buy-below price, but the growth rates are still the starting rule. '
                 'Read the annual report and set your own growth rates before deciding. This is not a buy signal.',
    'Wait': 'The price is above the buy-below price. The index fund gets this month\'s money; follow the company and wait.',
}


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


def what_if(c, scen):
    from valuation import dcf, reverse_dcf
    st.markdown('**What if?** Move the sliders to see how much the value depends on each assumption.')
    base = next((s for s in scen if s['scenario'] == 'Base'), None)
    a, b = st.columns(2)
    with a:
        g = st.slider('Cash-flow growth, years 1–10', -5.0, 25.0, round(base['growth'] * 100, 1) if base else 8.0, 0.5,
                      format='%.1f%%', key=f"wi_g_{c['ticker']}") / 100
        r = st.slider('Discount rate (the return you ask for)', 6.0, 12.0, base['discount_rate'] * 100 if base else 9.0, 0.5,
                      format='%.1f%%', key=f"wi_r_{c['ticker']}") / 100
        gt = st.slider('Growth after year 10', 0.0, 3.5, base['long_term_growth'] * 100 if base else 2.5, 0.5,
                       format='%.1f%%', key=f"wi_t_{c['ticker']}") / 100
    with b:
        if r <= gt:
            st.warning('The discount rate must be above the growth after year 10.')
            return
        v = dcf(c['fcf0'], g, r, gt, c['net_cash_per_share'])
        st.metric('Value per share', core.money(v['value'], c['currency']),
                  f"{v['value'] / c['price'] - 1:+.0%} vs today's price", delta_color='normal')
        st.caption(f"{v['terminal_share']:.0%} of this value comes after year 10. Starting cash flow "
                   f"{core.money(c['fcf0'], c['currency'])} per share; net cash {core.money(c['net_cash_per_share'], c['currency'])} per share.")
        try:
            implied = reverse_dcf(c['price'], c['fcf0'], r, gt, c['net_cash_per_share'])
            st.caption(f'At this discount rate, today\'s price assumes {implied:.1%} growth a year for 10 years.')
        except ValueError:
            pass


def growth_form(c, scen, entry):
    st.markdown('**Your growth rates.** Read the latest annual report first, then set what you believe. '
                'With the box ticked, a price under buy-below reads Buy instead of Deep dive.')
    if entry and entry.get('worked_example'):
        st.info('ASML is the hand-made worked example from the playbook. Saving growth rates here replaces it with '
                'the standard analysis, which uses the average cash flow of the last 3 years instead of the hand-made '
                'normalised figure.')
    g = {s['scenario']: s['growth'] for s in scen}
    with st.form(f"growth_{c['ticker']}"):
        a, b, d = st.columns(3)
        bear = a.number_input('Bear growth (%)', -10.0, 30.0, round(g.get('Bear', 0.03) * 100, 1), 0.5)
        base = b.number_input('Base growth (%)', -10.0, 30.0, round(g.get('Base', 0.06) * 100, 1), 0.5)
        bull = d.number_input('Bull growth (%)', -10.0, 30.0, round(g.get('Bull', 0.09) * 100, 1), 0.5)
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
                               help='Following: the weekly check refreshes the figures and price, re-runs the analysis '
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
    if entry.get('worked_example'):
        b.caption('The worked example stays in the list.')
        return
    with b.popover('Remove', icon=':material/delete:'):
        st.write(f"Remove {c['company']} from your candidates? Its journal entries stay.")
        if st.button('Yes, remove it', key=f"rm_{c['ticker']}"):
            _, err = core.wl('remove', ticker=c['ticker'])
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


def journal_part(c, entries):
    mine = newest_first([e for e in entries if e['company'] == c['company']])
    for e in mine:
        with st.container(border=True):
            st.markdown(f"**{e['date']}** · :{BADGE.get(e['decision'], 'gray')}-badge[{e['decision']}] · price "
                        f"{core.money(e['price'], e['currency'])} · {e.get('author', '')}")
            st.write(e['why'])
            if e.get('change_mind'):
                st.caption(f"What would change my mind: {e['change_mind']}")
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
    with st.form(f"jr_{c['ticker']}{key}", clear_on_submit=True):
        st.markdown(f"**Write a journal entry** for {c['company']}")
        dec = st.segmented_control('Decision', ['Buy', 'Wait', 'Deep dive', 'Sell', 'Pass'], default='Wait', required=True)
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
            if dec == 'Pass':  # a "No" is tracked too: was it right to stay away?
                import portfolio
                try:
                    portfolio.add_pass(c)
                except Exception as e:
                    print('tracking the pass:', e)
            data.changed()
            st.toast('Added to the journal.')
            st.rerun()


def committed(c, entry):
    """The program shows its valuation once you have written down your own (the worked example is shown as is)."""
    return bool((entry or {}).get('worked_example') or commit.get(c['ticker']))


def commit_form(c):
    st.markdown(f"#### First, your own estimate")
    st.write('The program has valued this company, but it shows you its numbers only after you have written down '
             'yours. That way you learn when your guesses get checked, not by reading the program\'s verdict. Use the '
             '**History** tab (revenue, cash flow, margins, return on capital) and the annual report. Your estimate is '
             'locked once saved and goes into the journal.')
    with st.form(f"commit_{c['ticker']}"):
        a, b = st.columns(2)
        g = a.number_input('Free cash flow growth you expect, per year for the next 10 years (%)', -10.0, 40.0, None,
                           0.5, placeholder='for example 8')
        v = b.number_input(f"What one share is worth to you ({c['currency']})", 0.0, 1e7, None,
                           placeholder=f"today's price is {core.money(c['price'], c['currency'])}")
        why = st.text_input('Why, in one line?', placeholder='What makes you expect this growth?')
        if st.form_submit_button('Lock in my estimate and show the program\'s', type='primary'):
            if g is None or v is None:
                st.error('Fill in both numbers.')
                return
            try:
                commit.new(c, g, v, why)
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
        {'': 'Growth a year, next 10 years', 'You': f"{mine['growth']:.1f}%",
         'The program (base case)': core.pct(base.get('growth')), 'The price assumes': core.pct(c['implied_growth'])},
        {'': 'Value of one share', 'You': core.money(mine['value'], mine['currency']),
         'The program (base case)': core.money(c['base'], c['currency']),
         'The price assumes': core.money(c['price'], c['currency'])}]), hide_index=True)
    if gap is not None:
        st.caption(f"Your value is {abs(gap):.0%} {'above' if gap >= 0 else 'below'} the program's base value. Neither "
                   'is the truth: write in the journal what you think explains the gap. Later, the figures show who '
                   'was closer.')


def render():
    m = core.margin()
    d = data.dashboard()
    cands = d['candidates']
    st.title('Candidates')
    st.caption(f'Companies you analysed. Buy-below = base value minus your {m}% margin of safety (change it on the '
               f'left). {core.DISCLAIMER}')
    if not cands:
        st.info('No candidates yet. Pick a company on the Screener page and analyse it.')
        return
    rows = []
    wl = {e['ticker']: e for e in core.watchlist()}
    for c in cands:
        bb = core.buy_below(c, m)
        if not committed(c, wl.get(c['ticker'])):
            rows.append({'Company': c['company'], 'Updates': c.get('follow', ''),
                         'Price': core.money(c['price'], c['currency']), 'Value (bear / base / bull)': 'after your estimate',
                         'Buy below': '', 'Price vs buy-below': None, 'Decision': 'Your estimate first',
                         'Checks passed': '', 'Analysed': c.get('analysed', '')})
            continue
        rows.append({'Company': c['company'], 'Updates': c.get('follow', ''), 'Price': core.money(c['price'], c['currency']),
                     'Value (bear / base / bull)': ' / '.join(core.money(c[k], c['currency']) for k in ('bear', 'base', 'bull')),
                     'Buy below': core.money(bb, c['currency']), 'Price vs buy-below': (c['price'] / bb - 1) * 100,
                     'Decision': core.decision(c, m), 'Checks passed': f"{c['quality_passed'] + c['garp_passed']} of 10",
                     'Analysed': c.get('analysed', '')})
    # the selected company survives reruns; coming from the Screener (focus) selects the company just analysed
    ss = st.session_state
    focus = ss.pop('focus', None)
    if focus:
        ss['cand_ticker'] = focus
        ss['cand_gen'] = ss.get('cand_gen', 0) + 1
    default = next((i for i, c in enumerate(cands) if c['ticker'] == ss.get('cand_ticker')), 0)
    ev = st.dataframe(pd.DataFrame(rows), hide_index=True, on_select='rerun', selection_mode='single-row',
                      selection_default={'selection': {'rows': [default]}},
                      key=f"cand_table_{ss.get('cand_gen', 0)}_{len(cands)}",
                      column_config={'Company': st.column_config.TextColumn('Company', pinned=True),
                                     'Price vs buy-below': st.column_config.NumberColumn(format='%+.0f%%',
                                     help='How far the price is above (+) or below (−) the buy-below price.')})
    sel = ev.selection.rows[0] if ev.selection.rows and ev.selection.rows[0] < len(cands) else default
    c = cands[sel]
    ss['cand_ticker'] = c['ticker']
    entry = next((e for e in core.watchlist() if e['ticker'] == c['ticker']), None)
    scen = [s for s in d['scenarios'] if s['company'] == c['company']]
    dec = core.decision(c, m)

    st.divider()
    st.subheader(f"{c['company']}")
    st.caption(f"{c['ticker']} · {c.get('exchange', '')} · {c.get('region', '')} · analysed {c.get('analysed', '')} · "
               f"figures up to {c.get('figures_to', '')}")
    if not committed(c, entry):
        st.metric('Price', core.money(c['price'], c['currency']), help=f"Close on {c.get('price_date', '')}")
        commit_form(c)
        t = st.tabs(['History', 'Updates', 'Journal'], key='cand_tabs_new')
        with t[0]:
            history_charts([h for h in d['history'] if h['company'] == c['company']], c)
        with t[1]:
            follow_controls(c, entry)
        with t[2]:
            journal_part(c, d['journal'])
        return
    st.markdown(f":{BADGE[dec]}-badge[{dec}] {MEANING[dec]}")
    bb = core.buy_below(c, m)
    k = st.columns(4)
    k[0].metric('Price', core.money(c['price'], c['currency']), help=f"Close on {c.get('price_date', '')}")
    k[1].metric(f'Buy below ({m}% margin)', core.money(bb, c['currency']), f"{c['price'] / bb - 1:+.0%} away",
                delta_color='inverse')
    k[2].metric('Base value', core.money(c['base'], c['currency']))
    k[3].metric('Growth the price assumes', core.pct(c['implied_growth']),
                f"delivered {core.pct(c['delivered_growth'])}", delta_color='off',
                help='Reverse DCF: the yearly cash-flow growth for 10 years that makes the value equal today\'s price, '
                     'next to the growth the company delivered.')
    st.altair_chart(value_line(c, m))
    st.caption('Grey bar: bear to bull value. Green: the buy zone, up to the buy-below price. Red: today\'s price.')

    t = st.tabs(['Valuation', '10 checks', 'History', 'Your growth rates', 'Journal'], key='cand_tabs')
    with t[0]:
        compare(c, scen)
        st.dataframe(pd.DataFrame([{'Scenario': s['scenario'], 'Growth, years 1–10': core.pct(s['growth']),
                                    'Discount rate': core.pct(s['discount_rate']),
                                    'Growth after year 10': core.pct(s['long_term_growth']),
                                    'Value': core.money(s['value'], c['currency']),
                                    'Share of value after year 10': core.pct(s['after_year_10'], 0)} for s in scen]),
                     hide_index=True)
        st.caption(f"Growth rates: {c.get('assumptions_source', '')}. Starting cash flow: {c.get('fcf_basis', '')}.")
        core.show_notes(c.get('notes'), st)
        st.divider()
        what_if(c, scen)
    with t[1]:
        checks = [x for x in d['checks'] if x['company'] == c['company']]
        st.dataframe(pd.DataFrame([{'Step': x['step'], 'Check': x['filter'], 'Value': x['value'],
                                    'Threshold': x['threshold'],
                                    'Result': {'Pass': '✅ Pass', 'Fail': '❌ Fail'}.get(x['result'], '— ' + x['result'])}
                                   for x in checks]), hide_index=True)
        st.caption('Six quality checks (is it a great business?) and four GARP checks (is it growing, at a reasonable '
                   'price?). Passing all 10 means worth a deep dive, never "buy".')
    with t[2]:
        history_charts([h for h in d['history'] if h['company'] == c['company']], c)
    with t[3]:
        follow_controls(c, entry)
        st.divider()
        growth_form(c, scen, entry)
    with t[4]:
        journal_part(c, d['journal'])

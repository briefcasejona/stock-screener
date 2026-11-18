"""Add a report: annual reports you download yourself, for companies the free sources miss or for more years.

ESEF reports (the official machine-readable version, a .zip or .xhtml) are read exactly. PDFs need you to point out
the lines that hold each figure; the report is saved only if the balance sheet balances, EPS x shares matches net
profit and the cash flow adds up (screener/code/user_reports.py does the reading and the checks).
"""
import hashlib
import json
import os
import re
from datetime import date

import streamlit as st

import core
from views import data

NEW = '__new__'
# figure, what you look for, search pattern, needed?, statement it is on, which match to offer first on that page
# (the totals of a cash flow statement come after the lines they add up, so there the last match is the likely one)
I, B, C = 'income', 'balance', 'cash'
ITEMS = [
    ('Revenue', 'Revenue (income statement)', r'^\s*(total\s+)?(revenues?|net sales|sales|turnover)\b', True, I, 'first'),
    ('CostOfSales', 'Cost of sales', r'^\s*cost of (sales|revenues?|goods sold)', False, I, 'first'),
    ('GrossProfit', 'Gross profit', r'^\s*gross (profit|margin)\b', False, I, 'first'),
    ('ProfitLossFromOperatingActivities', 'Operating profit (EBIT)',
     r'^\s*(operating (profit|income|result)|ebit\b|(profit|income|result) from operations)', False, I, 'first'),
    ('ProfitLossBeforeTax', 'Profit before tax', r'before (income )?tax', False, I, 'first'),
    ('IncomeTaxExpenseContinuingOperations', 'Income tax', r'^\s*(income tax(es| expenses?)?|taxes)\b', False, I, 'first'),
    ('FinanceCosts', 'Interest expense', r'^\s*(interest expenses?|finance (costs|expenses?)|financial expenses?)', False, I,
     'first'),
    ('ProfitLossAttributableToOwnersOfParent', 'Net profit for the shareholders (owners of the parent)',
     r'(owners|shareholders|equity holders|stockholders) of (the )?(parent|company)|attributable to (the )?'
     r'(owners|shareholders|equity holders)|shareholders of', True, I, 'first'),
    ('DilutedEarningsLossPerShare', 'Diluted earnings per share', r'diluted', True, I, 'first'),
    ('AdjustedWeightedAverageShares', 'Weighted average number of shares, diluted (often in a note)',
     r'weighted.*diluted|diluted.*(shares|weighted)', True, None, 'first'),
    ('CashFlowsFromUsedInOperatingActivities', 'Cash flow from operating activities',
     r'cash.*(from|generated|provided|used).*operating|operating activities|^\s*operating cash flow', True, C, 'last'),
    ('PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities',
     'Capital spending (purchases of property, plant, equipment; intangibles)',
     r'(purchases?|acquisitions?|additions?|capital expenditure|investments? in).*(property|tangible|plant|equipment)'
     r'|^\s*capital expenditure', True,
     C, 'first'),
    ('CashFlowsFromUsedInInvestingActivities', 'Cash flow from investing activities',
     r'cash.*investing activities|investing activities.*total|^\s*net cash.*investing|^\s*investing cash flow', False, C, 'last'),
    ('CashFlowsFromUsedInFinancingActivities', 'Cash flow from financing activities',
     r'cash.*financing activities|financing activities.*total|^\s*net cash.*financing|^\s*financing cash flow', False, C, 'last'),
    ('EffectOfExchangeRateChangesOnCashAndCashEquivalents', 'Effect of exchange rates on cash',
     r'(exchange rate|currency (re)?translation|foreign exchange)', False, C, 'first'),
    ('CashFlowStatementClosingCash', 'Cash at the end of the year (cash flow statement)',
     r'cash and cash equivalents at (the )?end', False, C, 'first'),
    ('CashAndCashEquivalents', 'Cash and cash equivalents (balance sheet)', r'^\s*cash and cash equivalents\b', True, B,
     'first'),
    ('EquityAttributableToOwnersOfParent', 'Equity for the shareholders',
     r'equity attributable to|total (shareholders.?|stockholders.?) equity', True, B, 'first'),
    ('NoncontrollingInterests', 'Non-controlling interests (balance sheet)', r'^\s*non-?controlling interests?', False, B,
     'first'),
    ('CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings', 'Short-term borrowings',
     r'(short-term (debt|borrowings)|current (borrowings|financial liabilities)|current portion of long-term)'
     r'|^\s*financial debt', False, B, 'first'),
    ('NoncurrentPortionOfNoncurrentBorrowings', 'Long-term borrowings',
     r'^\s*(long-term (debt|borrowings)|non-?current (borrowings|financial liabilities)|borrowings|financial debt)\b',
     False, B, 'last'),
    ('Assets', 'Total assets', r'^\s*total assets', True, B, 'first'),
    ('EquityAndLiabilities', 'Total equity and liabilities',
     r'^\s*total (equity and liabilities|liabilities and (shareholders.? |stockholders.? )?equity)', True, B, 'first'),
]
# a quarterly or half-year report: the same figures, the period's cash at both ends from the cash flow statement
# (US reports have no "attributable to" line when there are no minority owners: plain "Net loss" / "Net income")
INTERIM_ITEMS = [(c, w.replace('Cash at the end of the year', 'Cash at the end of the period'),
                  p + r'|^\s*net (income|loss|profit|earnings)( \(loss\))?\s*\$?\s*[\d(]'
                  if c == 'ProfitLossAttributableToOwnersOfParent' else p, n, k, f)
                 for c, w, p, n, k, f in ITEMS] + [
    ('CashFlowStatementOpeningCash', 'Cash at the beginning of the period (cash flow statement)',
     r'cash.*(beginning|start) of (the )?(period|year)', False, C, 'first')]
# under a heading such as "Diluted earnings per share" the figure is often on a line below it ("Net income 12.11")
BELOW_HEADING = {'DilutedEarningsLossPerShare'}
TOTAL_LINE = re.compile(r'net (income|profit|earnings)|total|attributable|profit for the (year|period)', re.I)
UNITS = {'millions': 1e6, 'thousands': 1e3, 'units': 1}


def company_picker(key, everyone=False):
    """A European company from the lists (any company with everyone), or a new one. Returns (ticker, name, yahoo)
    or None."""
    u = {t: v for t, v in core.universe().items() if everyone or v['region'] == 'eu'}
    screened = {r['ticker'] for r in data.screen()}
    opts = [NEW] + sorted(u, key=lambda t: u[t]['name'].lower())
    fmt = lambda t: 'A company that is not in the lists' if t == NEW else \
        f"{u[t]['name']} ({t})" + ('' if t in screened else ' · not screened yet')
    t = st.selectbox('Which company?', opts, index=None, format_func=fmt, key=f'{key}_co',
                     placeholder='Type to search the companies in the lists' if everyone else
                     'Type to search the STOXX Europe 600',
                     help='US companies are not needed here: the SEC already has their figures (see the "US company" tab).')
    if t is None:
        return None
    if t != NEW:
        return t, None, None
    a, b, c = st.columns(3)
    name = a.text_input('Company name', key=f'{key}_name')
    yahoo = b.text_input('Yahoo Finance symbol', key=f'{key}_yahoo', help='As on finance.yahoo.com, e.g. SIE.DE or NESN.SW')
    ticker = c.text_input('Ticker to use here', key=f'{key}_ticker', help='Usually the same as the Yahoo symbol')
    if not (name and yahoo and ticker):
        st.caption('Fill in all three.')
        return None
    return ticker.strip().upper(), name.strip(), yahoo.strip().upper()


def keep_upload(up):
    """Save an uploaded file in the cache folder; returns its path."""
    folder = os.path.join(core.CACHE, 'uploads')
    os.makedirs(folder, exist_ok=True)
    safe = re.sub(r'[^A-Za-z0-9._-]+', '_', os.path.basename(up.name))[-120:]
    path = os.path.join(folder, safe)
    with open(path, 'wb') as fh:
        fh.write(up.getvalue())
    return path


def bring_in(ticker):
    """After a report is saved: that company's figures, price and checks again."""
    from refresh_company import refresh
    import screen as scr
    with st.spinner('Updating this company\'s figures and the screener...'):
        try:
            r = refresh(ticker)
        except Exception as e:
            st.error(f'The report is saved, but updating the figures failed: {type(e).__name__}: {e}')
            return
    data.changed()
    msg = f"{ticker} now has {r['years']} years of figures, up to {r['last_period_end']}."
    if r['years'] < scr.MIN_YEARS:
        st.warning(msg + f' The screener needs at least {scr.MIN_YEARS}: add older annual reports too (each one '
                         'usually holds two years).')
    else:
        st.success(msg + ' It is in the Screener now.')
    for p in r['problems']:
        st.caption(p)


def esef_tab():
    st.write('The best kind: the company\'s official ESEF annual report, where every figure is tagged by the company '
             'itself. Look on its investor-relations site for "ESEF" (a .zip file), or find it on filings.xbrl.org.')
    pick = company_picker('esef')
    up = st.file_uploader('ESEF report (.zip, .xhtml or .html)', type=['zip', 'xhtml', 'html', 'htm'], key='esef_file')
    if not (pick and up):
        return
    if st.button('Read the report', type='primary'):
        ticker, name, yahoo = pick
        args = ['esef', keep_upload(up), '--ticker', ticker] + (['--name', name, '--yahoo', yahoo] if name else [])
        with st.spinner('Reading the tagged figures...'):
            code, out = core.user_report_cmd(*args)
        if code:
            st.error(out.strip().splitlines()[-1] if out.strip() else 'The report could not be read.')
            return
        res = json.loads(out.strip().splitlines()[-1])
        st.success(f"Read {res['facts']} figures, year end {res['period_end']} (revenue for {', '.join(res['revenue_years'])}).")
        bring_in(ticker)


@st.cache_data(show_spinner='Reading the PDF...', max_entries=3)
def pdf_text(path, digest):
    import user_reports as ur
    return ur.pdf_pages(path)


def candidates_for(pages, pattern, ncols, below_heading=False):
    """Lines matching a search that hold at least ncols numbers, as (page, line number, line). With below_heading, a
    matching heading without numbers also offers the lines just below it, the total-like ones first."""
    import user_reports as ur
    try:
        rx = ur.safe_pattern(pattern)
    except (re.error, ValueError):
        return None
    out = []
    for i, p in enumerate(pages, 1):
        lines = p.splitlines()
        for n, line in enumerate(lines):
            if not rx.search(line) or line.lstrip()[:1].isdigit():  # a line starting with a number: contents page
                continue
            if len(ur.numbers_on(line)) >= ncols:
                out.append((i, n, line))
            elif below_heading:
                under = [(i, k, lines[k]) for k in range(n + 1, min(n + 6, len(lines)))
                         if len(ur.numbers_on(lines[k])) >= ncols]
                out += sorted(under, key=lambda f: (not TOTAL_LINE.search(f[2]), -f[1]))
    return out


def statement_pages(pages):
    """For the income statement, balance sheet and cash flow statement: its pages (the page where most of its figures
    are found, and the pages next to it that hold some too), and how many figures each page holds."""
    best, score = {}, {}
    for kind in (I, B, C):
        count = {}
        for concept, _, pattern, _, st_kind, _ in ITEMS:
            if st_kind != kind:
                continue
            for pg in {f[0] for f in candidates_for(pages, pattern, 2, concept in BELOW_HEADING) or []}:
                count[pg] = count.get(pg, 0) + 1
                score[pg] = score.get(pg, 0) + 1
        if count:
            top = max(sorted(count), key=lambda pg: count[pg])
            best[kind] = (top, {pg for pg in (top - 1, top, top + 1) if pg in count})
    return best, score


def rank(found, kind, prefer, best, score):
    """Lines on the statement's own pages first (the last match first where totals come last), then busy pages."""
    top, home = best.get(kind, (None, set()))
    if prefer == 'last':
        return sorted(found, key=lambda f: (f[0] not in home, f[0] != top, -f[0] if f[0] in home else 0,
                                            -score.get(f[0], 0), f[0], -f[1] if f[0] in home else 0))
    return sorted(found, key=lambda f: (f[0] not in home, f[0] != top, -score.get(f[0], 0) if f[0] not in home else 0,
                                        f[0]))


def label_pattern(line):
    """A search pattern for one chosen line: the words before its first number."""
    import user_reports as ur
    m = ur.NUM.search(line)
    label = line[:m.start()].strip() if m else line.strip()
    return r'^\s*' + re.escape(label) if label else None


def pick_lines(pages, items, digest, prefix, show=2):
    """For each figure, a search box and the matching lines to pick from. Returns {concept: (page, n, line)}, or
    None while a needed figure has no line."""
    import user_reports as ur
    best, score = statement_pages(pages)
    chosen, missing = {}, []
    for concept, what, pattern, needed, kind, prefer in items:
        with st.container(border=True):
            l, r = st.columns([2, 3])
            pat = l.text_input(f"{what}{' (needed)' if needed else ' (optional)'}", value=pattern,
                               key=f'{prefix}s_{concept}_{digest}', help='Search words; a regular expression, not case-sensitive.')
            found = candidates_for(pages, pat, 2, concept in BELOW_HEADING)
            if found is None:
                r.error('That search is not valid, or it repeats a repeat (like (a+)+), which can freeze the program.')
                continue
            found = rank(found, kind, prefer, best, score)[:40]
            opts = ([] if needed else [None]) + found
            fmt = lambda f: 'Leave it out' if f is None else \
                f"p{f[0]}: {f[2].strip()[:70]}  →  {', '.join(f'{v:,g}' for v in ur.numbers_on(f[2])[-show:])}"
            # optional figures start on the best match too (leave one out if the company has no such line)
            pickl = r.selectbox('Line', opts, format_func=fmt, key=f'{prefix}l_{concept}_{digest}', label_visibility='hidden',
                                index=(0 if needed else 1) if len(opts) > (0 if needed else 1) else 0 if opts else None,
                                placeholder='No line found: change the search words')
            if pickl:
                chosen[concept] = pickl
            elif needed:
                missing.append(what)
    if missing:
        st.warning('Still needed: ' + '; '.join(missing) + '.')
        return None
    return chosen


def map_items(chosen, pages):
    """The map's items for the chosen lines: [page, label pattern] (+ which match, when the label repeats)."""
    items = {}
    for concept, (pg, _, line) in chosen.items():
        pat = label_pattern(line)
        if not pat:
            st.error(f'{concept}: the chosen line has no words before its numbers; pick another.')
            return None
        same = [ln for ln in pages[pg - 1].splitlines() if re.search(pat, ln, re.I)]
        nth = next((i for i, ln in enumerate(same) if ln == line), 0)
        items[concept] = [pg, pat] + ([None, nth] if len(same) > 1 else [])
    return items


def run_map(cmd, path, m, map_path):
    """Run the reader on a map; returns its result, or None after showing why nothing was saved."""
    core.localdata.write_json(map_path, m, indent=1)
    with st.spinner('Reading the figures and checking them...'):
        code, out = core.user_report_cmd(cmd, path, '--map', map_path)
    try:  # the result is the JSON block printed last (the PDF library may print warnings around it)
        start = out.rfind('\n{') + 1 if '\n{' in out else out.index('{')
        res = json.JSONDecoder().raw_decode(out[start:])[0]
    except ValueError:
        st.error(out or 'The PDF could not be read.')
        return None
    if code or not res.get('saved'):
        st.error('Not saved: the figures do not add up yet. Check the lines below (the columns, the units, and '
                 'whether each line is the total), then try again.')
        for p in res.get('problems', []):
            st.write(f'- {p}')
        return None
    return res


def pdf_tab():
    st.write('For a company without an ESEF report. Download the annual report PDF (or the "consolidated financial '
             'statements" PDF), then point out the line that holds each figure. The program reads the numbers and '
             'checks they add up before saving anything.')
    pick = company_picker('pdf')
    up = st.file_uploader('Annual report (PDF)', type=['pdf'], key='pdf_file')
    if not (pick and up):
        return
    ticker, name, yahoo = pick
    path = keep_upload(up)
    digest = hashlib.sha256(up.getvalue()).hexdigest()[:12]
    a, b, c, d = st.columns(4)
    year_end = a.date_input('Financial year ends on', value=date(date.today().year - 1, 12, 31), key=f'pe_{digest}')
    currency = b.text_input('Currency of the statements', value='EUR', key=f'cur_{digest}').strip().upper()
    unit = c.selectbox('Amounts are in', list(UNITS), key=f'unit_{digest}')
    sunit = d.selectbox('Share numbers are in', list(UNITS), index=0, key=f'sunit_{digest}')
    order = st.radio('The year columns are', ['newest year first', 'oldest year first'], horizontal=True, key=f'ord_{digest}')
    y = year_end.year
    columns = [str(y), str(y - 1)] if order.startswith('newest') else [str(y - 1), str(y)]
    pages = pdf_text(path, digest)
    st.caption(f'{len(pages)} pages read. For each figure, pick the line from the statements (the numbers shown are '
               f'the last two on the line: {columns[0]}, then {columns[1]}). Change the search words if the right line '
               'is not offered.')
    chosen = pick_lines(pages, ITEMS, digest, '')
    if chosen is None or not st.button('Read and check', type='primary'):
        return
    items = map_items(chosen, pages)
    if items is None:
        return
    m = {'ticker': ticker, 'period_end': year_end.isoformat(), 'currency': currency, 'scale': UNITS[unit],
         'share_scale': UNITS[sunit], 'columns': columns, 'items': items}
    if name:
        m |= {'name': name, 'yahoo': yahoo}
    res = run_map('pdf', path, m, os.path.join(core.PDF_MAPS, f'{ticker}_{year_end.isoformat()}.json'))
    if not res:
        return
    st.success(f"Read {res['facts']} figures; all checks passed. Saved with their page numbers.")
    bring_in(ticker)


def us_tab():
    st.write('A company listed in the US that is not in the S&P 500 (D-Wave Quantum, for example). No files needed: '
             'the SEC has every annual report (10-K) and quarterly report (10-Q) in a form the program reads exactly.')
    tk = st.text_input('Ticker', key='us_ticker', placeholder='e.g. QBTS').strip().upper()
    if tk and st.button('Add it', type='primary', key='us_add'):
        with st.spinner(f'Looking up {tk} at the SEC...'):
            code, out = core.user_report_cmd('add-us', tk)
        if code:
            st.error(out.strip().splitlines()[-1] if out.strip() else 'The company could not be added.')
            return
        res = json.loads(out.strip().splitlines()[-1])
        if res['added']:
            st.success(f"Added {res['name']} ({tk}).")
        else:
            st.info(f'{tk} is already in the lists; its figures are brought up to date.')
        bring_in(tk)
        st.markdown('**Latest twelve months**')
        from views import quarter
        quarter.show(tk, stamp=date.today().isoformat() + tk)


def interim_tab():
    from views import quarter
    st.write('Quarterly and half-year reports are unaudited and cover only part of a year. The program puts them '
             'together into the **latest twelve months** (the last full year, plus the months since, minus the same '
             'months a year earlier) and shows that next to the last full year. Your valuation and the screener keep '
             'using full years.')
    st.info('**US companies don\'t need an upload**: their quarterly figures come from the SEC with every refresh '
            '(add one that is not in the S&P 500 on the "US company" tab). For other companies, upload the report: '
            'as a PDF, or in inline XBRL (.htm, .xhtml or .zip) when the company publishes one.',
            icon=':material/info:')
    u = core.universe()
    pick = st.selectbox('Show the latest twelve months of', sorted(u, key=lambda k: u[k]['name'].lower()), index=None,
                        format_func=lambda k: f"{u[k]['name']} ({k})", key='q_show', placeholder='Type to search')
    if pick:
        quarter.show(pick, stamp=str(len(core.own_reports())))
    st.divider()
    st.markdown('**Upload a quarterly or half-year report**')
    pick = company_picker('interim', everyone=True)
    up = st.file_uploader('Report (PDF, or inline XBRL: .htm, .xhtml, .zip)',
                          type=['pdf', 'zip', 'xhtml', 'html', 'htm'], key='interim_file')
    if not (pick and up):
        return
    ticker, name, yahoo = pick
    if up.name.lower().endswith('.pdf'):
        interim_pdf(ticker, name, yahoo, up)
        return
    if st.button('Read the report', type='primary', key='interim_read'):
        args = ['interim', keep_upload(up), '--ticker', ticker] + (['--name', name, '--yahoo', yahoo] if name else [])
        with st.spinner('Reading the tagged figures...'):
            code, out = core.user_report_cmd(*args)
        if code:
            st.error(out.strip().splitlines()[-1] if out.strip() else 'The report could not be read.')
            return
        res = json.loads(out.strip().splitlines()[-1])
        st.success(f"Read {res['facts']} figures for {res['from']} to {res['period_end']}.")
        from views import quarter
        quarter.show(ticker, stamp=res['saved'])


def interim_pdf(ticker, name, yahoo, up):
    from views import quarter
    path = keep_upload(up)
    digest = hashlib.sha256(up.getvalue()).hexdigest()[:12]
    today = date.today()
    q_end = date(today.year, ((today.month - 1) // 3) * 3 or 12, 1)  # the last quarter end before this one
    q_end = date(q_end.year - (1 if q_end.month == 12 else 0), q_end.month, 1)
    import calendar
    q_end = q_end.replace(day=calendar.monthrange(q_end.year, q_end.month)[1])
    a, b = st.columns(2)
    end = a.date_input('The report covers up to', value=q_end, key=f'qe_{digest}')
    start = b.date_input('Counting from (the first day after the last year end)', value=date(end.year, 1, 1),
                         key=f'qs_{digest}', help='For a company whose year ends on 31 December: 1 January.')
    a, b, c = st.columns(3)
    currency = a.text_input('Currency of the statements', value='EUR', key=f'qcur_{digest}').strip().upper()
    unit = b.selectbox('Amounts are in', list(UNITS), key=f'qunit_{digest}')
    sunit = c.selectbox('Share numbers are in', list(UNITS), index=0, key=f'qsunit_{digest}')
    order = st.radio('In each pair of columns', ['this year first', 'last year first'], horizontal=True,
                     key=f'qord_{digest}')
    cols = st.radio('On the income statement, the figures since the start of the year are',
                    ['the last two columns', 'the two columns before the last two'], horizontal=True,
                    key=f'qcols_{digest}',
                    help='A US 10-Q prints "three months" first and "nine months" last: the last two columns. Some '
                         'European reports print the half year first and the quarter last.')
    pages = pdf_text(path, digest)
    st.caption(f'{len(pages)} pages read. Pick each figure\'s line from the statements; the numbers shown are the last '
               'four on the line. The program uses the figures since the start of the year (not the quarter alone) '
               'and, on the balance sheet, the column for the report\'s own date.')
    chosen = pick_lines(pages, INTERIM_ITEMS, digest, 'q', show=4)
    if chosen is None or not st.button('Read and check', type='primary', key=f'qread_{digest}'):
        return
    items = map_items(chosen, pages)
    if items is None:
        return
    m = {'ticker': ticker, 'period_end': end.isoformat(), 'year_to_date_from': start.isoformat(), 'currency': currency,
         'scale': UNITS[unit], 'share_scale': UNITS[sunit], 'order': 'newest' if order.startswith('this') else 'oldest',
         'income_columns': 'last' if cols.startswith('the last') else 'before_last', 'items': items}
    if name:
        m |= {'name': name, 'yahoo': yahoo}
    res = run_map('pdf-interim', path, m, os.path.join(core.PDF_MAPS, f'{ticker}_{end.isoformat()}_interim.json'))
    if not res:
        return
    st.success(f"Read {res['facts']} figures; all checks passed. Saved with their page numbers.")
    quarter.show(ticker, stamp=res['saved'])

def render():
    st.title('Add a report')
    st.caption('For companies the free sources miss (most German and Swiss ones), for more years, or for the latest '
               'quarter. Reports you add are marked "your files" in the screener. ' + core.DISCLAIMER)
    t = st.tabs(['ESEF report', 'PDF report', 'Quarterly report', 'US company', 'Your reports'])
    with t[0]:
        esef_tab()
    with t[1]:
        pdf_tab()
    with t[2]:
        interim_tab()
    with t[3]:
        us_tab()
    with t[4]:
        own = core.own_reports()
        if own:
            st.dataframe(own, hide_index=True)
        else:
            st.caption('None yet.')

"""Add annual reports the user downloads, so companies without free machine-readable data can be screened.

Two kinds of file:
- ESEF (a .zip package or the .xhtml/.html report inside it): the tagged figures are read exactly, the same way
  as the ESEF reports from filings.xbrl.org, only from the company's own file.
- PDF: the statements are read from the text with a small map per report (which line holds which figure), then
  checked: the balance sheet must balance, the cash flow must add up to the change in cash, and EPS x shares must
  match net profit. Every figure keeps its page number so it can be checked by eye.

Each report becomes user_reports/<ticker>/<period end>__<kind>.json with its facts in the same shape as the ESEF
cache, and extract_esef.py merges them with the other sources (newest report wins, as everywhere).

Run (python3 -I code/user_reports.py ...):
  esef <file> --ticker SIE.DE                 read an ESEF package or report
  pdf-text <file>                             write the PDF's text, page by page, next to the output (for the map)
  pdf-find <file> <regex>                     list matching lines with page numbers and the numbers on them
  pdf <file> --map <map.json>                 read a PDF with a map (see PDF_MAP_EXAMPLE) and check it
  list                                        list the reports added so far
"""
import argparse
import datetime as dt
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import pyexpat
import zipfile
from xml.etree import ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import localdata  # noqa: E402

# Expat 2.4.1 and newer refuse XML that blows up while it is read ("billion laughs"); every Python 3.12+ has it
if pyexpat.version_info < (2, 4, 1):
    raise SystemExit('this Python is too old to read reports safely: install Python 3.13 from python.org')
MAX_REPORT = 300 * 2**20   # the biggest report inside an ESEF zip we read (real ones are 5-60 MB)

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = localdata.USER_REPORTS
NS = {'ix': 'http://www.xbrl.org/2013/inlineXBRL', 'xbrli': 'http://www.xbrl.org/2003/instance'}
IX, XBRLI = '{%s}' % NS['ix'], '{%s}' % NS['xbrli']

PDF_MAP_EXAMPLE = {
    'ticker': 'NESN.SW', 'period_end': '2025-12-31', 'currency': 'CHF', 'scale': 1e6,
    'columns': ['2025', '2024'],          # the order of the year columns in the statements
    'items': {                            # metric: [page, label regex, optional index of the first year column, optional nth match]
        'Revenue': [120, r'^\s*Sales\b'],
        'ProfitLossAttributableToOwnersOfParent': [120, r'attributable to shareholders of the parent'],
        'Assets': [122, r'^\s*Total assets'],
        'EquityAndLiabilities': [123, r'^\s*Total equity and liabilities'],
    },
}
# map keys -> how each is stored (flow = full year, stock = year end)
FLOW = {'Revenue', 'CostOfSales', 'GrossProfit', 'ProfitLossFromOperatingActivities', 'ProfitLossBeforeTax',
        'IncomeTaxExpenseContinuingOperations', 'ProfitLossAttributableToOwnersOfParent', 'DilutedEarningsLossPerShare',
        'AdjustedWeightedAverageShares', 'CashFlowsFromUsedInOperatingActivities', 'FinanceCosts',
        'PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities', 'CashFlowsFromUsedInInvestingActivities',
        'CashFlowsFromUsedInFinancingActivities', 'EffectOfExchangeRateChangesOnCashAndCashEquivalents'}
POSITIVE = {'CostOfSales', 'IncomeTaxExpenseContinuingOperations', 'FinanceCosts',
            'PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities'}
STOCK = {'EquityAttributableToOwnersOfParent', 'Equity', 'NoncontrollingInterests', 'CashAndCashEquivalents',
         'CurrentFinancialAssetsAtFairValueThroughProfitOrLoss', 'Borrowings', 'NoncurrentPortionOfNoncurrentBorrowings',
         'CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings', 'Assets', 'EquityAndLiabilities',
         'CashFlowStatementClosingCash'}  # the last one is only used for the cash check


def ensure_company(ticker, name=None, yahoo=None):
    """The company must be in a universe; one outside the S&P 500 and STOXX 600 is added to the European list."""
    import csv
    if any(r['ticker'] == ticker for r in localdata.eu_universe()) or \
            any(r['ticker'] == ticker for r in csv.DictReader(open(f'{BASE}/raw/universe_us.csv', encoding='utf-8', errors='replace'))):
        return
    if not (name and yahoo):
        raise SystemExit(f'{ticker} is not in the screener lists: add --name and --yahoo (its Yahoo symbol) to add it')
    localdata.add_company({'ticker': ticker, 'name': name, 'yahoo': yahoo, 'source': 'user'})


def save(ticker, period_end, kind, source_file, facts, extra=None):
    os.makedirs(f'{OUT}/{ticker}', exist_ok=True)
    path = f'{OUT}/{ticker}/{period_end}__{kind}.json'
    doc = {'ticker': ticker, 'period_end': period_end, 'kind': kind, 'source_file': source_file,
           'added': dt.date.today().isoformat(), 'facts': facts, **(extra or {})}
    localdata.write_json(path, doc, indent=0)
    return path


# ---------- ESEF (inline XBRL) ----------

def number(text, fmt):
    t = (text or '').strip()
    f = (fmt or '').split(':')[-1].replace('-', '')
    if f in ('zerodash', 'fixedzero') or t in ('-', '–', '—', ''):
        return 0.0
    t = re.sub(r'[\s  \']', '', t)
    if 'commadecimal' in f:
        t = t.replace('.', '').replace(',', '.')
    else:
        t = t.replace(',', '')
    return float(t)


def ixbrl_facts(stream):
    """Non-dimensional numeric facts of an inline XBRL report: [concept, start, end, value, unit].
    Inline XBRL dates are the real dates (unlike xBRL-JSON's next-midnight ends), so nothing is shifted."""
    contexts, units, raw = {}, {}, []
    for _, el in ET.iterparse(stream, events=('end',)):
        tag = el.tag
        if tag == XBRLI + 'context':
            if el.find('.//xbrli:segment', NS) is None and el.find('.//xbrli:scenario', NS) is None:
                p = el.find('xbrli:period', NS)
                inst = p.findtext('xbrli:instant', namespaces=NS)
                contexts[el.get('id')] = (None, inst.strip()) if inst else \
                    (p.findtext('xbrli:startDate', namespaces=NS).strip(), p.findtext('xbrli:endDate', namespaces=NS).strip())
            el.clear()
        elif tag == XBRLI + 'unit':
            ms = [m.text.split(':')[-1] for m in el.iter(XBRLI + 'measure')]
            units[el.get('id')] = '/'.join(ms)
            el.clear()
        elif tag == IX + 'nonFraction':
            if el.get('{http://www.w3.org/2001/XMLSchema-instance}nil') != 'true':
                try:
                    v = number(''.join(el.itertext()), el.get('format')) * 10 ** int(el.get('scale') or 0)
                    raw.append((el.get('name'), el.get('contextRef'), el.get('unitRef'), -v if el.get('sign') == '-' else v))
                except ValueError:
                    pass
    facts = []
    for name, ctx, unit, v in raw:
        if ctx in contexts:  # dimensional contexts are left out
            start, end = contexts[ctx]
            facts.append([name.split(':')[-1], start, end, v, units.get(unit, '')])
    return facts


def report_period_end(facts):
    """The report's own year end: the latest end date of a full-year revenue or profit figure."""
    ends = [e for c, s, e, v, u in facts
            if s and c in ('Revenue', 'ProfitLoss', 'ProfitLossAttributableToOwnersOfParent', 'CashFlowsFromUsedInOperatingActivities')
            and 350 <= (dt.date.fromisoformat(e) - dt.date.fromisoformat(s)).days <= 380]
    if not ends:
        raise SystemExit('no full-year revenue or profit found: is this an annual report?')
    return max(ends)


def cmd_esef(args):
    ensure_company(args.ticker, args.name, args.yahoo)
    path = args.file
    if zipfile.is_zipfile(path):
        z = zipfile.ZipFile(path)
        reports = [n for n in z.namelist() if '/reports/' in n and n.lower().endswith(('.xhtml', '.html', '.htm'))]
        if not reports:
            raise SystemExit('no report found in the package (expected a reports/ folder)')
        biggest = max(reports, key=lambda n: z.getinfo(n).file_size)
        if z.getinfo(biggest).file_size > MAX_REPORT:  # a small zip can unpack to many gigabytes
            raise SystemExit(f'the report inside the zip is bigger than {MAX_REPORT // 2**20} MB unpacked: not read')
        with z.open(biggest) as fh:
            facts = ixbrl_facts(fh)
    else:
        if os.path.getsize(path) > MAX_REPORT:
            raise SystemExit(f'the report is bigger than {MAX_REPORT // 2**20} MB: not read')
        with open(path, 'rb') as fh:
            facts = ixbrl_facts(fh)
    if not facts:
        raise SystemExit('no tagged figures found: this file is not an ESEF report')
    pe = report_period_end(facts)
    out = save(args.ticker, pe, 'esef', os.path.basename(path), facts)
    years = sorted({e[:4] for c, s, e, v, u in facts if s and c == 'Revenue'})
    print(json.dumps({'saved': out, 'period_end': pe, 'facts': len(facts), 'revenue_years': years}))


# ---------- PDF ----------

def pdf_pages(path):
    """The PDF's text page by page, laid out in columns: pdftotext when installed, otherwise PyMuPDF."""
    if shutil.which('pdftotext'):
        out = subprocess.run(['pdftotext', '-layout', path, '-'], capture_output=True, text=True, check=True).stdout
        return out.split('\f')
    import pymupdf
    pages = []
    for page in pymupdf.open(path):
        rows = {}
        for w in page.get_text('words'):  # x0, y0, x1, y1, word, ...: words in the same 3pt band share a line
            rows.setdefault(round((w[1] + w[3]) / 6), []).append(w)
        lines = []
        for k in sorted(rows):
            s = ''
            for w in sorted(rows[k], key=lambda w: w[0]):
                col = int(w[0] / 4.5)  # keep columns apart, as -layout does
                s = s.ljust(col) if col > len(s) else s + ' ' if s else s
                s += w[4]
            lines.append(s)
        pages.append('\n'.join(lines))
    return pages


NUM = re.compile(r'(?<![\d.,])\(?-?(?:\d{1,3}(?:[ ,. ]\d{3}(?!\d))+|\d+)(?:[.,]\d+)?\)?|(?<=\s\s)[—–−](?=\s|$)')  # a lone dash in a column = 0


def numbers_on(line):
    vals = []
    for m in NUM.finditer(line):
        t = m.group()
        if t in ('—', '–', '−'):
            vals.append(0.0)
            continue
        neg = t.startswith('(') or t.startswith('-')
        t = t.strip('()-').replace(' ', '').replace(' ', '')
        # 1,234.5 / 1.234,5 / 1.234 (dot thousands) / 1 234 / 12.3
        if re.search(r',\d{1,2}$', t):
            t = t.replace('.', '').replace(',', '.')
        elif re.fullmatch(r'\d{1,3}(\.\d{3})+', t):
            t = t.replace('.', '')
        else:
            t = t.replace(',', '')
        try:
            vals.append(-float(t) if neg else float(t))
        except ValueError:
            pass
    return vals


def cmd_pdf_text(args):
    pages = pdf_pages(args.file)
    dst = args.out or os.path.splitext(args.file)[0] + '.txt'
    with open(dst, 'w', encoding='utf-8') as fh:
        for i, p in enumerate(pages, 1):
            fh.write(f'\n===== page {i} =====\n{p}')
    print(json.dumps({'pages': len(pages), 'text': dst}))


def safe_pattern(pattern):
    """A search pattern that can't freeze the program: a repeat inside a repeat, like (a+)+, can take ages on one line."""
    if re.search(r'[+*}]\)*[+*{]|\([^()]*[+*}][^()]*\)[+*{]', pattern):
        raise ValueError('this search repeats a repeat (like (a+)+), which can freeze the program: simplify it')
    return re.compile(pattern, re.I)


def cmd_pdf_find(args):
    rx = safe_pattern(args.regex)
    for i, p in enumerate(pdf_pages(args.file), 1):
        for line in p.splitlines():
            if rx.search(line):
                print(f'p{i}: {line.strip()[:140]}  ->  {numbers_on(line)}')


def cmd_pdf(args):
    m = json.load(open(args.map, encoding='utf-8', errors='replace'))
    ensure_company(m['ticker'], m.get('name'), m.get('yahoo'))
    pages = pdf_pages(args.file)
    pe = dt.date.fromisoformat(m['period_end'])
    facts, refs, problems = [], {}, []
    for concept, item in m['items'].items():
        page, label = item[0], item[1]
        start_at = item[2] if len(item) > 2 else None  # where the year columns start, for two tables side by side
        nth = item[3] if len(item) > 3 else None       # which match, when the label repeats on the page
        rx = safe_pattern(label)
        lines = [l for l in pages[page - 1].splitlines() if rx.search(l)]
        if nth is not None and nth < len(lines):
            lines = [lines[nth]]
        if len(lines) != 1:
            problems.append(f'{concept}: {len(lines)} lines match on page {page}')
            continue
        # the year columns are the last numbers on the line (notes references come first)
        nums = numbers_on(lines[0])
        vals = nums[start_at:start_at + len(m['columns'])] if start_at is not None else nums[-len(m['columns']):]
        if len(vals) != len(m['columns']):
            problems.append(f'{concept}: expected {len(m["columns"])} numbers on page {page}: {lines[0].strip()}')
            continue
        refs[concept] = {'page': page, 'line': lines[0].strip()}
        per_share = concept == 'DilutedEarningsLossPerShare'
        if concept in POSITIVE:  # statements print costs in brackets; XBRL stores these as positive amounts
            vals = [abs(v) for v in vals]
        for col, v in zip(m['columns'], vals):
            end = pe.replace(year=int(col))
            start = (end.replace(year=end.year - 1) + dt.timedelta(days=1)).isoformat()
            scale = 1 if per_share else m.get('share_scale', m['scale']) if concept == 'AdjustedWeightedAverageShares' else m['scale']
            unit = f"{m['currency']}/shares" if per_share else 'shares' if concept == 'AdjustedWeightedAverageShares' else m['currency']
            facts.append([concept, start if concept in FLOW else None, end.isoformat(), v * scale, unit])
    # checks: a figure that does not add up stops the report from being saved
    get = lambda c, y: next((f[3] for f in facts if f[0] == c and f[2][:4] == y), None)
    for y in m['columns']:
        a, el = get('Assets', y), get('EquityAndLiabilities', y)
        if a is not None and el is not None and abs(a - el) > 0.001 * a:
            problems.append(f'{y}: balance sheet does not balance ({a:,.0f} vs {el:,.0f})')
        ni, eps, sh = get('ProfitLossAttributableToOwnersOfParent', y), get('DilutedEarningsLossPerShare', y), get('AdjustedWeightedAverageShares', y)
        if ni and eps and sh and abs(eps * sh / ni - 1) > 0.02:
            problems.append(f'{y}: EPS x shares is {eps * sh:,.0f}, net profit {ni:,.0f}')
    # the cash flow statement's own closing cash when given (it can include cash held for sale or overdrafts)
    cash_key = 'CashFlowStatementClosingCash' if 'CashFlowStatementClosingCash' in m['items'] else 'CashAndCashEquivalents'
    cash = [get(cash_key, y) for y in m['columns']]
    flows = [get(c, m['columns'][0]) for c in ('CashFlowsFromUsedInOperatingActivities', 'CashFlowsFromUsedInInvestingActivities',
                                                'CashFlowsFromUsedInFinancingActivities')]
    if None not in cash[:2] and None not in flows:
        fx = get('EffectOfExchangeRateChangesOnCashAndCashEquivalents', m['columns'][0]) or 0
        diff = cash[0] - cash[1] - sum(flows) - fx
        if abs(diff) > 0.01 * max(abs(cash[0]), 1):
            problems.append(f'cash flow does not add up to the change in cash (off by {diff:,.0f}; overdrafts or held-for-sale cash?)')
    if problems:
        print(json.dumps({'saved': None, 'problems': problems}, indent=1))
        sys.exit(1)
    out = save(m['ticker'], m['period_end'], 'pdf', os.path.basename(args.file), facts, {'page_refs': refs})
    print(json.dumps({'saved': out, 'facts': len(facts), 'checks': 'passed'}))


def cmd_list(args):
    for p in sorted(glob.glob(f'{OUT}/*/*.json')):
        d = json.load(open(p, encoding='utf-8', errors='replace'))
        print(d['ticker'], d['period_end'], d['kind'], d['source_file'], d['added'], len(d['facts']))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    a = sub.add_parser('esef'); a.add_argument('file'); a.add_argument('--ticker', required=True)
    a.add_argument('--name'); a.add_argument('--yahoo')
    a = sub.add_parser('pdf-text'); a.add_argument('file'); a.add_argument('--out')
    a = sub.add_parser('pdf-find'); a.add_argument('file'); a.add_argument('regex')
    a = sub.add_parser('pdf'); a.add_argument('file'); a.add_argument('--map', required=True)
    sub.add_parser('list')
    args = ap.parse_args()
    {'esef': cmd_esef, 'pdf-text': cmd_pdf_text, 'pdf-find': cmd_pdf_find, 'pdf': cmd_pdf, 'list': cmd_list}[args.cmd](args)


if __name__ == '__main__':
    main()

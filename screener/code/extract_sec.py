"""Yearly figures for every company in a universe from SEC EDGAR company facts.

The same method as step 1 (data-check/code/extract.py), generalised to hundreds of companies:
- only annual filings (10-K, 20-F, 40-F and amendments), only facts without dimensions (companyfacts has none);
- a fiscal year is an annual period (350-380 days); it is labelled by the calendar year it ends in;
- for each figure the newest filing that reports it wins, so all years are on the latest (restated) basis;
- inside one filing the highest-priority concept wins (revenue: the largest of the revenue concepts,
  because companies tag their total under different names).
Share counts and per-share figures are adjusted for splits using Yahoo's split history when the
value was filed before the split.

Input:  raw/universe_<region>.csv (ticker, name, sector, industry, cik), the gzip cache from fetch_sec.py,
        raw/splits_<region>.json (from prices.py)
Output: output/figures_<region>.csv, one row per company and fiscal year.
Run: python3 -I code/extract_sec.py us
"""
import csv
import gzip
import json
import os
import sys
from datetime import date

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.environ.get('SEC_CACHE', '/tmp/claude-0/sec_cache')
ANNUAL_FORMS = {'10-K', '10-K/A', '20-F', '20-F/A', '40-F', '40-F/A', '10-KT'}
FIRST_YEAR = 2015  # keep 10+ years

FLOWS = {  # metric: concepts in priority order ('max' = take the largest)
    'revenue': ('max', ['Revenues', 'RevenueFromContractWithCustomerExcludingAssessedTax',
                        'RevenueFromContractWithCustomerIncludingAssessedTax', 'SalesRevenueNet',
                        'SalesRevenueGoodsNet', 'SalesRevenueServicesNet', 'RegulatedAndUnregulatedOperatingRevenue',
                        'ElectricUtilityRevenue', 'Revenue', 'RevenueFromContractsWithCustomers']),
    'cost_of_revenue': ('first', ['CostOfRevenue', 'CostOfGoodsAndServicesSold', 'CostOfGoodsSold', 'CostOfServices',
                                  'CostOfGoodsAndServiceExcludingDepreciationDepletionAndAmortization', 'CostOfSales']),
    'gross_profit': ('first', ['GrossProfit']),
    'operating_income': ('first', ['OperatingIncomeLoss', 'ProfitLossFromOperatingActivities']),
    'pretax_income': ('first', ['IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest',
                                'IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments',
                                'ProfitLossBeforeTax']),
    'income_tax': ('first', ['IncomeTaxExpenseBenefit', 'IncomeTaxExpenseContinuingOperations']),
    'net_income': ('first', ['NetIncomeLoss', 'NetIncomeLossAvailableToCommonStockholdersBasic',
                             'ProfitLossAttributableToOwnersOfParent']),
    'eps_diluted': ('first', ['EarningsPerShareDiluted', 'EarningsPerShareBasicAndDiluted', 'DilutedEarningsLossPerShare']),
    'diluted_shares': ('first', ['WeightedAverageNumberOfDilutedSharesOutstanding',
                                 'WeightedAverageNumberOfShareOutstandingBasicAndDiluted', 'AdjustedWeightedAverageShares']),
    'operating_cash_flow': ('first', ['NetCashProvidedByUsedInOperatingActivities',
                                      'NetCashProvidedByUsedInOperatingActivitiesContinuingOperations',
                                      'CashFlowsFromUsedInOperatingActivities']),
    'interest_expense': ('first', ['InterestExpense', 'InterestExpenseNonoperating', 'InterestExpenseDebt',
                                   'InterestAndDebtExpense', 'InterestExpenseNet', 'FinanceCosts']),
    'capex': ('first', ['PaymentsToAcquirePropertyPlantAndEquipment', 'PaymentsToAcquireProductiveAssets',
                        'PaymentsForCapitalImprovements', 'PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities',
                        'PaymentsToAcquireOtherPropertyPlantAndEquipment', 'PaymentsToAcquireOtherProductiveAssets',
                        'PaymentsForProceedsFromProductiveAssets', 'PaymentsToAcquireMachineryAndEquipment',
                        'PaymentsToAcquireOilAndGasPropertyAndEquipment', 'PaymentsToExploreAndDevelopOilAndGasProperties',
                        'PaymentsForConstructionInProcess',
                        # IFRS line that also holds intangibles (used only when PP&E is not tagged on its own)
                        'PurchaseOfPropertyPlantAndEquipmentIntangibleAssetsOtherThanGoodwillInvestmentPropertyAndOtherNoncurrentAssets']),
}
STOCKS = {
    'equity': ['StockholdersEquity', 'EquityAttributableToOwnersOfParent'],
    'equity_total': ['StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest', 'Equity'],
    'minority_interest': ['MinorityInterest', 'NoncontrollingInterestInEquity', 'NoncontrollingInterests'],
    'cash': ['CashAndCashEquivalentsAtCarryingValue', 'CashAndCashEquivalents',
             'CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents', 'Cash'],
    'short_term_investments': ['ShortTermInvestments', 'MarketableSecuritiesCurrent',
                               'AvailableForSaleSecuritiesDebtSecuritiesCurrent', 'CurrentFinancialAssetsAtFairValueThroughProfitOrLoss'],
}
# Debt is tagged in many ways. Each group below is read concept by concept and the group keeps its largest
# value, so a company that tags only part of its debt under one name (Marriott: LongTermDebt = $23m) and the
# total under another (DebtAndCapitalLeaseObligations = $16.2bn) gets the total. US GAAP and IFRS names mixed.
DEBT_GROUPS = {
    # totals of all borrowings, current and non-current
    'total': ['DebtLongtermAndShorttermCombinedAmount', 'DebtAndCapitalLeaseObligations', 'Borrowings'],
    # long-term debt including its current part (short-term loans come on top)
    'long_term': ['LongTermDebt', 'DebtInstrumentCarryingAmount'],
    'noncurrent': ['LongTermDebtNoncurrent', 'LongTermDebtAndCapitalLeaseObligations', 'LongTermNotesPayable',
                   'SeniorLongTermNotes', 'ConvertibleLongTermNotesPayable', 'ConvertibleDebtNoncurrent',
                   'UnsecuredLongTermDebt', 'NotesPayable', 'SeniorNotes', 'OtherLongTermDebtNoncurrent',
                   'LongTermLineOfCredit', 'NoncurrentPortionOfNoncurrentBorrowings', 'LongtermBorrowings',
                   'NoncurrentPortionOfNoncurrentBondsIssued'],
    'current_long_term': ['LongTermDebtCurrent', 'LongTermDebtAndCapitalLeaseObligationsCurrent',
                          'ConvertibleNotesPayableCurrent', 'NotesPayableCurrent', 'UnsecuredDebtCurrent',
                          'CurrentPortionOfLongtermBorrowings', 'CurrentPortionOfNoncurrentBondsIssued'],
    'short': ['ShortTermBorrowings', 'CommercialPaper', 'LinesOfCreditCurrent', 'ShorttermBorrowings'],
    # all current debt (current part of long-term debt plus short-term loans)
    'current_total': ['DebtCurrent', 'CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings'],
}
SHARE_METRICS = {'diluted_shares'}
PER_SHARE = {'eps_diluted'}


def _d(s):
    return date.fromisoformat(s)


PREDECESSORS = {'0002115436': ['0000034088']}  # ExxonMobil's new holding company (2026) and the old registrant


def ensure(cik):
    """Download a company's facts into the cache when they are not there (fetch_sec.py fetches the universe; this
    covers predecessors, which only this file knows about)."""
    path = f'{CACHE}/{cik}.json.gz'
    if os.path.exists(path):
        return
    import net
    os.makedirs(CACHE, exist_ok=True)
    data = net.fetch(f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json')
    with gzip.open(path, 'wb') as fh:
        fh.write(data)


def load(cik):
    data = json.load(gzip.open(f'{CACHE}/{cik}.json.gz'))
    facts = []
    for old in PREDECESSORS.get(cik, []):
        ensure(old)
        facts += load(old)[1]
    for tags in data.get('facts', {}).values():
        for concept, body in tags.items():
            for unit, rows in body['units'].items():
                for r in rows:
                    if r.get('form') in ANNUAL_FORMS:
                        facts.append((concept, r.get('start'), r['end'], float(r['val']), unit, r['accn'], r['filed']))
    return data.get('entityName', ''), facts


def periods(facts):
    """Annual period end dates (from revenue / net income / cash flow facts), one per fiscal year label."""
    names = {c for m in ('revenue', 'net_income', 'operating_cash_flow') for c in FLOWS[m][1]}
    ends = {}
    for c, start, end, v, unit, accn, filed in facts:
        if c in names and start and 350 <= (_d(end) - _d(start)).days <= 380 and _d(end).year >= FIRST_YEAR:
            ends.setdefault(_d(end).year, set()).add(end)
    # a year with two different ends (a changed fiscal year) keeps the latest
    return {y: max(e) for y, e in ends.items()}


def index(facts):
    idx = {}
    for f in facts:
        idx.setdefault(f[0], []).append(f)
    return idx


def pick_flow(idx, how, concepts, end):
    per_doc = {}
    for c, start, e, v, unit, accn, filed in (f for c in concepts for f in idx.get(c, ())):
        if not start or abs((_d(e) - _d(end)).days) > 7:
            continue
        if not 350 <= (_d(e) - _d(start)).days <= 380:
            continue
        rank = -v if how == 'max' else concepts.index(c)
        if accn not in per_doc or rank < per_doc[accn][0]:
            per_doc[accn] = (rank, (filed, v, unit, c))
    if not per_doc:
        return None
    return max(h for _, h in per_doc.values())  # newest filing


def pick_stock(idx, concepts, end):
    per_doc = {}
    for c, start, e, v, unit, accn, filed in (f for c in concepts for f in idx.get(c, ())):
        if start or abs((_d(e) - _d(end)).days) > 7:
            continue
        rank = concepts.index(c)
        if accn not in per_doc or rank < per_doc[accn][0]:
            per_doc[accn] = (rank, (filed, v, unit, c))
    if not per_doc:
        return None
    return max(h for _, h in per_doc.values())


def real_split(ratio):
    """Yahoo also books spin-offs as odd 'splits' (1.196 for 3M in 2024). Keep only ratios that are a
    simple fraction p/q with q <= 4 (2-for-1, 5-for-4, 1-for-8 ...)."""
    for q in (1, 2, 3, 4):
        for r in (ratio, 1 / ratio):
            p = round(r * q)
            if p > q and abs(r - p / q) <= 0.005 * r:
                return True
    return False


def split_factor(splits, filed, end):
    """How many new shares one share filed on `filed` for a period ending `end` has become."""
    f = 1.0
    for day, ratio in splits:
        if filed < day and end < day:
            f *= ratio
    return f


def build_row(u, fy, end, facts, splits):  # facts: index() of the company's facts
    """One company-year: every figure, the concept it came from, and which fallbacks were used."""
    row = {'ticker': u['ticker'], 'name': u['name'], 'sector': u['sector'], 'fiscal_year': fy, 'period_end': end}
    currencies = set()
    for m, (how, concepts) in FLOWS.items():
        hit = pick_flow(facts, how, concepts, end)
        row[m] = hit[1] if hit else ''
        row[m + '_concept'] = hit[3] if hit else ''
        if hit and m in SHARE_METRICS | PER_SHARE:
            f = split_factor(splits, hit[0], end)
            row[m] = hit[1] * f if m in SHARE_METRICS else hit[1] / f
        elif hit and hit[2] != 'pure' and '/' not in hit[2] and hit[2] != 'shares':
            currencies.add(hit[2])
    for m, concepts in STOCKS.items():
        hit = pick_stock(facts, concepts, end)
        row[m] = hit[1] if hit else ''
    # debt: every way of adding it up that the tags allow, then the largest (overstating debt is the safe side)
    g = {}
    for name, concepts in DEBT_GROUPS.items():
        vals = [(h[1], c) for c in concepts for h in [pick_stock(facts, [c], end)] if h]
        g[name] = max(vals) if vals else None
    v = {k: (x[0] if x else None) for k, x in g.items()}
    short, cur_ltd = v['short'] or 0, v['current_long_term'] or 0
    current = max(v['current_total'] or 0, cur_ltd + short)
    estimates = {}
    if v['total'] is not None:
        estimates['total ' + g['total'][1]] = v['total']
    if v['long_term'] is not None:
        estimates[g['long_term'][1] + ' + short-term'] = v['long_term'] + short
    if v['noncurrent'] is not None or v['current_total'] is not None or v['current_long_term'] is not None or v['short'] is not None:
        estimates['non-current + current'] = (v['noncurrent'] or 0) + current
    if estimates:
        method, row['debt'] = max(estimates.items(), key=lambda kv: kv[1])
        # DebtInstrumentCarryingAmount is the principal, a few % above the balance-sheet value (10-K spot-check:
        # Lockheed, Rollins). Use it only when the balance-sheet lines miss more than a fifth of it.
        sheet = {k: x for k, x in estimates.items() if not k.startswith('DebtInstrumentCarryingAmount')}
        if method.startswith('DebtInstrumentCarryingAmount') and sheet and max(sheet.values()) >= 0.8 * row['debt']:
            method, row['debt'] = max(sheet.items(), key=lambda kv: kv[1])
        row['debt_found'], row['debt_method'] = 'yes', method
    else:
        row['debt'], row['debt_found'], row['debt_method'] = 0.0, 'no', ''
    # some companies only tag total equity on the balance sheet: take the minority owners' part off
    row['equity_source'] = 'parent'
    if row['equity'] == '' and row['equity_total'] != '':
        row['equity'] = row['equity_total'] - (row['minority_interest'] or 0)
        row['equity_source'] = 'total minus minority interest'
    # no operating profit line (common for pharma and conglomerates): pretax profit plus interest
    row['operating_income_source'] = 'reported'
    if row['operating_income'] == '' and row['pretax_income'] != '':
        row['operating_income'] = row['pretax_income'] + (row['interest_expense'] or 0)
        row['operating_income_source'] = 'pretax profit plus interest'
    if row['gross_profit'] == '' and row['revenue'] != '' and row['cost_of_revenue'] != '':
        row['gross_profit'] = row['revenue'] - row['cost_of_revenue']
    # no diluted share count tagged (common in ESEF): net profit / diluted EPS, both from the same report
    row['diluted_shares_source'] = 'reported'
    if row['diluted_shares'] == '' and row['net_income'] not in ('', 0) and row['eps_diluted'] not in ('', 0):
        row['diluted_shares'] = row['net_income'] / row['eps_diluted']
        row['diluted_shares_source'] = 'net profit / diluted EPS'
    row['currency'] = ','.join(sorted(currencies))
    return row


def company_rows(u, splits_all):
    """One company's yearly rows from its cached company facts."""
    facts = load(u['cik'])[1]
    splits = sorted((d, r) for d, r in splits_all.get(u['ticker'], []) if real_split(r))
    idx = index(facts)
    return [build_row(u, fy, end, idx, splits) for fy, end in sorted(periods(facts).items())]


def main():
    region = sys.argv[1]
    universe = list(csv.DictReader(open(f'{BASE}/raw/universe_{region}.csv')))
    splits_all = json.load(open(f'{BASE}/raw/splits_{region}.json')) if os.path.exists(f'{BASE}/raw/splits_{region}.json') else {}
    out, missing = [], []
    for u in universe:
        if not os.path.exists(f'{CACHE}/{u["cik"]}.json.gz'):
            missing.append(u['ticker'])
            continue
        out += company_rows(u, splits_all)
    fields = list(out[0])
    with open(f'{BASE}/output/figures_{region}.csv', 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(out)
    print(f'{len(out)} company-years for {len({r["ticker"] for r in out})} companies; no data file for {missing}')


if __name__ == '__main__':
    main()

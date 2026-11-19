"""Your money: broker files read the same in any language, a base currency other than the euro, paper-trade dates,
claims about years that have not ended, the Box 3 year."""
import unittest
from datetime import date, timedelta

import _env  # noqa: F401
import broker_import as B
import holdings as H
import portfolio as P

DEGIRO_NL = ('Datum,Tijd,Valutadatum,Product,ISIN,Omschrijving,FX,Mutatie,,Saldo,,Order Id\n'
             '02-11-2026,09:00,02-11-2026,,,iDEAL Deposit,,EUR,"1000,00",EUR,"1000,00",\n'
             '05-11-2026,09:00,05-11-2026,ASML,NL0010273215,Dividend,,EUR,"10,00",EUR,"1010,00",\n')
DEGIRO_EN = DEGIRO_NL.replace('Datum,Tijd,Valutadatum,Product,ISIN,Omschrijving,FX,Mutatie',
                              'Date,Time,Value date,Product,ISIN,Description,FX,Change')
IBKR_USD = ('HEADER,CTRN,LevelOfDetail,Type,Amount,CurrencyPrimary,Date/Time,TransactionID,FXRateToBase,ISIN,Description\n'
            'DATA,CTRN,DETAIL,Deposits/Withdrawals,5000,USD,20261102,9001,1,,\n'
            'DATA,CTRN,DETAIL,Deposits/Withdrawals,1000,EUR,20261102,9002,1.25,,\n'
            'DATA,CTRN,DETAIL,Sales Tax,-0.32,EUR,20261102,9003,1.25,,\n'
            'DATA,CTRN,DETAIL,Something New,-1.00,EUR,20261102,9004,1.25,,\n'
            'HEADER,TRNT,LevelOfDetail\nDATA,TRNT,ORDER\nHEADER,POST,LevelOfDetail\nDATA,POST,LOT\n'
            'HEADER,CRTT,LevelOfDetail\nDATA,CRTT,Total\n')


def empty():
    return {'events': [], 'securities': {}, 'imports': [], 'checks': []}


class Brokers(unittest.TestCase):
    def test_degiro_in_another_language_adds_nothing_twice(self):
        s = empty()
        self.assertEqual(H.add_events(s, B.parse_degiro_account(DEGIRO_NL), 'DeGiro', 'nl'), 2)
        self.assertEqual(H.add_events(s, B.parse_degiro_account(DEGIRO_EN), 'DeGiro', 'en'), 0)

    def test_ibkr_base_currency_and_unknown_kinds(self):
        events, _, _ = B.parse_ibkr(IBKR_USD)
        dep = {e['cash'].popitem()[0]: e['eur'] for e in events if e['kind'] == 'deposit'}
        self.assertAlmostEqual(dep['USD'], 4000.0)  # 5000 dollars at IBKR's own 1.25 dollars a euro
        self.assertAlmostEqual(dep['EUR'], 1000.0)
        kinds = {e.get('note') or e['kind'] for e in events}
        self.assertIn('fee', kinds)            # Sales Tax is a cost
        self.assertIn('Something New', kinds)  # kept, not refused


class PaperTrades(unittest.TestCase):
    def test_paper_trades_are_dated_today(self):
        self.assertIsNotNone(P.check_date(date.today() - timedelta(days=1), paper=True))
        self.assertIsNone(P.check_date(date.today(), paper=True))
        self.assertIsNone(P.check_date(date.today() - timedelta(days=3), paper=False))
        self.assertIsNotNone(P.check_date(date.today() - timedelta(days=8), paper=False))

    def test_withholding_by_country(self):
        r = {**P.DEFAULT_RULES, 'withholding_by_country': True}
        self.assertEqual(P.withholding(r, 'MSFT'), 0)
        self.assertEqual(P.withholding(r, 'NESN.SW'), 20)
        self.assertEqual(P.withholding({**r, 'withholding_by_country': False}, 'MSFT'), 15)


class Claims(unittest.TestCase):
    def test_only_years_that_have_not_ended(self):
        import claims
        real = claims.base_year_end
        try:
            claims.base_year_end = lambda t: (2025, date(2025, 12, 31))
            self.assertEqual(claims.valid_targets('X', today=date(2026, 3, 1)), [2026, 2027, 2028])
            self.assertEqual(claims.valid_targets('X', today=date(2027, 1, 15)), [2027, 2028])
        finally:
            claims.base_year_end = real


class Box3(unittest.TestCase):
    def test_last_years_return_until_june(self):
        self.assertEqual(H.box3_year(date(2027, 3, 1)), 2026)
        self.assertEqual(H.box3_year(date(2027, 9, 1)), 2027)


if __name__ == '__main__':
    unittest.main()

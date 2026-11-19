"""The screener on made-up figures: the honest price check, data notes capping a 10, and the page's text."""
import unittest

import _env  # noqa: F401
import screen


def rows(n=10, debt_found='yes', capex=True):
    out = []
    for i in range(n):
        g = 1.10 ** i
        out.append({'fiscal_year': str(2016 + i), 'revenue': str(1000 * g), 'gross_profit': str(600 * g),
                    'operating_income': str(300 * g), 'pretax_income': str(290 * g), 'income_tax': str(60 * g),
                    'net_income': str(230 * g), 'eps_diluted': str(2.3 * g), 'diluted_shares': '100',
                    'operating_cash_flow': str(280 * g), 'capex': str(30 * g) if capex else '',
                    'equity': str(800 * g), 'cash': '100', 'short_term_investments': '0', 'debt': '50',
                    'debt_found': debt_found})
    return out


META = {'name': 'Test', 'sector': 'Industrials', 'report_currency': 'USD'}


class Screen(unittest.TestCase):
    def test_price_check_uses_cautious_growth(self):
        cheap = screen.screen('T', META, rows(), {'price': 30.0, 'currency': 'USD', 'date': '2026-11-01'}, 1.0)
        dear = screen.screen('T', META, rows(), {'price': 400.0, 'currency': 'USD', 'date': '2026-11-01'}, 1.0)
        self.assertLessEqual(dear['base_growth'], 0.12)
        self.assertEqual(dear['g_price'], 'fail')
        self.assertIn(cheap['g_price'], ('pass', 'ask'))
        self.assertEqual(cheap['price_date'], '2026-11-01')

    def test_shrinking_price_asks_why(self):
        r = screen.screen('T', META, rows(), {'price': 15.0, 'currency': 'USD'}, 1.0)
        self.assertEqual(r['g_price'], 'ask')

    def test_serious_note_caps_at_nine(self):
        r = screen.screen('T', META, rows(capex=False), {'price': 30.0, 'currency': 'USD'}, 1.0)
        self.assertLessEqual(r['passed'], 9)

    def test_short_history_is_noted(self):
        r = screen.screen('T', META, rows(6), {'price': 30.0, 'currency': 'USD'}, 1.0)
        self.assertIn('only 6 years', r['data_flags'])


class ScreenerPage(unittest.TestCase):
    def test_debt_text_with_negative_cash_flow(self):
        from views import screener
        debt = next(c for c in screener.CHECKS if c[0] == 'q_debt')[3]
        self.assertIn('not positive', debt({'net_debt_m': 500.0, 'net_debt_to_fcf': None}))
        self.assertEqual(debt({'net_debt_m': -5.0, 'net_debt_to_fcf': None}), 'net cash')
        self.assertEqual(debt({'net_debt_m': None, 'net_debt_to_fcf': None}), 'debt not found')


if __name__ == '__main__':
    unittest.main()

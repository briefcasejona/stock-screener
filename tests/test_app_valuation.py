"""The valuation sums: the DCF, the reverse DCF, and the screener's cautious growth."""
import unittest

import _env  # noqa: F401
import screen
from valuation import dcf, reverse_dcf


class Valuation(unittest.TestCase):
    def test_reverse_dcf_inverts_dcf(self):
        v = dcf(10.0, 0.08, 0.09, 0.025, net_cash=5.0)['value']
        self.assertAlmostEqual(reverse_dcf(v, 10.0, 0.09, 0.025, 5.0), 0.08, places=4)

    def test_higher_growth_higher_value(self):
        self.assertGreater(dcf(10, 0.10, 0.09, 0.025)['value'], dcf(10, 0.05, 0.09, 0.025)['value'])

    def test_base_growth_is_cautious_and_bounded(self):
        self.assertEqual(screen.base_growth(0.30, 0.25), 0.12)   # never above 12%
        self.assertEqual(screen.base_growth(0.06, 0.09), 0.06)   # the lower of the two
        self.assertEqual(screen.base_growth(-0.05, None), 0.02)  # never below 2%
        self.assertEqual(screen.base_growth(0.0612, None), 0.06)  # nearest 0.5%

    def test_same_rate_in_every_scenario(self):
        import analyse
        self.assertEqual(len(set(analyse.RATES.values())), 1)
        self.assertEqual(analyse.RATES['base'], (0.09, 0.025))


if __name__ == '__main__':
    unittest.main()


class StartingRule(unittest.TestCase):
    def test_bear_is_half_of_base_when_revenue_grows(self):
        import analyse
        a = analyse.default_assumptions(0.15, 0.10)
        self.assertEqual((a['base'], a['bear']), (0.10, 0.05))

    def test_bear_declines_when_revenue_shrinks(self):
        import analyse
        a = analyse.default_assumptions(0.03, -0.02)
        self.assertEqual(a['bear'], -0.02)
        self.assertEqual(analyse.default_assumptions(0.03, -0.20)['bear'], -0.05)  # never below -5% a year

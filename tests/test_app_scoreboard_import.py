"""The Scoreboard reads your index fund buys from your broker records, once, and not twice when typed by hand."""
import unittest
from unittest import mock

import _env  # noqa: F401
import holdings as H
import portfolio as P


def records():
    s = {'events': [], 'securities': {}, 'imports': [], 'checks': []}
    s['events'] = [
        {'id': 'e1', 'broker': 'IBKR', 'ref': 't1', 'date': '2026-10-02', 'kind': 'buy', 'isin': 'IE00BK5BQT80',
         'units': 7.0, 'price': 140.0, 'currency': 'EUR', 'cash': {'EUR': -981.25}, 'costs_eur': 1.25, 'eur': -981.25},
        {'id': 'e2', 'broker': 'IBKR', 'ref': 't2', 'date': '2026-11-03', 'kind': 'buy', 'isin': 'IE00BK5BQT80',
         'units': 7.0, 'price': 142.0, 'currency': 'EUR', 'cash': {'EUR': -995.25}, 'costs_eur': 1.25, 'eur': -995.25},
        {'id': 'e3', 'broker': 'IBKR', 'ref': 't3', 'date': '2026-11-03', 'kind': 'buy', 'isin': 'US0000000001',
         'units': 1.0, 'price': 100.0, 'currency': 'USD', 'cash': {'USD': -101.0}, 'costs_eur': 1.0, 'eur': -90.0},
    ]
    s['securities'] = {'IE00BK5BQT80': {'symbol': 'VWCE.DE', 'kind': 'index', 'name': 'Vanguard All-World'},
                       'US0000000001': {'symbol': 'XYZ', 'kind': 'stock', 'name': 'XYZ'}}
    return s


def state():
    return {'rules': dict(P.DEFAULT_RULES), 'trades': [], 'rule_changes': []}


class FromRecords(unittest.TestCase):
    def setUp(self):
        self.p = mock.patch.object(H, 'load', records)
        self.p.start()
        self.s = mock.patch.object(P, 'save', lambda st: None)
        self.s.start()

    def tearDown(self):
        self.p.stop()
        self.s.stop()

    def test_only_the_index_fund_and_only_once(self):
        st = state()
        buys, other = P.imported_index_buys(st)
        self.assertEqual([b['event']['id'] for b in buys], ['e1', 'e2'])  # not the stock
        self.assertEqual(other, set())
        P.add_imported_index_buys(st, buys)
        t = st['trades'][0]
        self.assertEqual((t['kind'], t['symbol'], t['units'], t['amount_eur']), ('index', 'VWCE.DE', 7.0, 981.25))
        self.assertEqual(P.imported_index_buys(st)[0], [])  # added once

    def test_a_buy_typed_by_hand_is_not_added_again(self):
        st = state()
        st['trades'].append({'id': 'h', 'kind': 'index', 'date': '2026-11-04', 'amount_eur': 1000.0, 'units': 7,
                             'symbol': 'VWCE.DE', 'ticker': 'INDEX', 'recorded': '2026-11-04T10:00:00'})
        buys, _ = P.imported_index_buys(st)
        self.assertEqual([b['event']['id'] for b in buys], ['e1'])

    def test_another_index_fund_is_named(self):
        st = state()
        st['rules']['index_symbol'] = 'IWDA.AS'
        buys, other = P.imported_index_buys(st)
        self.assertEqual(buys, [])
        self.assertEqual(other, {'VWCE.DE'})


class RemoveOrder(unittest.TestCase):
    def test_a_buy_with_a_later_sale_cannot_be_removed_first(self):
        from datetime import datetime
        now = datetime.now().isoformat(timespec='seconds')
        st = state()
        st['trades'] = [{'id': 'b', 'kind': 'buy', 'ticker': 'NVDA', 'date': '2026-11-19', 'recorded': now, 'paper': True},
                        {'id': 's', 'kind': 'sell', 'ticker': 'NVDA', 'date': '2026-11-19', 'recorded': now, 'paper': True}]
        with mock.patch.object(P, 'save', lambda s: None):
            with self.assertRaises(ValueError):
                P.remove(st, 'b')


class ExitReview(unittest.TestCase):
    def test_reason_first_and_trim_needs_an_amount(self):
        import exit_review as X
        with self.assertRaises(ValueError):
            X.write('NL0010273215', 'ASML', None, 'a reason that is long enough to count as ten words here', '')
        with self.assertRaises(ValueError):
            X.write('NL0010273215', 'ASML', 'Sell', 'too short', '')
        with self.assertRaises(ValueError):
            X.write('NL0010273215', 'ASML', 'Trim', 'I hold too much of it compared with my ten percent rule', '')
        e = X.write('NL0010273215', 'ASML', 'Trim', 'I hold too much of it compared with my ten percent rule', '', 40)
        self.assertEqual((e['decision'], e['exit_review'], e['price'], e['trim_pct']), ('Trim', 'NL0010273215', None, 40))
        self.assertIn('NL0010273215', X.written())


if __name__ == '__main__':
    unittest.main()

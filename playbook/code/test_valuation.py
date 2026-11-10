"""Checks that the valuation formulas give the textbook answers. Run: python3 -I code/test_valuation.py"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from valuation import cagr, dcf, reverse_dcf  # noqa: E402


def close(a, b, tol=1e-9):
    return math.isclose(a, b, rel_tol=tol, abs_tol=tol)


def test_constant_growth_equals_gordon():
    # if growth is the same in both stages, the two-stage DCF collapses to FCF1 / (r - g)
    v = dcf(10.0, 0.03, 0.09, 0.03)['value']
    assert close(v, 10.0 * 1.03 / (0.09 - 0.03)), v


def test_zero_growth_is_a_perpetuity():
    v = dcf(5.0, 0.0, 0.10, 0.0)['value']
    assert close(v, 50.0), v


def test_hand_calculation_two_years():
    # 2-year version worked out by hand: 1.1/1.1 + 1.21/1.21 + 1.21*1.02/(0.08)/1.21
    out = dcf(1.0, 0.10, 0.10, 0.02, years=2)
    assert close(out['stage1'], 2.0)
    assert close(out['terminal'], 1.02 / 0.08)


def test_net_cash_is_added_once():
    a, b = dcf(4.0, 0.05, 0.09, 0.025), dcf(4.0, 0.05, 0.09, 0.025, net_cash=7.0)
    assert close(b['value'] - a['value'], 7.0)
    assert close(a['terminal_share'], b['terminal_share'])


def test_reverse_dcf_round_trip():
    for g in (-0.05, 0.0, 0.07, 0.15, 0.30):
        price = dcf(20.0, g, 0.09, 0.025, net_cash=3.0)['value']
        assert abs(reverse_dcf(price, 20.0, 0.09, 0.025, net_cash=3.0) - g) < 1e-9, g


def test_value_rises_with_growth_and_falls_with_rate():
    assert dcf(1, 0.10, 0.09, 0.025)['value'] > dcf(1, 0.08, 0.09, 0.025)['value']
    assert dcf(1, 0.10, 0.10, 0.025)['value'] < dcf(1, 0.10, 0.09, 0.025)['value']


def test_rate_must_exceed_long_term_growth():
    try:
        dcf(1, 0.1, 0.03, 0.03)
    except ValueError:
        return
    raise AssertionError('expected ValueError')


def test_cagr():
    assert close(cagr(100, 121, 2), 0.10)


if __name__ == '__main__':
    tests = [v for k, v in sorted(globals().items()) if k.startswith('test_')]
    for t in tests:
        t()
        print('ok ', t.__name__)
    print(f'{len(tests)} tests passed')

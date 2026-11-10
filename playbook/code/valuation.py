"""Valuation tools used by the playbook: two-stage DCF, reverse DCF and helpers.

All amounts are per share and in the company's own currency. Rates are decimals (0.09 = 9%).
Run the tests with: python3 -I code/test_valuation.py   (from the playbook folder)
"""

YEARS = 10


def dcf(fcf0, g, r, g_t, net_cash=0.0, years=YEARS):
    """Two-stage DCF, exactly as written in the playbook.

    Stage 1: FCF grows at g for `years` years, each year discounted at r.
    Stage 2: from year years+1 FCF grows at g_t forever (Gordon growth), discounted back.
    Returns a dict with the value per share and how it splits into its parts.
    """
    if r <= g_t:
        raise ValueError('discount rate must be above long-term growth')
    stage1 = sum(fcf0 * (1 + g) ** t / (1 + r) ** t for t in range(1, years + 1))
    fcf_n = fcf0 * (1 + g) ** years
    terminal = fcf_n * (1 + g_t) / (r - g_t) / (1 + r) ** years
    operating = stage1 + terminal
    return {
        'value': operating + net_cash,
        'stage1': stage1,
        'terminal': terminal,
        'net_cash': net_cash,
        'terminal_share': terminal / operating,  # share of the business value that comes after year 10
        'fcf_year10': fcf_n,
    }


def reverse_dcf(price, fcf0, r, g_t, net_cash=0.0, years=YEARS, lo=-0.5, hi=1.0):
    """The yearly FCF growth for years 1-10 that makes the DCF value equal today's price.

    Value rises steadily with g, so bisection always finds the single answer if it lies in [lo, hi].
    """
    f = lambda g: dcf(fcf0, g, r, g_t, net_cash, years)['value'] - price
    if f(lo) > 0 or f(hi) < 0:
        raise ValueError('implied growth outside the search range')
    for _ in range(200):
        mid = (lo + hi) / 2
        if f(mid) > 0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def cagr(start, end, years):
    """Compound yearly growth from start to end over `years` years."""
    return (end / start) ** (1 / years) - 1


def fair_pe(r, g, g_t, payout=1.0, years=YEARS):
    """P/E a DCF implies when all earnings are free cash (payout = FCF / earnings)."""
    return dcf(payout, g, r, g_t, 0.0, years)['value']

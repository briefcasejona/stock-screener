"""Course write-ups: junk is refused, the program's own figure goes next to yours."""
import unittest
from unittest import mock

import _env  # noqa: F401
import course as C

HISTORY = [{'company': 'X', 'year': 2024, 'revenue_m': 100.0, 'eps': 1.2},
           {'company': 'X', 'year': 2025, 'revenue_m': 120.0, 'eps': 1.5}]
GOOD = [{'name': 'revenue 2025', 'report': '120 m EUR, page 40', 'program': ''},
        {'name': 'EPS 2025', 'report': '1.50 EUR, page 41', 'program': ''},
        {'name': 'net debt', 'report': '30 m EUR, page 70', 'program': ''}]


class ProgramFigure(unittest.TestCase):
    def test_matches_name_and_year(self):
        self.assertEqual(C.program_value('Revenue 2024', HISTORY, 'X'), '2024: 100 million')
        self.assertEqual(C.program_value('EPS', HISTORY, 'X'), '2025: 1.50 per share')
        self.assertEqual(C.program_value('net debt', HISTORY, 'X'), '')
        self.assertEqual(C.program_value('revenue', HISTORY, 'Y'), '')


class Junk(unittest.TestCase):
    def setUp(self):
        self.c = {'ticker': 'X', 'company': 'X', 'price': 10.0, 'currency': 'EUR'}
        p = mock.patch.multiple(C, not_ready=lambda c: None, save=lambda s: None,
                                load=lambda: {'writeups': [], 'rule': None, 'graduated': None})
        p.start()
        self.addCleanup(p.stop)

    def test_one_letter_figures_refused(self):
        junk = [{'name': 'x', 'report': 'a', 'program': ''}] * 3
        with self.assertRaises(ValueError):
            C.add(self.c, 'No', junk, 'a perfectly fine conclusion of thirty characters', HISTORY)

    def test_same_figure_three_times_refused(self):
        with self.assertRaises(ValueError):
            C.add(self.c, 'No', [GOOD[0]] * 3, 'a perfectly fine conclusion of thirty characters', HISTORY)

    def test_short_conclusion_refused(self):
        with self.assertRaises(ValueError):
            C.add(self.c, 'No', GOOD, 'ok', HISTORY)


if __name__ == '__main__':
    unittest.main()

"""What the Candidates page says: reviewed or not, the fact about the price, your own decision, money in text."""
import unittest

import _env  # noqa: F401
import core


class Reviewed(unittest.TestCase):
    def test_starting_rule_is_not_reviewed(self):
        self.assertFalse(core.reviewed({'assumptions_source': 'starting rule from delivered growth (not yet reviewed)'}))

    def test_worked_example_is_not_reviewed(self):
        self.assertFalse(core.reviewed({'reviewed': False, 'assumptions_source': 'the worked example'}))

    def test_ticked_box_is_reviewed(self):
        self.assertTrue(core.reviewed({'reviewed': True}))
        self.assertTrue(core.reviewed({'assumptions_source': 'set by hand, reviewed'}))  # older analyses


class Decisions(unittest.TestCase):
    def test_position_is_a_fact(self):
        c = {'base': 100.0, 'price': 79.0}
        self.assertEqual(core.position(c, 20), 'At or below buy-below')
        self.assertEqual(core.position({**c, 'price': 81.0}, 20), 'Above buy-below')

    def test_margin_choices(self):
        self.assertEqual(core.MARGINS, (10, 20, 30))
        self.assertEqual(core.DEFAULT_MARGIN, 20)

    def test_my_decision_is_the_latest_of_mine(self):
        c = {'company': 'X'}
        j = [{'company': 'X', 'author': 'You', 'decision': 'Wait', 'date': '2026-01-01'},
             {'company': 'X', 'author': 'Claude (watchlist)', 'decision': 'Note', 'date': '2026-02-01'},
             {'company': 'X', 'author': 'You', 'decision': 'Pass', 'date': '2026-01-05'}]
        self.assertEqual(core.my_decision(c, j), ('No', '2026-01-05'))  # "Pass" reads "No"


class Text(unittest.TestCase):
    def test_money(self):
        self.assertEqual(core.money(-0.32, 'GBP'), '−£0.32')
        self.assertEqual(core.money(1496, 'EUR'), '€1,496')
        self.assertEqual(core.money(None, 'EUR'), 'n/a')

    def test_dollars_are_escaped_for_markdown(self):
        self.assertEqual(core.md('$350 to $400'), '\\$350 to \\$400')


def put(path, obj):
    import json
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(obj, fh)


def get(path):
    import json
    with open(path, encoding='utf-8') as fh:
        return json.load(fh)


class Backups(unittest.TestCase):
    def test_restore_is_a_full_replace(self):
        import io
        import os
        os.makedirs(core.DATA, exist_ok=True)
        path = os.path.join(core.DATA, 'holdings.json')
        put(path, {'events': [1]})
        self.assertIn('holdings.json', core.BACKUP_PARTS)
        backup = core.backup_bytes()
        put(path, {'events': [1, 2]})
        claims = os.path.join(core.DATA, 'claims.json')
        put(claims, [{'new': True}])  # made after the backup
        core.restore_backup(io.BytesIO(backup))
        self.assertEqual(get(path), {'events': [1]})
        self.assertFalse(os.path.exists(claims))

    def test_a_foreign_zip_is_refused(self):
        import io
        import zipfile
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as z:
            z.writestr('../evil.txt', 'x')
        with self.assertRaises(ValueError):
            core.restore_backup(io.BytesIO(buf.getvalue()))



class Reasons(unittest.TestCase):
    def test_junk_is_not_a_reason(self):
        for junk in ('', 'x', '.', '🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀', 'a b c d'):
            self.assertFalse(core.words(junk), junk)
        self.assertTrue(core.words('margins keep rising'))



class TableChoice(unittest.TestCase):
    def ev(self, rows=(), cells=()):
        from types import SimpleNamespace as N
        return N(selection=N(rows=list(rows), cells=list(cells)))

    def test_a_click_in_another_row_wins_over_the_ticked_row(self):
        self.assertEqual(core.picked(self.ev(rows=[0], cells=[(1, 'Company')]), 2, current=0), 1)

    def test_nothing_new_keeps_the_open_row(self):
        self.assertEqual(core.picked(self.ev(rows=[1], cells=[(1, 'Price')]), 2, current=1), 1)

    def test_the_old_ticked_row_does_not_come_back_on_the_next_run(self):
        memo = {}
        ev = self.ev(rows=[0], cells=[(1, 'Company')])
        core.picked(self.ev(rows=[0]), 2, 0, memo)  # first run: the default row
        self.assertEqual(core.picked(ev, 2, 0, memo), 1)  # a click in row 1
        self.assertEqual(core.picked(ev, 2, 1, memo), 1)  # typing elsewhere reruns with the same selection

    def test_no_selection(self):
        self.assertIsNone(core.picked(self.ev(), 2, current=0))
        self.assertIsNone(core.picked(self.ev(rows=[5]), 2))  # a row that is gone after a filter

if __name__ == '__main__':
    unittest.main()

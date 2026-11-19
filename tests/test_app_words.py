"""One meaning per word: "pass" is a check, "No" is your decision, and "deep dive" is gone from the pages."""
import os
import re
import unittest

import _env
import core
import glossary as G


class Words(unittest.TestCase):
    def test_no_deep_dive_on_any_page(self):
        views = os.path.join(_env.APP, 'views')
        for f in os.listdir(views):
            if f.endswith('.py'):
                text = open(os.path.join(views, f), encoding='utf-8').read()
                self.assertNotRegex(text.lower(), r'deep[ -]dive', f)

    def test_the_decisions_and_the_glossary_agree(self):
        for d in ('No', 'Wait', 'Still researching'):
            self.assertIn(d, core.DECISIONS)
            self.assertIn(d, G.WORDS)
        self.assertNotIn('Pass', core.DECISIONS)
        self.assertTrue(all(len(t) > 20 for t in G.WORDS.values()))


if __name__ == '__main__':
    unittest.main()

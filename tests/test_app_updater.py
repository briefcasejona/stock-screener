"""The updater asks first: nothing is installed without a yes, and "skip" and "not now" are remembered."""
import os
import tempfile
import unittest

import _env  # noqa: F401
import updater


class AsksFirst(unittest.TestCase):
    def setUp(self):
        self.old = updater.CHOICES
        updater.CHOICES = os.path.join(tempfile.mkdtemp(), 'choices.json')
        self.info = {'version': '2099.1.1.1', 'url': 'x', 'sha256': '0' * 64, 'size': 1, 'notes': 'n'}
        self.real_newer, self.real_ask, self.real_download = updater.newer, updater.ask, updater.download
        updater.newer = lambda current, timeout=5: self.info
        updater.download = lambda *a, **k: self.fail('downloaded without a yes')

    def tearDown(self):
        updater.CHOICES, updater.newer, updater.ask, updater.download = (self.old, self.real_newer, self.real_ask,
                                                                         self.real_download)

    def test_no_screen_means_no_install(self):
        self.assertFalse(updater.update_if_available('2026.1.1.1', tempfile.mkdtemp(), log=lambda m: None,
                                                     window=False))

    def test_skip_is_remembered(self):
        updater.ask = lambda current, info: 'skip'
        self.assertFalse(updater.update_if_available('2026.1.1.1', tempfile.mkdtemp(), log=lambda m: None))
        self.assertFalse(updater.wanted('2099.1.1.1'))
        self.assertTrue(updater.wanted('2099.1.1.2'))

    def test_not_now_waits_a_week(self):
        updater.ask = lambda current, info: 'later'
        updater.update_if_available('2026.1.1.1', tempfile.mkdtemp(), log=lambda m: None)
        self.assertFalse(updater.wanted('2099.1.1.1'))


if __name__ == '__main__':
    unittest.main()

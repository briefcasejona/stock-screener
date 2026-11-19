"""Two computers: another computer's fresh note blocks this one; a computer with the same name still counts as another."""
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest import mock

import _env  # noqa: F401
import datafolder as D


class OneAtATime(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        p = mock.patch.object(D, 'ID_FILE', os.path.join(self.dir, 'id'))
        p.start()
        self.addCleanup(p.stop)

    def note(self, **kw):
        with open(os.path.join(self.dir, D.LOCK), 'w', encoding='utf-8') as f:
            json.dump({'computer': D.me(), 'since': datetime.now().isoformat(timespec='seconds'), **kw}, f)

    def test_own_note_is_not_another_computer(self):
        D.mark_in_use(self.dir)
        self.assertIsNone(D.other_user(self.dir))

    def test_same_name_other_id_is_another_computer(self):
        self.note(id='someone-else')
        self.assertEqual(D.other_user(self.dir)[0], D.me())

    def test_old_note_has_expired(self):
        self.note(id='someone-else', since=(datetime.now() - timedelta(minutes=20)).isoformat(timespec='seconds'))
        self.assertIsNone(D.other_user(self.dir))


if __name__ == '__main__':
    unittest.main()

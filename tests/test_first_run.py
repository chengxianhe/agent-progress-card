import json
from datetime import datetime, timezone
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import uuid

from agent_progress_card import setup_session
from agent_progress_card.history import read_history, update_history
from agent_progress_card.store import ProgressStore, default_directory


class FirstRunTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.directory = self.root / 'private state'
        self.thread = str(uuid.uuid4())
        self.record = self.root / 'selected.jsonl'
        self.write_record()

    def write_record(self, thread=None):
        rows = [{'type': 'session_meta', 'payload': {'id': thread or self.thread}},
                {'type': 'event_msg', 'timestamp': datetime.now(timezone.utc).isoformat(), 'payload': {'type': 'task_started'}}]
        self.record.write_text(''.join(json.dumps(row) + '\n' for row in rows))

    def connect(self, **kwargs):
        return setup_session.connect(self.directory, self.record, self.thread, '我的任务', **kwargs)

    def checkpoint(self):
        return {name: (self.directory / name).read_bytes() for name in
                ('state.json', 'activity-source.json', 'history.json')}

    def test_only_selected_record_is_inspected_and_task_is_bound_before_watcher(self):
        other = self.root / 'unselected.jsonl'
        other.write_text('not a record')
        with patch.object(Path, 'glob', side_effect=AssertionError('must not discover sessions')):
            result = self.connect()
        self.assertEqual(self.thread, result['thread_id'])
        binding = json.loads((self.directory / 'activity-source.json').read_text())
        self.assertEqual(str(self.record.resolve()), binding['path'])
        state = ProgressStore(self.directory).read()
        self.assertEqual(result['task_id'], state['task_id'])
        self.assertEqual('running', state['status'])
        self.assertEqual(self.thread, read_history(self.directory)['tasks'][-1]['thread_id'])
        self.assertEqual('not a record', other.read_text())
        for name in self.checkpoint():
            self.assertEqual(0o600, (self.directory / name).stat().st_mode & 0o777)

    def test_switch_requires_confirmation_and_preserves_old_history(self):
        first = self.connect()
        before = self.checkpoint()
        with self.assertRaises(setup_session.SetupError):
            self.connect()
        self.assertEqual(before, self.checkpoint())
        second = self.connect(replace=True)
        tasks = read_history(self.directory)['tasks']
        self.assertEqual([first['task_id'], second['task_id']], [task['task_id'] for task in tasks])
        self.assertEqual('running', tasks[0]['status'])

    def test_inflight_old_feed_cannot_bind_new_task_to_old_thread(self):
        self.connect()
        before = (self.directory / 'history.json').read_bytes()
        store = ProgressStore(self.directory)
        with store._locked(), self.assertRaises(ValueError):
            update_history(self.directory, store.read(), {'thread_id': str(uuid.uuid4())})
        self.assertEqual(before, (self.directory / 'history.json').read_bytes())

    def test_failed_switch_rolls_back_every_file_byte_for_byte(self):
        self.connect()
        before = self.checkpoint()
        original = setup_session.update_history
        calls = 0
        def fail_after_save(*args):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError('simulated archive write failure')
            return original(*args)
        with patch.object(setup_session, 'update_history', side_effect=fail_after_save):
            with self.assertRaises(OSError):
                self.connect(replace=True)
        self.assertEqual(before, self.checkpoint())
        self.assertFalse(list(self.directory.glob('.setup-*')))

    def test_failed_first_connection_leaves_no_partial_binding_or_task(self):
        with patch.object(setup_session, 'update_history', side_effect=OSError('disk unavailable')):
            with self.assertRaises(OSError):
                self.connect()
        for name in ('state.json', 'activity-source.json', 'history.json'):
            self.assertFalse((self.directory / name).exists())

    def test_identity_change_and_invalid_title_do_not_modify_old_data(self):
        self.connect()
        before = self.checkpoint()
        self.write_record(str(uuid.uuid4()))
        with self.assertRaises(setup_session.SetupError):
            self.connect(replace=True)
        self.write_record()
        with self.assertRaises(ValueError):
            setup_session.connect(self.directory, self.record, self.thread, 'x' * 81, True)
        self.assertEqual(before, self.checkpoint())

    def test_corrupt_or_oversized_existing_records_are_preserved(self):
        self.connect()
        for name, value in [('history.json', b'{broken'), ('activity-source.json', b'x' * 16385)]:
            (self.directory / name).write_bytes(value)
            before = self.checkpoint()
            with self.assertRaises(ValueError):
                self.connect(replace=True)
            self.assertEqual(before, self.checkpoint())
            if name == 'history.json':
                (self.directory / name).write_text('{"version":1,"tasks":[]}')

    def test_malformed_headers_and_missing_started_event_are_rejected(self):
        for value in [[], {'type': 'session_meta', 'payload': []},
                      {'type': 'session_meta', 'payload': {'id': 'invalid'}},
                      {'type': 'session_meta', 'payload': {'id': self.thread}}]:
            self.record.write_text(json.dumps(value) + '\n')
            with self.assertRaises(ValueError):
                setup_session.inspect(self.record)
        self.record.write_bytes(b'x' * (setup_session.MAX_LINE + 1))
        with self.assertRaises(ValueError):
            setup_session.inspect(self.record)

    def test_tail_ignores_partial_and_oversized_lines(self):
        self.write_record()
        with self.record.open('ab') as stream:
            stream.write(b'x' * (setup_session.MAX_LINE + 1) + b'\n[]\n{"unfinished":')
        self.assertEqual(self.thread, setup_session.inspect(self.record)['thread_id'])

    def test_state_override_is_explicit_absolute_and_does_not_change_home(self):
        home = Path.home()
        with patch.dict(os.environ, {'WEIGUANG_STATE_DIR': str(self.directory)}):
            self.assertEqual(self.directory, default_directory())
            self.assertEqual(home, Path.home())
        with patch.dict(os.environ, {'WEIGUANG_STATE_DIR': 'relative'}):
            with self.assertRaises(ValueError):
                default_directory()

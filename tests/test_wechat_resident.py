import fcntl
import importlib.util
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
import uuid

from agent_progress_wechat.files import save_json
from agent_progress_wechat.resident import relay_target, supervise


class ResidentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.card = Path(self.temp.name) / 'card'
        self.directory = Path(self.temp.name) / 'wechat'
        self.thread = str(uuid.uuid4())
        save_json(self.card / 'wechat-source.json', dict(version=1, directory=str(self.directory)))
        save_json(self.card / 'activity-source.json', dict(thread_id=self.thread))
        save_json(self.directory / 'connection.json', dict(mode='current_session', thread_id=self.thread, status='stopped'))
        save_json(self.directory / 'credentials.json', {})

    def test_stopped_process_can_restart_without_relogin_or_permission_override(self):
        self.assertEqual(relay_target(self.card), (self.directory, self.thread, 'ready'))
        stop = threading.Event()
        calls = []
        class Child:
            def poll(self):
                stop.set()
                return 0
        def launch(args, **kwargs):
            calls.append(args)
            return Child()
        supervise(self.card, stop, launch)
        self.assertEqual(len(calls), 1)
        self.assertIn(self.thread, calls[0])
        self.assertNotIn('--reconnect', calls[0])
        self.assertNotIn('--remote-approvals', calls[0])
        self.assertNotIn('--dangerously-bypass-approvals-and-sandbox', calls[0])

    def test_manual_stop_and_reconnect_are_respected(self):
        for name in ('stop-request', 'reconnect-request'):
            path = self.directory / name
            path.touch()
            self.assertEqual(relay_target(self.card)[1:], (None, 'manually_stopped'))
            self.assertTrue(path.exists())
            path.unlink()

    def test_does_not_launch_duplicate_pollers(self):
        with (self.directory / 'service.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertEqual(relay_target(self.card)[1:], (None, 'already_running'))

    def test_binding_change_does_not_follow_another_thread(self):
        save_json(self.card / 'activity-source.json', dict(thread_id=str(uuid.uuid4())))
        self.assertEqual(relay_target(self.card)[1:], (None, 'binding_changed'))

    def test_expired_login_waits_for_new_credentials(self):
        save_json(self.directory / 'connection.json', dict(mode='current_session', thread_id=self.thread, status='expired'))
        os.utime(self.directory / 'credentials.json', (1, 1))
        self.assertEqual(relay_target(self.card)[1:], (None, 'login_expired'))
        future = time.time() + 10
        os.utime(self.directory / 'credentials.json', (future, future))
        self.assertEqual(relay_target(self.card)[1:], (self.thread, 'ready'))

    def test_missing_credentials_never_auto_requests_qr(self):
        (self.directory / 'credentials.json').unlink()
        self.assertEqual(relay_target(self.card)[1:], (None, 'login_required'))

    def test_missing_state_and_invalid_thread_do_not_spawn(self):
        save_json(self.card / 'activity-source.json', dict(thread_id='invalid'))
        with self.assertRaises(ValueError):
            relay_target(self.card)

    def test_launch_agent_has_restart_and_no_credentials_or_permission_changes(self):
        spec = importlib.util.spec_from_file_location('resident_plist', Path(__file__).parents[1] / 'desktop/resident-plist.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        result = module.configuration('/Applications/Test App.app', '/tmp/card directory')
        self.assertTrue(result['RunAtLoad'])
        self.assertTrue(result['KeepAlive'])
        self.assertEqual(result['ThrottleInterval'], 30)
        self.assertEqual(result['ProgramArguments'][-1], '/tmp/card directory')
        self.assertNotIn('token', str(result))
        self.assertNotIn('credentials', str(result))
        with self.assertRaises(ValueError):
            module.configuration('relative', '/tmp/card')

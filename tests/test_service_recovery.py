import os
from pathlib import Path
import signal
import subprocess
import tempfile
import threading
import time
import unittest
import uuid
from unittest.mock import patch

from agent_progress_wechat.files import read_json, save_json
from agent_progress_wechat import relay, resident, worker_watchdog
from agent_progress_wechat.relay_service import run_relay
from test_all_message_recovery import incoming


class ServiceRecoveryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.card, self.state = self.root / 'card', self.root / 'wechat'
        self.thread = str(uuid.uuid4())
        save_json(self.card / 'activity-source.json', {'thread_id': self.thread})
        save_json(self.card / 'wechat-source.json', {'version': 1, 'directory': str(self.state)})
        save_json(self.state / 'connection.json', {'mode': 'current_session', 'thread_id': self.thread, 'status': 'stopped'})
        save_json(self.state / 'credentials.json', {'owner': 'owner', 'token': 'synthetic', 'base_url': 'https://ilinkai.weixin.qq.com'})

    def test_startup_keeps_owner_transport_without_backend_open_or_new_login(self):
        argv = ['relay', '--state-dir', str(self.state), '--thread-id', self.thread, '--card-dir', str(self.card), '--socket', str(self.root / 'missing')]
        old_mask = os.umask(0o077)
        handlers = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)}
        def started(*args):
            args[5].set()
        try:
            with patch('sys.argv', argv), patch.object(relay, 'run_relay', side_effect=started) as run, \
                 patch.object(relay, 'CurrentSession', side_effect=AssertionError('must not bootstrap backend')), \
                 patch.object(relay, 'login', side_effect=AssertionError('must retain existing login')):
                relay.main()
            self.assertEqual(run.call_count, 1)
            self.assertEqual(run.call_args.args[2], self.thread)
        finally:
            os.umask(old_mask)
            for sig, handler in handlers.items(): signal.signal(sig, handler)

    def test_phone_can_query_when_backend_is_down(self):
        stop = threading.Event()
        replies = []
        class OfflineSession:
            thread_id = self.thread
            def __init__(self, *args): pass
            def open(self): raise OSError('synthetic backend unavailable')
        class OnlineWeChat:
            def __init__(self, *args): self.first = True
            def updates(self, cursor):
                if self.first:
                    self.first = False
                    return incoming('diagnostics', '诊断')
                stop.wait(.05)
                return {'msgs': []}
            def send(self, text, *args):
                replies.append(text)
                if '手机链路诊断' in text: stop.set()
        timeout = threading.Timer(5, stop.set)
        timeout.start()
        try:
            with patch('agent_progress_wechat.relay_service.CurrentSession', OfflineSession), \
                 patch('agent_progress_wechat.relay_service.Client', OnlineWeChat):
                run_relay(self.state, {'owner': 'owner'}, self.thread, self.root / 'missing', self.card, stop, False)
        finally:
            timeout.cancel()
        self.assertTrue(any('手机链路诊断' in text for text in replies), replies)
        self.assertFalse(any('synthetic backend unavailable' in text for text in replies))

    def test_status_message_excludes_internal_waiting_marker(self):
        stop = threading.Event()
        inspected = []
        class Session:
            thread_id = self.thread
            def __init__(self, *args): pass
            def open(self): return self
            def inspect(self, connection):
                inspected.append(True)
                return {'status': {'activeFlags': ['waitingOnApproval']}}
            def close(self): pass
        class WeChat:
            def __init__(self, *args): pass
            def updates(self, cursor):
                stop.wait(.1)
                return {'msgs': []}
            def send(self, *args): raise AssertionError('No outbound context')
        timer = threading.Timer(.3, stop.set)
        timer.start()
        try:
            with patch('agent_progress_wechat.relay_service.CurrentSession', Session), \
                 patch('agent_progress_wechat.relay_service.Client', WeChat):
                run_relay(self.state, {'owner': 'owner'}, self.thread, self.root / 'missing', self.card, stop, False)
        finally:
            timer.cancel()
        message = read_json(self.state / 'connection.json')['message']
        self.assertTrue(inspected)
        self.assertIn('当前任务等待', message)
        self.assertNotIn('；1', message)

    def test_watchdog_only_accepts_fresh_owned_child_heartbeat(self):
        now = time.time()
        self.assertFalse(worker_watchdog.unresponsive(self.state, self.thread, 123, now - 10, now))
        self.assertTrue(worker_watchdog.unresponsive(self.state, self.thread, 123, now - 200, now))
        save_json(self.state / 'service-heartbeat.json', {'pid': 123, 'thread_id': self.thread, 'written_at': now, 'stalled': []})
        self.assertFalse(worker_watchdog.unresponsive(self.state, self.thread, 123, now - 200, now))
        self.assertTrue(worker_watchdog.unresponsive(self.state, 'other', 123, now - 200, now))
        self.assertTrue(worker_watchdog.unresponsive(self.state, self.thread, 456, now - 200, now))
        self.assertTrue(worker_watchdog.publish(self.state, self.thread, {'main': 121, 'poller': 0}))
        self.assertFalse(worker_watchdog.publish(self.state, self.thread, {'main': 500}, grace_until=now + 20))

    def test_supervisor_stops_its_hung_child_and_checks_binding_before_restart(self):
        class Stop:
            stopped = False
            def is_set(self): return self.stopped
            def wait(self, seconds):
                if seconds == 15: self.stopped = True
                return self.stopped
        stop = Stop()
        class Child:
            pid, ended, terminated, killed = 123, False, False, False
            def poll(self): return 0 if self.ended else None
            def terminate(self): self.terminated = True
            def wait(self, timeout):
                if not self.killed: raise subprocess.TimeoutExpired('owned-child', timeout)
                self.ended = True
            def kill(self): self.killed = True
        child = Child()
        with patch.object(resident.time, 'time', side_effect=[1000, 1000, 1001]), \
             patch.object(resident, 'relay_target', return_value=(self.state, self.thread, 'ready')), \
             patch.object(worker_watchdog, 'unresponsive', return_value=True) as check:
            resident.supervise(self.card, stop, lambda *a, **k: child)
        self.assertTrue(child.terminated)
        self.assertTrue(child.killed)
        check.assert_called_once()

    def test_sleep_jump_gets_grace_instead_of_immediate_restart(self):
        class Stop:
            calls = 0
            def is_set(self): return self.calls >= 2
            def wait(self, seconds):
                self.calls += 1
                return self.calls >= 2
        stop = Stop()
        class Child:
            pid, ended = 123, False
            def poll(self): return 0 if self.ended else None
            def terminate(self): self.ended = True
            def wait(self, timeout): return 0
        with patch.object(resident.time, 'time', side_effect=[1000, 1000, 1400]), \
             patch.object(resident, 'relay_target', return_value=(self.state, self.thread, 'ready')), \
             patch.object(worker_watchdog, 'unresponsive') as check:
            resident.supervise(self.card, stop, lambda *a, **k: Child())
        check.assert_not_called()

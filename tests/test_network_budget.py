import json
import subprocess
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_progress_wechat.ilink import BASE_URL, LinkError, request
from agent_progress_wechat import network_budget


class NetworkBudgetTests(unittest.TestCase):
    def result(self, value):
        return subprocess.CompletedProcess([], 0, json.dumps(value).encode())

    def test_credentials_use_stdin_and_error_flags_survive_process_boundary(self):
        packet = {'ok': False, 'error': {'message': '微信接口错误：-2', 'expired': False, 'stale_context': True}}
        with patch.object(network_budget.subprocess, 'run', return_value=self.result(packet)) as worker:
            with self.assertRaises(LinkError) as failure:
                request(BASE_URL, 'sendmessage', {'msg': 'synthetic'}, token='private-credential')
        self.assertTrue(failure.exception.stale_context)
        self.assertFalse(failure.exception.expired)
        argv = worker.call_args.args[0]
        self.assertNotIn('private-credential', ' '.join(argv))
        self.assertIn('private-credential', worker.call_args.kwargs['input'].decode())
        self.assertEqual(worker.call_args.kwargs['timeout'], 20)
        self.assertFalse(worker.call_args.kwargs.get('shell', False))

    def test_actual_hanging_worker_is_killed_and_reaped_at_deadline(self):
        real_popen = subprocess.Popen
        children = []
        def fake_worker(*args, **kwargs):
            child = real_popen([sys.executable, '-c', 'import time;time.sleep(30)'], **kwargs)
            children.append(child)
            return child
        started = time.monotonic()
        # Only substitute the child fixture and shorten its budget, retaining run's kill/wait logic.
        real_run = subprocess.run
        def short_run(*args, **kwargs):
            kwargs['timeout'] = .1
            return real_run(*args, **kwargs)
        with patch.object(network_budget.subprocess, 'run', side_effect=short_run), \
             patch.object(subprocess, 'Popen', side_effect=fake_worker):
            with self.assertRaisesRegex(LinkError, '总时限'):
                request(BASE_URL, 'getupdates', token='synthetic')
        self.assertLess(time.monotonic() - started, 2)
        self.assertEqual(len(children), 1)
        self.assertIsNotNone(children[0].poll())

    def test_invalid_worker_packets_and_timeout_are_safe(self):
        for packet in ({'ok': True, 'value': []}, {'error': {}}, {'error': {'expired': 1, 'stale_context': False, 'message': 'x'}}):
            with self.subTest(packet=packet), patch.object(network_budget.subprocess, 'run', return_value=self.result(packet)):
                with self.assertRaisesRegex(LinkError, '工作进程异常'):
                    request(BASE_URL, 'getupdates')
        for timeout in (True, 0, float('nan'), 100):
            with self.subTest(timeout=timeout), patch.object(network_budget.subprocess, 'run') as worker:
                with self.assertRaises(LinkError):
                    request(BASE_URL, 'getupdates', timeout=timeout)
                worker.assert_not_called()

    def test_real_worker_bootstrap_and_invalid_input_do_not_touch_network(self):
        bootstrap = "import runpy,sys;sys.path.insert(0,sys.argv[1]);runpy.run_module('agent_progress_wechat.network_worker',run_name='__main__')"
        source = str(Path(network_budget.__file__).resolve().parents[1])
        result = subprocess.run([sys.executable, '-I', '-B', '-c', bootstrap, source], input=b'{}',
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=3)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, b'')
        self.assertEqual(json.loads(result.stdout)['error']['message'], '微信网络工作进程异常')

    def test_success_and_expired_auth_do_not_change_meaning(self):
        packets = [({'ok': True, 'value': {'msgs': []}}, False),
                   ({'ok': False, 'error': {'expired': True, 'stale_context': False, 'message': '微信接口错误：-14'}}, True)]
        for packet, expired in packets:
            with patch.object(network_budget.subprocess, 'run', return_value=self.result(packet)) as worker:
                if expired:
                    with self.assertRaises(LinkError) as failure:
                        request(BASE_URL, 'getupdates')
                    self.assertTrue(failure.exception.expired)
                else:
                    self.assertEqual(request(BASE_URL, 'getupdates'), {'msgs': []})
                self.assertEqual(worker.call_args.kwargs['timeout'], 40)

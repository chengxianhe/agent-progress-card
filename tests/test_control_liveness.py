import socket
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from agent_progress_wechat.local_socket import LocalSocket, TransportError
from agent_progress_wechat.approval_service import run_approvals


class ControlLivenessTests(unittest.TestCase):
    def test_frame_drip_cannot_extend_the_total_deadline(self):
        left, right = socket.socketpair()
        client = LocalSocket.__new__(LocalSocket)
        client.socket = left
        def drip():
            try:
                for byte in b'\x81\x05hello':
                    right.sendall(bytes([byte])); time.sleep(.025)
            except OSError:
                pass
            finally:
                right.close()
        thread = threading.Thread(target=drip)
        thread.start()
        started = time.monotonic()
        try:
            with self.assertRaises((TimeoutError, TransportError)):
                client._receive(started + .08)
            self.assertLess(time.monotonic() - started, .4)
        finally:
            left.close(); thread.join(timeout=2)

    def test_continuous_events_still_service_pending_decisions_and_expiry(self):
        stop = threading.Event()
        sent = []
        expired = []
        class Connection:
            events = []
            socket = object()
            def __init__(self, path): self.reads = 0
            def subscribe(self, session): pass
            def _receive(self, deadline):
                self.reads += 1
                if self.reads > 5: stop.set()
                return {'method': 'serverRequest/resolved', 'params': {}}
            def respond(self, *reply): sent.append(reply); stop.set()
            def close(self): pass
        state = SimpleNamespace(event=lambda *args: None, expire=lambda: expired.append(True),
                                claim=lambda connection: (17, 'accept'), invalidate=lambda connection: None)
        session = SimpleNamespace(socket_path='unused', thread_id='thread')
        with patch('agent_progress_wechat.approval_service.ApprovalConnection', Connection), \
             patch('agent_progress_wechat.approval_service.check_binding'), \
             patch('agent_progress_wechat.approval_service.select.select', return_value=([1], [], [])):
            run_approvals(None, session, None, stop, lambda *args: None, state)
        self.assertTrue(expired)
        self.assertEqual(sent, [(17, 'accept')])


if __name__ == '__main__': unittest.main()

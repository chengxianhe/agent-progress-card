import tempfile
import time
import unittest
from pathlib import Path

from agent_progress_wechat.relay_store import RelayStore


class DeliveryRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.store = RelayStore(Path(self.folder.name), 'owner', 'thread', since=1)
        self.addCleanup(self.store.db.close)
        self.store.put('context', 'synthetic-context')
        self.store.put('context_at', time.time() - 3600)
        with self.store.lock, self.store.db:
            self.store.enqueue('note:reply', 'Synthetic reply')

    def test_age_alone_does_not_block_send(self):
        self.assertEqual('note:reply', self.store.outgoing()['id'])

    def test_server_expiry_blocks_until_new_inbound_context(self):
        self.store.put('send_paused_until', time.time() + 300)
        self.assertIsNone(self.store.outgoing())
        self.ingest()
        self.assertEqual('note:reply', self.store.outgoing()['id'])

    def test_exhausted_legacy_notification_recovers_after_due_time(self):
        self.store.db.execute('UPDATE outbox SET attempts=5,due=0')
        self.store.db.commit()
        self.assertEqual('note:reply', self.store.outgoing()['id'])

    def test_retry_is_delayed_and_capped_not_a_busy_loop(self):
        for _ in range(20):
            self.store.sent('note:reply', False)
        row = self.store.db.execute('SELECT attempts,due FROM outbox').fetchone()
        self.assertEqual(20, row['attempts'])
        self.assertGreater(row['due'], time.time() + 29)
        self.assertLessEqual(row['due'], time.time() + 300)
        self.assertIsNone(self.store.outgoing())
        self.ingest()
        self.assertIsNotNone(self.store.outgoing())

    def test_delivered_and_uncertain_input_not_replayed_on_context_refresh(self):
        self.store.sent('note:reply', True)
        self.ingest()
        self.store.mark('inbound', 'uncertain')
        self.ingest('next')
        self.assertIsNone(self.store.outgoing())
        row = self.store.db.execute("SELECT status FROM inbox WHERE id='inbound'").fetchone()
        self.assertEqual('uncertain', row[0])

    def ingest(self, identity='inbound'):
        self.store.ingest({'msgs': [{'from_user_id': 'owner', 'message_type': 1,
            'message_id': identity, 'context_token': 'synthetic-fresh', 'create_time_ms': time.time()*1000,
            'item_list': [{'type': 1, 'text_item': {'text': '进度'}}]}]})


class NotificationTransportTests(unittest.TestCase):
    def test_stale_response_cannot_invalidate_newer_context(self):
        from agent_progress_wechat.notification_delivery import send_outgoing
        from agent_progress_wechat.ilink import LinkError
        with tempfile.TemporaryDirectory() as d:
            store = RelayStore(Path(d), 'owner', 'thread', since=1)
            self.addCleanup(store.db.close)
            store.put('context', 'old'); store.put('context_at', 1)
            with store.lock, store.db:
                store.enqueue('note:reply', 'reply')
            class Client:
                def send(self, text, context, identity):
                    assert context == 'old'
                    store.put('context', 'new'); store.put('context_at', 2)
                    raise LinkError('expired', stale_context=True)
            with self.assertRaises(LinkError):
                send_outgoing(store, Client())
            self.assertEqual('2', store.get('context_at'))
            self.assertEqual(0, store.outgoing()['attempts'])

    def test_transport_retry_reuses_identity_and_marks_only_success_delivered(self):
        from agent_progress_wechat.notification_delivery import send_outgoing
        from agent_progress_wechat.ilink import LinkError
        with tempfile.TemporaryDirectory() as d:
            store = RelayStore(Path(d), 'owner', 'thread', since=1)
            self.addCleanup(store.db.close)
            store.put('context', 'synthetic'); store.put('context_at', 1)
            with store.lock, store.db:
                store.enqueue('note:reply', 'reply')
            calls = []
            class Client:
                def send(self, text, context, identity):
                    calls.append(identity)
                    if len(calls) == 1:
                        raise LinkError('offline')
            with self.assertRaises(LinkError): send_outgoing(store, Client())
            self.assertEqual(1, store.summary()['unsent'])
            self.assertFalse(send_outgoing(store, Client()))
            with store.lock, store.db: store.db.execute('UPDATE outbox SET due=0')
            self.assertFalse(send_outgoing(store, Client()))
            store.ingest({'msgs': [{'from_user_id': 'owner', 'message_type': 1,
                'message_id': 'fresh', 'context_token': 'new-context', 'create_time_ms': time.time()*1000,
                'item_list': [{'type': 1, 'text_item': {'text': '进度'}}]}]})
            self.assertTrue(send_outgoing(store, Client()))
            self.assertEqual(calls[0], calls[1])
            self.assertEqual(0, store.summary()['unsent'])


class SendPauseRecoveryTests(unittest.TestCase):
    def test_rejection_waits_for_new_input_instead_of_probing_old_context(self):
        from unittest.mock import patch
        from agent_progress_wechat.notification_delivery import send_outgoing
        from agent_progress_wechat.ilink import LinkError
        with tempfile.TemporaryDirectory() as d:
            store = RelayStore(Path(d), 'owner', 'thread', since=1)
            self.addCleanup(store.db.close)
            store.put('context', 'synthetic'); store.put('context_at', 0)
            with store.lock, store.db: store.enqueue('note:old', 'reply')
            class Client:
                def send(self, *args): raise LinkError('rejected', stale_context=True)
            with self.assertRaises(LinkError): send_outgoing(store, Client())
            with store.lock, store.db: store.enqueue('note:new', 'new reply')
            self.assertIsNone(store.outgoing())
            future = time.time() + 301
            with patch('time.time', return_value=future):
                self.assertIsNone(store.outgoing())
            store.ingest({'msgs': [{'from_user_id': 'owner', 'message_type': 1,
                'message_id': 'fresh', 'context_token': 'new-context', 'create_time_ms': time.time()*1000,
                'item_list': [{'type': 1, 'text_item': {'text': '进度'}}]}]})
            self.assertEqual(store.outgoing()['id'], 'note:new')

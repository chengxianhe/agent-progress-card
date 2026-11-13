import json
import tempfile
import time
import unittest
from pathlib import Path

from agent_progress_wechat import delivery_policy
from agent_progress_wechat.approval_state import ApprovalState
from agent_progress_wechat.notification_delivery import send_outgoing
from agent_progress_wechat.ilink import LinkError
from agent_progress_wechat.relay_mirror import mirror
from agent_progress_wechat.relay_store import RelayStore
from agent_progress_wechat.inbound_dispatch import take, release
from test_remote_approvals import approval


def incoming(identity='fresh', text='进度', owner='owner'):
    return {'msgs': [{'message_id': identity, 'from_user_id': owner, 'message_type': 1,
                     'context_token': 'synthetic-' + identity, 'create_time_ms': time.time()*1000,
                     'item_list': [{'type': 1, 'text_item': {'text': text}}]}]}


class AllMessageRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.store = RelayStore(self.root, 'owner', 'thread', since=1)
        self.store.put('context', 'synthetic')
        self.addCleanup(lambda: self.store.db.close())

    def test_failure_drops_every_category_and_paused_burst_has_no_payload_backlog(self):
        prefixes = ['note:', 'card:', 'delivered:', 'approval:A:part:', 'approval-result:',
                    'choice:', 'prompt:', 'uncertain:', 'reject:', 'local:', 'notice:', 'unknown:']
        for prefix in prefixes:
            self.store.enqueue(prefix + 'before', 'old notification')
        class Offline:
            def send(self, *args): raise LinkError('offline')
        with self.assertRaises(LinkError):
            send_outgoing(self.store, Offline())
        for index in range(100):
            for prefix in prefixes:
                self.store.enqueue(prefix + str(index), 'must not pile up')
        self.assertEqual(self.store.summary()['unsent'], 0)
        self.assertIsNone(self.store.outgoing())
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM outbox WHERE text!=''").fetchone()[0], 0)
        self.assertEqual(self.store.db.execute('SELECT sum(delivered) FROM outbox').fetchone()[0], 0)

    def test_reconnect_produces_one_current_summary_and_does_not_replay_any_old_feed(self):
        before = time.time()
        self.store.put('send_requires_context', '1')
        self.store.enqueue('approval:old', 'old approval')
        self.store.ingest(incoming())
        state = {'title': 'Current task', 'task_id': 'task', 'updated_at': before}
        feed = {'choice': {'id': 'choice-old', 'created_at': before, 'question': 'old', 'options': ['a', 'b']},
                'notes': [{'id': 'old-final', 'kind': 'final', 'time': before, 'text': 'old result'}],
                'question_notices': [{'id': 'native:old', 'time': before, 'text': 'old question'}]}
        for _ in range(3):
            mirror(self.store, state, feed)
        rows = self.store.db.execute('SELECT * FROM outbox WHERE delivered=0 AND superseded=0').fetchall()
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]['id'].startswith('recovery:'))
        self.assertIn('Current task', rows[0]['text'])
        self.assertNotIn('old result', rows[0]['text'])
        self.assertNotIn('old approval', rows[0]['text'])

    def test_pause_and_discard_survive_restart_without_touching_inbound_or_approval_state(self):
        state = ApprovalState(self.store, 'thread')
        self.store.ingest(incoming('task', 'task request'))
        state.event(approval(), 'conn')
        self.store.put('send_requires_context', '1')
        self.store.db.close()
        self.store = RelayStore(self.root, 'owner', 'thread')
        self.assertEqual(self.store.summary()['unsent'], 0)
        self.assertEqual(self.store.db.execute("SELECT status FROM inbox WHERE id='task'").fetchone()[0], 'queued')
        self.assertEqual(self.store.db.execute('SELECT state FROM remote_approvals').fetchone()[0], 'pending')
        self.store.ingest(incoming('foreign', owner='stranger'))
        self.assertTrue(self.store.summary()['send_paused'])

    def test_query_is_a_bounded_index_not_a_replay_of_all_active_requests(self):
        state = ApprovalState(self.store, 'thread')
        self.store.put('send_requires_context', '1')
        for index in range(12): state.event(approval(index), 'conn')
        self.store.ingest(incoming('query', '审批'))
        state.handle(self.store.next_message())
        rows = self.store.db.execute('SELECT * FROM outbox WHERE superseded=0 AND delivered=0').fetchall()
        self.assertEqual(len(rows), 1)
        self.assertIn('当前 12 项请求', rows[0]['text'])
        self.assertEqual(rows[0]['text'].count('item/commandExecution/requestApproval'), 5)
        code = self.store.db.execute('SELECT code FROM remote_approvals LIMIT 1').fetchone()[0]
        self.store.sent(rows[0]['id'], True)
        self.store.ingest(incoming('detail', '审批 ' + code))
        state.handle(self.store.next_message())
        pending = self.store.db.execute('SELECT * FROM outbox WHERE superseded=0 AND delivered=0').fetchall()
        self.assertEqual(len(pending), 1)
        self.assertIn('printf hello', pending[0]['text'])
        self.assertIn('1. 仅此次允许', pending[0]['text'])

    def test_late_ack_cannot_mark_a_refreshed_notification_sent(self):
        state = ApprovalState(self.store, 'thread')
        state.event(approval(), 'conn')
        row = self.store.outgoing()
        code = self.store.db.execute('SELECT code FROM remote_approvals').fetchone()[0]
        self.store.ingest(incoming('detail', '审批 ' + code))
        state.handle(self.store.next_message())
        self.store.sent(row['id'], True, row['revision'])
        latest = self.store.db.execute('SELECT * FROM outbox WHERE id=?', (row['id'],)).fetchone()
        self.assertEqual(latest['delivered'], 0)
        self.assertGreater(latest['revision'], row['revision'])

    def test_ordinary_capacity_cannot_reject_or_block_control_commands(self):
        for i in range(20): self.store.ingest(incoming(str(i), 'ordinary task ' + str(i)))
        self.store.ingest(incoming('status', '进度'))
        self.assertEqual(take(self.store, True)['id'], 'status')
        ordinary = take(self.store, False)
        self.assertEqual(ordinary['id'], '0')
        self.store.ingest(incoming('approval-query', '审批'))
        self.assertEqual(take(self.store, True)['id'], 'approval-query')
        release(self.store, ordinary)
        self.assertEqual(self.store.db.execute("SELECT status FROM inbox WHERE id='0'").fetchone()[0], 'queued')
        self.store.ingest(incoming('card-selection', '1 C0123456789'))
        self.assertEqual(take(self.store, False)['id'], 'card-selection')

    def test_repeated_suppressed_identity_cannot_revive_after_resume(self):
        self.store.put('send_requires_context', '1')
        self.store.enqueue('notice:old', 'old')
        self.store.ingest(incoming())
        self.store.enqueue('notice:old', 'old again')
        self.assertEqual(self.store.summary()['unsent'], 0)

    def test_restart_with_cached_online_context_drops_all_old_notices(self):
        self.store.enqueue('notice:old', 'stale cached context')
        self.store.db.commit()
        self.store.db.close()
        self.store = RelayStore(self.root, 'owner', 'thread')
        self.assertTrue(self.store.summary()['send_paused'])
        self.assertIsNone(self.store.outgoing())
        self.assertEqual(self.store.summary()['unsent'], 0)

    def test_previously_delivered_notifications_remain_delivered_and_are_not_resent(self):
        self.store.enqueue('notice:sent', 'already sent')
        self.store.sent('notice:sent', True)
        self.store.put('send_requires_context', '1')
        self.store.ingest(incoming())
        row = self.store.db.execute("SELECT * FROM outbox WHERE id='notice:sent'").fetchone()
        self.assertEqual((row['delivered'], row['superseded']), (1, 0))


if __name__ == '__main__': unittest.main()

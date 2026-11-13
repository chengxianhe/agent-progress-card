"""Fault cases where an owner is away from the computer."""
import tempfile
import time
import unittest
from pathlib import Path

from agent_progress_card.choice import create_choice, read_choice
from agent_progress_wechat.approval_state import ApprovalState
from agent_progress_wechat import approval_notice, choice_notice
from agent_progress_wechat.current_session import CurrentSession
from agent_progress_wechat.files import save_json
from agent_progress_wechat.relay_service import deliver
from agent_progress_wechat.relay_store import RelayStore
from agent_progress_wechat.remote_health import describe
from test_all_message_recovery import incoming
from test_remote_approvals import approval


class OutsideRecoveryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.store = RelayStore(self.root, 'owner', 'thread', since=1)
        self.addCleanup(self.store.db.close)
        self.store.put('context', 'synthetic')
        self.state = ApprovalState(self.store, 'thread')
        save_json(self.root / 'activity-source.json', {'thread_id': 'thread'})

    def row(self):
        return self.store.db.execute('SELECT * FROM remote_approvals').fetchone()

    def message(self, text, identity=None):
        self.store.ingest(incoming(identity or str(time.time_ns()), text))
        return self.store.next_message()

    def test_explicit_refresh_cannot_recreate_offline_payloads(self):
        self.state.event(approval(), 'conn')
        create_choice(self.root, '完整问题', ['甲', '乙'])
        choice = read_choice(self.root, 'thread')
        # Both previously delivered and never-delivered rows must remain suppressed.
        for delivered in (False, True):
            self.store.put('send_requires_context', '0')
            choice_notice.publish(self.store, choice)
            if delivered:
                self.store.db.execute('UPDATE outbox SET delivered=1')
            self.store.put('send_requires_context', '1')
            before = list(map(tuple, self.store.db.execute('SELECT * FROM outbox')))
            approval_notice.publish(self.store, self.row(), refresh=True)
            choice_notice.publish(self.store, choice, refresh=True)
            self.assertEqual(before, list(map(tuple, self.store.db.execute('SELECT * FROM outbox'))))
            self.assertEqual(self.store.summary()['unsent'], 0)

    def test_expired_live_request_gets_new_code_only_after_query(self):
        self.state.event(approval(), 'conn')
        old = self.row()['code']
        self.store.db.execute('UPDATE remote_approvals SET expires=0')
        self.state.expire()
        self.assertEqual(self.row()['code'], old)
        self.assertIsNone(self.state.claim('conn'))
        self.state.handle(self.message('审批'))
        new = self.row()['code']
        self.assertNotEqual(new, old)
        self.assertEqual(self.row()['state'], 'pending')
        self.assertIsNone(self.state.claim('conn'))
        self.state.handle(self.message('1 ' + old))
        self.assertIsNone(self.state.claim('conn'))
        # Even a fresh code cannot authorize a message sent before the code existed.
        early = self.message('1 ' + new)
        early['created'] = 0
        self.state.handle(early)
        self.assertIsNone(self.state.claim('conn'))
        self.state.handle(self.message('1 ' + new))
        self.assertEqual(self.state.claim('conn'), (17, 'accept'))

    def test_resolution_closes_expired_and_renewed_codes(self):
        for renew in (False, True):
            self.state.event(approval(int(renew)), 'conn')
            self.store.db.execute("UPDATE remote_approvals SET expires=0 WHERE state='pending'")
            self.state.expire()
            if renew:
                self.state.handle(self.message('审批'))
            self.state.event({'method': 'serverRequest/resolved', 'params': {'threadId': 'thread', 'requestId': int(renew)}}, 'conn')
            self.state.handle(self.message('审批'))
            rows = self.store.db.execute('SELECT state,server_live FROM remote_approvals').fetchall()
            self.assertTrue(all(tuple(r) == ('resolved', 0) for r in rows))
            self.assertIsNone(self.state.claim('conn'))

    def test_disconnected_or_uncertain_request_is_never_renewed(self):
        for identity in (1, 2):
            self.state.event(approval(identity), 'conn')
        rows = self.store.db.execute('SELECT * FROM remote_approvals').fetchall()
        self.state.handle(self.message('1 ' + rows[0]['code']))
        self.state.claim('conn')
        self.store.db.execute('UPDATE remote_approvals SET expires=0')
        self.state.expire()
        self.state.invalidate('conn')
        self.state.handle(self.message('审批'))
        after = self.store.db.execute('SELECT * FROM remote_approvals').fetchall()
        self.assertEqual([r['code'] for r in rows], [r['code'] for r in after])
        self.assertEqual([r['state'] for r in after], ['uncertain', 'expired'])
        self.assertTrue(all(not r['server_live'] for r in after))

    def test_phone_diagnostics_never_calls_backend_and_exposes_missing_evidence(self):
        # No snapshot or backend connection is available, but this local command works.
        msg = self.message('出门检查')
        session = CurrentSession('does-not-exist', 'thread')
        deliver(self.store, session, msg, self.root, self.state,
                lambda compact=False: describe(self.store, self.root, {'codex': '任务会话不可用'}))
        reply = self.store.db.execute('SELECT text FROM outbox WHERE id=?', ('local:' + msg['id'],)).fetchone()
        if reply is None:
            replies = '\n'.join(r[0] for r in self.store.db.execute('SELECT text FROM outbox'))
        else:
            replies = reply[0]
        self.assertIn('任务会话不可用', replies)
        self.assertIn('采集心跳', replies)
        self.assertIn('不能承诺自动重启', replies)
        self.assertNotIn(str(self.root), replies)

    def test_diagnostics_distinguishes_pending_backend_without_mobile_request(self):
        text = describe(self.store, self.root, {'approval_waiting': '1'})
        self.assertIn('手机没有收到可用请求', text)
        self.assertIn('不能补造请求', text)
        self.state.event(approval(), 'conn')
        self.store.db.execute('UPDATE remote_approvals SET expires=0')
        self.state.expire()
        text = describe(self.store, self.root, {'approval_waiting': '1'})
        self.assertNotIn('手机没有收到可用请求', text)
        self.assertIn('发送“审批”刷新编号', text)

    def test_supervision_requires_fresh_matching_child_evidence(self):
        save_json(self.root / 'activity-heartbeat.json', {'thread_id': 'thread', 'checked_at': time.time()})
        save_json(self.root / 'service-heartbeat.json', {'pid': 123})
        save_json(self.root / 'resident.json', {'status': 'running', 'child_pid': 123, 'checked_at': time.time()})
        self.assertEqual(describe(self.store, self.root, {}, compact=True), '')
        save_json(self.root / 'resident.json', {'status': 'running', 'child_pid': 999, 'checked_at': time.time()})
        self.assertIn('不能承诺自动重启', describe(self.store, self.root, {}, compact=True))

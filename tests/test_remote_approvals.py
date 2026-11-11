import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from agent_progress_wechat.approval_prompt import display, parse_reply
from agent_progress_wechat.approval_state import ApprovalState
from agent_progress_wechat.approval_transport import ApprovalConnection
from agent_progress_wechat.current_session import CurrentSession, SessionUnavailable
from agent_progress_wechat.relay_service import deliver
from agent_progress_wechat.relay_store import RelayStore
from agent_progress_wechat.files import save_json
from agent_progress_card.choice import create_choice


def approval(identity=17, **changes):
    params = dict(threadId='thread', turnId='turn', itemId='item', kind='humanCommand',
                  command='printf hello', cwd='/tmp', reason='测试', availableDecisions=['accept', 'decline'])
    params.update(changes)
    return dict(id=identity, method='item/commandExecution/requestApproval', params=params)


class ApprovalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)
        self.store = RelayStore(self.path, 'owner', 'thread', since=1)
        self.state = ApprovalState(self.store, 'thread')
        save_json(self.path / 'activity-source.json', {'thread_id': 'thread'})

    def tearDown(self):
        self.store.db.close()
        self.temp.cleanup()

    def rows(self):
        return self.store.db.execute('SELECT * FROM remote_approvals').fetchall()

    def inbound(self, text, identity='message', **changes):
        msg = dict(message_id=identity, from_user_id='owner', message_type=1, create_time_ms=time.time()*1000,
                   context_token='context', item_list=[dict(type=1, text_item=dict(text=text))])
        msg.update(changes)
        self.store.ingest(dict(msgs=[msg]))
        return self.store.next_message()

    def resolve(self, identity=17, thread='thread'):
        self.state.event(dict(method='serverRequest/resolved', params=dict(threadId=thread, requestId=identity)), 'conn')

    def test_no_decision_without_explicit_owner_reply(self):
        self.state.event(approval(), 'conn')
        self.assertIsNone(self.state.claim('conn'))
        code = self.rows()[0]['code']
        self.assertIsNone(self.inbound('批准 ' + code, from_user_id='stranger'))
        self.assertIsNone(self.inbound('批准 ' + code, group_id='group'))
        self.assertIsNone(self.state.claim('conn'))

    def test_one_time_reply_and_repeated_messages(self):
        self.state.event(approval(), 'conn')
        self.state.event(approval(), 'conn')
        self.assertEqual(len(self.rows()), 1)
        code = self.rows()[0]['code']
        notice = self.store.db.execute('SELECT text FROM outbox WHERE id=?', ('approval:' + code,)).fetchone()[0]
        self.assertIn('命令：\nprintf hello', notice)
        self.assertIn('目录：/tmp', notice)
        self.assertIn('原因：测试', notice)
        self.assertIn('1. 仅此次允许', notice)
        self.assertLess(len(notice), 180)
        message = self.inbound('批准 ' + code)
        deliver(self.store, CurrentSession('unused', 'thread'), message, self.path, self.state)
        self.assertEqual(self.state.claim('conn'), (17, 'accept'))
        self.assertIsNone(self.state.claim('conn'))
        self.state.handle(self.inbound('批准 ' + code, 'second'))
        self.assertIsNone(self.state.claim('conn'))
        self.resolve()
        self.assertEqual(self.rows()[0]['state'], 'resolved')
        self.assertEqual(self.store.db.execute("SELECT delivered FROM outbox WHERE id=?", ('approval:' + code,)).fetchone()[0], 1)

    def test_decline_and_no_session_or_persistent_grants(self):
        self.state.event(approval('abc'), 'conn')
        self.state.handle(self.inbound('拒绝 ' + self.rows()[0]['code']))
        self.assertEqual(self.state.claim('conn'), ('abc', 'decline'))
        client = ApprovalConnection.__new__(ApprovalConnection)
        sent = []
        client._send = sent.append
        for decision in ('acceptForSession', {'acceptWithExecpolicyAmendment': {}}):
            with self.assertRaises(ValueError):
                client.respond(17, decision)
        client.respond(17, 'decline')
        self.assertEqual(json.loads(sent[0]), {'id': 17, 'result': {'decision': 'decline'}})

    def test_desktop_resolves_before_owner_reply(self):
        self.state.event(approval(), 'conn')
        code = self.rows()[0]['code']
        self.resolve()
        self.state.handle(self.inbound('批准 ' + code))
        self.assertIsNone(self.state.claim('conn'))
        self.assertEqual(self.rows()[0]['state'], 'resolved')

    def test_desktop_resolves_after_queue_before_send(self):
        self.state.event(approval(), 'conn')
        self.state.handle(self.inbound('批准 ' + self.rows()[0]['code']))
        self.resolve()
        self.assertIsNone(self.state.claim('conn'))

    def test_foreign_thread_and_typed_request_ids(self):
        self.state.event(approval(threadId='other'), 'conn')
        self.assertFalse(self.rows())
        self.state.event(approval(17), 'conn')
        self.state.event(approval('17'), 'conn')
        self.assertEqual(len(self.rows()), 2)
        self.resolve(thread='other')
        self.assertTrue(all(r['state'] == 'pending' for r in self.rows()))
        self.resolve(17)
        self.assertEqual([r['state'] for r in self.rows()], ['resolved', 'pending'])

    def test_expired_old_and_wrong_connection_replies(self):
        self.state.event(approval(), 'conn')
        code = self.rows()[0]['code']
        self.store.db.execute('UPDATE remote_approvals SET expires=0')
        self.state.handle(self.inbound('批准 ' + code))
        self.assertIsNone(self.state.claim('conn'))
        self.assertEqual(self.rows()[0]['state'], 'expired')
        self.state.event(approval(18), 'conn')
        self.state.handle(self.inbound('批准 ' + self.rows()[1]['code'], 'new'))
        self.assertIsNone(self.state.claim('other-connection'))

    def test_disconnect_restart_never_resubmit_ambiguous_response(self):
        self.state.event(approval(), 'conn')
        self.state.handle(self.inbound('批准 ' + self.rows()[0]['code']))
        self.state.claim('conn')
        self.state.invalidate('conn')
        self.assertEqual(self.rows()[0]['state'], 'uncertain')
        fresh = ApprovalState(self.store, 'thread')
        self.assertIsNone(fresh.claim('conn'))
        fresh.event(approval(), 'new-conn')
        self.assertEqual(len(self.rows()), 2)
        self.assertNotEqual(self.rows()[0]['code'], self.rows()[1]['code'])

    def test_malformed_reply_consumed_locally_even_when_feature_disabled(self):
        for text in ('批准', '批准 1', '批准 A0000000000'):
            message = self.inbound(text, identity=text)
            deliver(self.store, CurrentSession('unused', 'thread'), message, self.path)
            self.assertIsNone(self.store.next_message())

    def test_sensitive_or_partial_permission_prompts_stay_native(self):
        variants = [dict(command='echo token=secret'), dict(command='x'*1401), dict(command='cat ~/.env'),
                    dict(networkApprovalContext={'host': 'test'}), dict(additionalPermissions={'network': True}),
                    dict(kind='writeStdin'), dict(command=None), dict(availableDecisions=['accept']), dict(cwd=None)]
        for idx, values in enumerate(variants):
            self.state.event(approval(idx, **values), 'conn')
        self.assertTrue(all(r['state'] == 'native' for r in self.rows()))
        self.assertIsNone(self.state.claim('conn'))
        notices = '\n'.join(r[0] for r in self.store.db.execute('SELECT text FROM outbox'))
        self.assertNotIn('token=secret', notices)
        self.assertNotIn('cat ~/.env', notices)

    def test_native_fallback_explains_limits_without_echoing_request(self):
        variants = [
            (dict(command='x' * 1401), '命令正文超过微信审批的 1400 字符展示上限'),
            (dict(cwd='x' * 301), '目录超过微信审批的 300 字符展示上限'),
            (dict(reason='x' * 401), '原因超过微信审批的 400 字符展示上限'),
            (dict(command='echo token=private-value'), '敏感内容'),
            (dict(additionalPermissions={'network': True}), '额外权限'),
            (dict(command=None), '缺少完整'),
            (dict(command='echo \x1b[31m'), '控制字符'),
            (dict(kind='writeStdin'), '这类操作'),
            (dict(availableDecisions=['accept']), '审批选项'),
        ]
        for identity, (changes, expected) in enumerate(variants):
            with self.subTest(expected=expected):
                self.state.event(approval(identity, **changes), 'conn')
                row = self.rows()[-1]
                notice = self.store.db.execute('SELECT text FROM outbox WHERE id=?',
                                              ('approval:' + row['code'],)).fetchone()[0]
                self.assertEqual(row['state'], 'native')
                self.assertIn(expected, notice)
                self.assertIn('不能回复数字授权', notice)
                self.assertNotIn('private-value', notice)
                self.assertNotIn('x' * 100, notice)
        self.assertIsNone(self.state.claim('conn'))
        self.assertIsNotNone(display(approval(command='x' * 1400)['params']))

    def test_approval_notification_precedes_progress_backlog(self):
        self.store.put('context', 'fresh')
        with self.store.lock, self.store.db:
            self.store.enqueue('notice:older', 'old progress')
        self.state.event(approval(), 'conn')
        self.assertTrue(self.store.outgoing()['id'].startswith('approval:'))

    def test_queued_reply_expires_on_restart(self):
        self.state.event(approval(), 'conn')
        self.state.handle(self.inbound('批准 ' + self.rows()[0]['code']))
        restarted = ApprovalState(self.store, 'thread')
        self.assertIsNone(restarted.claim('conn'))
        self.assertEqual(self.rows()[0]['state'], 'expired')

    def test_real_native_order_accept_persistent_cancel(self):
        offered = ['accept', {'acceptWithExecpolicyAmendment': {'execpolicy_amendment': ['printf', 'test']}}, 'cancel']
        self.state.event(approval(availableDecisions=offered), 'conn')
        row = self.rows()[0]
        self.assertEqual(row['state'], 'pending')
        choices = json.loads(row['choices'])
        self.assertEqual([c['decision'] for c in choices], ['accept', None, 'cancel'])
        self.assertIn('电脑端', choices[1]['label'])
        self.state.handle(self.inbound('2 ' + row['code']))
        self.assertIsNone(self.state.claim('conn'))
        self.state.handle(self.inbound('拒绝 ' + row['code'], 'no-implicit-cancel'))
        self.assertIsNone(self.state.claim('conn'))
        self.state.handle(self.inbound('3 ' + row['code'], 'cancel-explicitly'))
        self.assertEqual(self.state.claim('conn'), (17, 'cancel'))

    def test_bare_number_requires_unique_delivered_prompt(self):
        self.state.event(approval(), 'conn')
        row = self.rows()[0]
        self.state.handle(self.inbound('1'))
        self.assertIsNone(self.state.claim('conn'))
        self.store.sent('approval:' + row['code'], True)
        self.state.handle(self.inbound('1', 'after-delivery'))
        self.assertEqual(self.state.claim('conn'), (17, 'accept'))
        self.resolve()
        message = self.inbound('1', 'duplicate')
        deliver(self.store, CurrentSession('unused', 'thread'), message, self.path, self.state)
        self.assertIsNone(self.store.next_message())
        self.assertIsNone(self.state.claim('conn'))

    def test_bare_number_ambiguous_but_explicit_code_works(self):
        self.state.event(approval(1), 'conn')
        self.state.event(approval(2), 'conn')
        for r in self.rows():
            self.store.sent('approval:' + r['code'], True)
        self.state.handle(self.inbound('1'))
        self.assertIsNone(self.state.claim('conn'))
        self.state.handle(self.inbound('1 ' + self.rows()[1]['code'], 'explicit'))
        self.assertEqual(self.state.claim('conn'), (2, 'accept'))

    def test_bare_number_cannot_answer_normal_choice_and_approval_together(self):
        self.state.event(approval(), 'conn')
        self.store.sent('approval:' + self.rows()[0]['code'], True)
        create_choice(self.path, '普通问题', ['甲', '乙'])
        message = self.inbound('1')
        deliver(self.store, CurrentSession('unused', 'thread'), message, self.path, self.state)
        self.assertIsNone(self.state.claim('conn'))
        self.assertIsNone(self.store.next_message())

    def test_numeric_mapping_preserves_server_order(self):
        self.state.event(approval(availableDecisions=['cancel', 'accept']), 'conn')
        self.state.handle(self.inbound('2 ' + self.rows()[0]['code']))
        self.assertEqual(self.state.claim('conn'), (17, 'accept'))

    def test_cancel_response_is_exact(self):
        client = ApprovalConnection.__new__(ApprovalConnection)
        sent = []
        client._send = sent.append
        client.respond('request', 'cancel')
        self.assertEqual(json.loads(sent[0]), {'id': 'request', 'result': {'decision': 'cancel'}})

    def test_listing_and_reply_parser(self):
        self.state.event(approval(), 'conn')
        code = self.rows()[0]['code']
        self.state.handle(self.inbound('审批'))
        self.assertIsNone(self.state.claim('conn'))
        self.assertEqual(parse_reply('批准 ' + code.lower().replace('a','A',1)), (code, 'accept'))
        for invalid in ('1', '同意', '批准 ' + code + ' 后续都允许'):
            self.assertIsNone(parse_reply(invalid))


class TransportTests(unittest.TestCase):
    def test_resume_only_open_bound_thread_without_overrides(self):
        client = ApprovalConnection.__new__(ApprovalConnection)
        calls = []
        def call(method, params):
            calls.append((method, params))
            return dict(thread=dict(id='thread', canAcceptDirectInput=True, status=dict(type='active')))
        client.call = call
        client.subscribe(CurrentSession('unused', 'thread'))
        self.assertEqual(calls[1], ('thread/resume', {'threadId':'thread', 'excludeTurns':True}))
        client.call = lambda *_: dict(thread=dict(id='thread', canAcceptDirectInput=False))
        with self.assertRaises(SessionUnavailable):
            client.subscribe(CurrentSession('unused', 'thread'))

    def test_call_preserves_approval_during_resume_but_not_model_output(self):
        client = ApprovalConnection.__new__(ApprovalConnection)
        client.events, client.timeout = [], 1
        events = [approval(), dict(method='item/reasoning/delta', params=dict(text='private'))]
        identity = []
        client._send = lambda value: identity.append(json.loads(value)['id'])
        client._receive = lambda deadline: events.pop(0) if events else dict(id=identity[0], result={})
        client.call('thread/resume', {'threadId':'thread', 'excludeTurns':True})
        self.assertEqual(client.events, [approval()])

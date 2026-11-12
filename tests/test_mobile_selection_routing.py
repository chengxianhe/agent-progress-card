import json
import tempfile
import time
import unittest
from pathlib import Path

from agent_progress_card.choice import create_choice, read_choice
from agent_progress_wechat.approval_prompt import METHOD, numbered_reply
from agent_progress_wechat.approval_requests import FILE, PERMISSIONS, INPUT, MCP
from agent_progress_wechat.approval_state import ApprovalState
from agent_progress_wechat.current_session import CurrentSession
from agent_progress_wechat.files import save_json
from agent_progress_wechat.relay_service import deliver
from agent_progress_wechat.relay_store import RelayStore
from agent_progress_wechat.selection_text import card_code
from test_remote_approvals import approval
from test_mobile_requests import request, question


class CardRPC:
    def __init__(self):
        self.calls = []

    def call(self, method, params):
        self.calls.append((method, params))
        if method == 'thread/read':
            return {'thread': {'id': 'thread', 'canAcceptDirectInput': True, 'status': {'type': 'idle'}}}
        return {'turn': {'id': 'next-turn'}}

    def close(self):
        pass


class MobileSelectionRoutingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.store = RelayStore(self.path, 'owner', 'thread', since=1)
        self.addCleanup(self.store.db.close)
        self.state = ApprovalState(self.store, 'thread')
        save_json(self.path / 'activity-source.json', {'thread_id': 'thread'})
        self.rpc = CardRPC()
        self.session = CurrentSession('unused', 'thread', lambda _: self.rpc)
        self.counter = 0

    def answer(self, text, created=None):
        self.counter += 1
        self.store.ingest({'msgs': [{'message_id': 'reply-' + str(self.counter), 'from_user_id': 'owner',
            'message_type': 1, 'create_time_ms': (time.time() if created is None else created)*1000, 'context_token': 'synthetic',
            'item_list': [{'type': 1, 'text_item': {'text': text}}]}]})
        deliver(self.store, self.session, self.store.next_message(), self.path, self.state)

    def event(self, event):
        self.state.event(event, 'conn')
        row = self.store.db.execute('SELECT * FROM remote_approvals ORDER BY rowid DESC LIMIT 1').fetchone()
        self.store.sent('approval:' + row['code'], True)
        return row

    def test_number_variants_cover_command_files_sandbox_mcp_and_input(self):
        permissions = {'network': {'enabled': True}, 'fileSystem': {'read': ['/tmp/synthetic']}}
        self.state.event({'method': 'item/started', 'params': {'threadId': 'thread', 'turnId': 'turn',
            'item': {'type': 'fileChange', 'id': 'patch', 'changes': [{'path': '/tmp/synthetic.py',
            'kind': {'type': 'update', 'move_path': None}, 'diff': '-old\n+new'}]}}}, 'conn')
        formats = ['1 {c}', '选项号 {c} 回复 1', '选项号 {c} 1', '选项号 1 {c}', '回复 1 {c}']
        for method in [METHOD, FILE, PERMISSIONS, MCP, INPUT]:
            for form in formats:
                with self.subTest(method=method, reply=form):
                    identity = 1000 + self.counter
                    if method == METHOD:
                        event, payload = approval(identity), 'accept'
                    elif method == FILE:
                        event, payload = request(FILE, identity, itemId='patch'), {'decision': 'accept'}
                    elif method == PERMISSIONS:
                        event = request(PERMISSIONS, identity, permissions=permissions, cwd='/tmp')
                        payload = {'permissions': permissions, 'scope': 'turn'}
                    elif method == MCP:
                        event = request(MCP, identity)
                        payload = {'action': 'accept', 'content': {}, '_meta': None}
                    else:
                        event = request(INPUT, identity, questions=[question()])
                        payload = {'answers': {'choice': {'answers': ['Allow']}}}
                    row = self.event(event)
                    self.answer(form.format(c=row['code'].lower()))
                    expected = (identity, payload) if method == METHOD else (identity, payload, method)
                    self.assertEqual(self.state.claim('conn'), expected)
                    self.state.event({'method': 'serverRequest/resolved', 'params': {
                        'threadId': 'thread', 'requestId': identity}}, 'conn')
        self.assertEqual(self.rpc.calls, [])

    def test_explicit_card_selection_does_not_answer_pending_system_request(self):
        self.event(approval())
        choice = create_choice(self.path, '是否安装？', ['备份安装', '保留旧版'])
        self.answer('选项号 ' + card_code(choice).lower() + ' 1')
        self.assertIsNone(self.state.claim('conn'))
        self.assertIsNone(read_choice(self.path, 'thread'))
        self.assertIn('备份安装', self.rpc.calls[-1][1]['input'][0]['text'])

    def test_system_code_never_consumes_normal_card_choice(self):
        row = self.event(approval())
        choice = create_choice(self.path, '普通问题', ['甲', '乙'])
        self.answer('选项号 ' + row['code'] + ' 回复 1')
        self.assertEqual(self.state.claim('conn'), (17, 'accept'))
        self.assertEqual(read_choice(self.path, 'thread')['id'], choice['id'])
        self.assertEqual(self.rpc.calls, [])

    def test_resolved_system_history_does_not_block_new_card_number(self):
        self.event(approval())
        self.state.event({'method': 'serverRequest/resolved', 'params': {'threadId': 'thread', 'requestId': 17}}, 'conn')
        create_choice(self.path, '普通问题', ['甲', '乙'])
        self.answer('1')
        self.assertEqual(self.rpc.calls[-1][0], 'turn/start')
        self.assertIsNone(self.state.claim('conn'))

    def test_ambiguous_bare_number_and_invalid_card_code_are_not_dispatched(self):
        self.event(approval())
        choice = create_choice(self.path, '普通问题', ['甲', '乙'])
        for text in ['1', '9 ' + card_code(choice), '1 C0000000000']:
            self.answer(text)
        self.assertEqual(self.rpc.calls, [])
        self.assertIsNone(self.state.claim('conn'))
        self.assertIsNotNone(read_choice(self.path, 'thread'))

    def test_exact_allow_label_with_code_matches_once(self):
        row = self.event(approval())
        self.answer('选项号 ' + row['code'].lower() + ' 仅此次允许')
        self.assertEqual(self.state.claim('conn'), (17, 'accept'))
        self.answer('1 ' + row['code'])
        self.assertIsNone(self.state.claim('conn'))
        self.assertEqual(self.rpc.calls, [])

    def test_closed_and_expired_feedback_are_distinct_and_never_reauthorize(self):
        row = self.event(approval(1))
        self.state.event({'method': 'serverRequest/resolved', 'params': {'threadId': 'thread', 'requestId': 1}}, 'conn')
        self.answer('选项号 ' + row['code'] + ' 1')
        latest = self.store.db.execute('SELECT text FROM outbox ORDER BY rowid DESC LIMIT 1').fetchone()[0]
        self.assertIn('已关闭', latest)
        self.assertNotIn('已过期', latest)
        row = self.event(approval(2))
        self.store.db.execute('UPDATE remote_approvals SET expires=0 WHERE code=?', (row['code'],))
        self.store.db.commit()
        self.answer('1 ' + row['code'])
        latest = self.store.db.execute('SELECT text FROM outbox ORDER BY rowid DESC LIMIT 1').fetchone()[0]
        self.assertIn('已过期', latest)
        self.assertIsNone(self.state.claim('conn'))

    def test_notification_has_copyable_example_not_placeholder(self):
        row = self.event(approval())
        notice = self.store.db.execute('SELECT text FROM outbox WHERE id=?', ('approval:' + row['code'],)).fetchone()[0]
        self.assertIn('1 ' + row['code'], notice)
        self.assertNotIn('选项号 ' + row['code'], notice)
        self.assertEqual(numbered_reply('选项号 ' + row['code'].lower() + ' 回复 1'), (1, row['code']))

    def test_command_without_optional_decision_list_has_one_time_options(self):
        event = approval()
        event['params'].pop('availableDecisions')
        row = self.event(event)
        self.answer('1 ' + row['code'])
        self.assertEqual(self.state.claim('conn'), (17, 'accept'))

    def test_missing_detail_delivery_still_blocks_prefixed_numeric_reply(self):
        row = self.event(approval(command='printf hello\n' * 200))
        self.answer('选项号 ' + row['code'] + ' 回复 1')
        self.assertIsNone(self.state.claim('conn'))
        reply = self.store.db.execute('SELECT text FROM outbox ORDER BY rowid DESC LIMIT 1').fetchone()[0]
        self.assertIn('完整详情', reply)

    def test_lowercase_form_code_preserves_the_actual_json_answer(self):
        row = self.event(request(INPUT, questions=[{**question(), 'options': []}]))
        self.answer('填写 ' + row['code'].lower() + ' {"choice":"选项号 A0123456789 回复 1"}')
        self.assertEqual(self.state.claim('conn'), (71, {'answers': {'choice': {
            'answers': ['选项号 A0123456789 回复 1']}}}, INPUT))

    def test_overflow_is_not_silently_ignored(self):
        for identity in range(21):
            self.state.event(approval(identity), 'conn')
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM remote_approvals').fetchone()[0], 20)
        self.assertIsNotNone(self.store.db.execute("SELECT 1 FROM outbox WHERE id LIKE 'notice:approval-limit:%'").fetchone())

    def test_out_of_range_card_numbers_are_not_new_tasks(self):
        choice = create_choice(self.path, '普通问题', ['甲', '乙'])
        for text in ['0', '3', '9']:
            self.answer(text)
        self.assertEqual(self.rpc.calls, [])
        self.assertEqual(read_choice(self.path, 'thread')['id'], choice['id'])

    def test_old_bare_number_cannot_answer_new_choice_with_or_without_closed_history(self):
        choice = create_choice(self.path, '新的问题', ['甲', '乙'])
        self.answer('1', created=choice['created_at'] - 1)
        self.assertEqual(self.rpc.calls, [])
        self.event(approval())
        self.state.event({'method': 'serverRequest/resolved', 'params': {
            'threadId': 'thread', 'requestId': 17}}, 'conn')
        self.answer('1', created=choice['created_at'] - 1)
        self.assertEqual(self.rpc.calls, [])
        self.assertEqual(read_choice(self.path, 'thread')['id'], choice['id'])

    def test_out_of_range_system_numbers_are_not_new_tasks(self):
        self.event(approval())
        for text in ['0', '9']:
            self.answer(text)
        self.assertEqual(self.rpc.calls, [])
        self.assertIsNone(self.state.claim('conn'))

    def test_delayed_bare_number_cannot_authorize_a_new_system_request(self):
        row = self.event(approval())
        self.answer('1', created=row['created'] - 1)
        self.assertIsNone(self.state.claim('conn'))
        self.assertEqual(self.rpc.calls, [])
        reply = self.store.db.execute('SELECT text FROM outbox ORDER BY rowid DESC LIMIT 1').fetchone()[0]
        self.assertIn('早于', reply)

    def test_nonfinite_message_time_is_ignored_without_refreshing_context(self):
        for index, stamp in enumerate([float('nan'), float('inf'), -float('inf'), True]):
            self.store.ingest({'msgs': [{'message_id': 'invalid-' + str(index), 'from_user_id': 'owner',
                'message_type': 1, 'create_time_ms': stamp, 'context_token': 'invalid',
                'item_list': [{'type': 1, 'text_item': {'text': '1'}}]}]})
        self.assertIsNone(self.store.next_message())
        self.assertEqual(self.store.get('context'), '')

import json
import tempfile
import time
import unittest
from pathlib import Path

from agent_progress_wechat.approval_state import ApprovalState
from agent_progress_wechat.approval_transport import ApprovalConnection
from agent_progress_wechat.approval_requests import retained_event
from agent_progress_wechat.approval_prompt import display
from agent_progress_wechat.relay_store import RelayStore
from agent_progress_wechat.request_catalog import SERVER_REQUESTS
from test_all_message_recovery import incoming


class RequestCatalogTests(unittest.TestCase):
    def test_generated_01672_catalog_is_classified_without_matching_option_words(self):
        expected = {'item/commandExecution/requestApproval', 'item/fileChange/requestApproval',
                    'item/permissions/requestApproval', 'item/tool/requestUserInput',
                    'mcpServer/elicitation/request', 'execCommandApproval', 'applyPatchApproval',
                    'item/tool/call', 'account/chatgptAuthTokens/refresh', 'attestation/generate'}
        self.assertEqual(SERVER_REQUESTS, expected)
        for method in expected:
            self.assertTrue(retained_event({'id': 1, 'method': method, 'params': {}}), method)

    def test_both_legacy_requests_use_their_actual_response_schema_and_only_once(self):
        for method in ('execCommandApproval', 'applyPatchApproval'):
            with self.subTest(method=method), tempfile.TemporaryDirectory() as d:
                store = RelayStore(Path(d), 'owner', 'thread', since=1)
                self.addCleanup(store.db.close)
                store.put('context', 'synthetic')
                state = ApprovalState(store, 'thread')
                params = {'conversationId': 'thread', 'callId': 'item', 'reason': 'fixture',
                          'command': ['printf', 'hello world'], 'cwd': '/tmp', 'parsedCmd': [],
                          'fileChanges': {'/tmp/synthetic': {'type': 'update', 'unified_diff': '-a\n+b'}}}
                state.event({'id': 17, 'method': method, 'params': params}, 'conn')
                row = store.db.execute('SELECT * FROM remote_approvals').fetchone()
                self.assertEqual(row['state'], 'pending')
                store.sent('approval:' + row['code'], True)
                store.ingest(incoming(text='2 ' + row['code']))
                state.handle(store.next_message())
                identity, response, actual = state.claim('conn')
                self.assertEqual(actual, method)
                self.assertEqual(response, {'decision': {'denied': {'rejection': '用户拒绝本次请求'}}})
                connection = ApprovalConnection.__new__(ApprovalConnection)
                sent = []
                connection._send = sent.append
                connection.respond(identity, response, method)
                self.assertEqual(json.loads(sent[0])['result'], response)
                for invalid in ('approved_for_session', 'denied', 'timed_out'):
                    with self.assertRaises(ValueError): connection.respond(17, {'decision': invalid}, method)
                self.assertIsNone(state.claim('conn'))

    def test_unknown_scoped_backend_and_url_auth_are_visible_but_not_approvable(self):
        for method, extra in (
            ('future/requestApproval', {}), ('item/tool/call', {}),
            ('mcpServer/elicitation/request', {'mode': 'url', 'url': 'https://auth.example/private'}),
            ('applyPatchApproval', {'conversationId': 'thread', 'grantRoot': '/tmp'}),
        ):
            with self.subTest(method=method), tempfile.TemporaryDirectory() as d:
                store = RelayStore(Path(d), 'owner', 'thread', since=1)
                self.addCleanup(store.db.close)
                store.put('context', 'synthetic')
                state = ApprovalState(store, 'thread')
                state.event({'id': 1, 'method': method, 'params': {'threadId': 'thread', **extra}}, 'conn')
                row = store.db.execute('SELECT * FROM remote_approvals').fetchone()
                self.assertEqual(row['state'], 'native')
                self.assertIsNone(state.claim('conn'))
                self.assertTrue(store.db.execute('SELECT text FROM outbox').fetchone()[0])

    def test_stdin_and_network_context_preview_action_and_target_without_persistent_grants(self):
        params = {'kind': 'writeStdin', 'command': 'y\n', 'cwd': '/tmp', 'environmentId': 'test-env',
                  'networkApprovalContext': {'host': 'example.test', 'protocol': 'https'}}
        preview = display(params)
        self.assertIn('写入现有进程', preview)
        self.assertIn('example.test', preview)
        self.assertIn('test-env', preview)
        self.assertIsNone(display({**params, 'networkApprovalContext': {'host': 'example.test', 'protocol': 'ssh'}}))


if __name__ == '__main__': unittest.main()

import json
from pathlib import Path
import tempfile
import time
import unittest

from agent_progress_wechat.approval_requests import FILE, PERMISSIONS, INPUT, MCP, retained_event
from agent_progress_wechat.approval_state import ApprovalState
from agent_progress_wechat.approval_transport import ApprovalConnection
from agent_progress_wechat.approval_forms import validate_content, form_reply
from agent_progress_wechat.current_session import CurrentSession
from agent_progress_wechat.files import save_json
from agent_progress_wechat.relay_service import deliver
from agent_progress_wechat.relay_store import RelayStore


def request(method=MCP, identity=71, **changes):
    params = {'threadId': 'thread', 'turnId': 'turn', 'serverName': 'test-server', 'mode': 'form',
              'message': 'Allow read-only synthetic lookup?', 'requestedSchema': {'type': 'object', 'properties': {}},
              '_meta': {'codex_approval_kind': 'mcp_tool_call', 'tool_name': 'lookup',
                        'persist': ['session', 'always'], 'tool_params': {'query': 'synthetic'}}}
    params.update(changes)
    return {'id': identity, 'method': method, 'params': params}


def question(key='choice'):
    return {'id': key, 'header': 'test', 'question': '请选择', 'isOther': False, 'isSecret': False,
            'options': [{'label': label, 'description': description} for label, description in
                        [('Allow', '本次执行'), ('Allow for session', '本会话'), ('Always allow', '永久'), ('Cancel', '取消')]]}


class MobileRequestsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)
        self.store = RelayStore(self.path, 'owner', 'thread', since=1)
        self.state = ApprovalState(self.store, 'thread')
        save_json(self.path/'activity-source.json', {'thread_id': 'thread'})

    def tearDown(self):
        self.store.db.close()
        self.temp.cleanup()

    def event(self, value):
        self.state.event(value, 'conn')
        return self.store.db.execute('SELECT * FROM remote_approvals ORDER BY rowid DESC LIMIT 1').fetchone()

    def answer(self, text, identity='reply', owner='owner'):
        self.store.ingest({'msgs': [{'message_id': identity, 'from_user_id': owner, 'message_type': 1,
                                     'create_time_ms': time.time()*1000, 'context_token': 'context',
                                     'item_list': [{'type': 1, 'text_item': {'text': text}}]}]})
        incoming = self.store.next_message()
        if incoming:
            deliver(self.store, CurrentSession('unused', 'thread'), incoming, self.path, self.state)

    def sent(self):
        self.store.db.execute('UPDATE outbox SET delivered=1')
        self.store.db.commit()

    def test_mcp_four_options_single_allow_and_cancel_are_exact(self):
        row = self.event(request())
        self.assertEqual(row['state'], 'pending')
        choices = json.loads(row['choices'])
        self.assertEqual(len(choices), 4)
        self.assertTrue(choices[0]['label'].startswith('Allow'))
        self.assertIsNone(choices[1]['response'])
        self.assertIsNone(choices[2]['response'])
        self.sent()
        self.answer('1')
        self.assertEqual(self.state.claim('conn'), (71, {'action': 'accept', 'content': {}, '_meta': None}, MCP))
        self.assertIsNone(self.state.claim('conn'))
        row = self.event(request(identity=72))
        self.answer('4 ' + row['code'], 'cancel')
        self.assertEqual(self.state.claim('conn'), (72, {'action': 'cancel', 'content': None, '_meta': None}, MCP))

    def test_unselected_persistent_meta_never_echoed_as_response(self):
        row = self.event(request())
        self.answer('2 ' + row['code'])
        self.assertIsNone(self.state.claim('conn'))
        self.answer('1 ' + row['code'], 'one-time')
        self.assertIsNone(self.state.claim('conn')[1]['_meta'])

    def test_allow_word_requires_unique_notified_request(self):
        row = self.event(request())
        self.answer('Allow')
        self.assertIsNone(self.state.claim('conn'))
        self.sent()
        self.answer('allow', 'after-notice')
        self.assertEqual(self.state.claim('conn')[1], {'action':'accept','content':{},'_meta':None})
        self.event(request(identity=72))
        self.event(request(identity=73))
        self.sent()
        self.answer('allow', 'ambiguous')
        self.assertIsNone(self.state.claim('conn'))

    def test_native_four_options_preserve_label_and_question_id(self):
        row = self.event(request(INPUT, questions=[question()]))
        self.assertEqual(row['state'], 'pending')
        self.sent()
        self.answer('1')
        self.assertEqual(self.state.claim('conn'), (71, {'answers': {'choice': {'answers': ['Allow']}}}, INPUT))

    def test_native_multiple_questions_require_complete_explicit_answers(self):
        row = self.event(request(INPUT, questions=[question('a'), question('b')]))
        self.answer('填写 ' + row['code'] + ' {"a":1}')
        self.assertIsNone(self.state.claim('conn'))
        self.answer('填写 ' + row['code'] + ' {"a":1,"b":4}', 'complete')
        self.assertEqual(self.state.claim('conn')[1], {'answers': {'a': {'answers': ['Allow']}, 'b': {'answers': ['Cancel']}}})

    def test_free_text_and_malformed_form_replies_are_consumed_locally(self):
        q = question(); q['options'] = None
        row = self.event(request(INPUT, questions=[q]))
        self.answer('填写 ' + row['code'] + ' not-json')
        self.assertIsNone(self.state.claim('conn'))
        self.answer('填写 ' + row['code'] + ' {"choice":"用户填写的答案"}', 'valid')
        self.assertEqual(self.state.claim('conn')[1]['answers']['choice']['answers'], ['用户填写的答案'])

    def test_private_questions_and_unknown_requests_notify_without_answering(self):
        q = question(); q['isSecret'] = True
        for i, event in enumerate([request(INPUT, questions=[q]), request('item/future/requestApproval'),
                                   request(MCP, mode='openai/userVerification')]):
            event['id'] = i
            row = self.event(event)
            self.assertEqual(row['state'], 'native')
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM outbox').fetchone()[0], 3)
        self.assertIsNone(self.state.claim('conn'))

    def test_tool_parameters_cannot_be_hidden_in_approved_preview(self):
        row = self.event(request(_meta={'codex_approval_kind': 'mcp_tool_call', 'tool_name': 'lookup',
                                        'tool_params': {'token': 'private-value'}}))
        self.assertEqual(row['state'], 'native')
        self.assertNotIn('private-value', self.store.db.execute('SELECT text FROM outbox').fetchone()[0])

    def test_mcp_boolean_and_string_schema_validation(self):
        schema = {'type': 'object', 'properties': {'confirmed': {'type': 'boolean'}}, 'required': ['confirmed']}
        row = self.event(request(_meta=None, requestedSchema=schema))
        self.answer('2 ' + row['code'])
        self.assertEqual(self.state.claim('conn')[1]['content'], {'confirmed': False})
        schema = {'type': 'object', 'properties': {'target': {'type': 'string', 'minLength': 2, 'maxLength': 5}}, 'required': ['target']}
        row = self.event(request(identity=72, _meta=None, requestedSchema=schema))
        self.answer('填写 ' + row['code'] + ' {"target":"a"}', 'short')
        self.assertIsNone(self.state.claim('conn'))
        self.answer('填写 ' + row['code'] + ' {"target":"valid"}', 'valid')
        self.assertEqual(self.state.claim('conn')[1]['content'], {'target': 'valid'})

    def test_unknown_schema_constraints_are_not_silently_ignored(self):
        schema = {'type': 'object', 'properties': {'x': {'type': 'string', 'pattern': '^safe$'}}}
        self.assertEqual(self.event(request(_meta=None, requestedSchema=schema))['state'], 'native')
        with self.assertRaises(ValueError):
            form_reply('填写 A0000000000 {"x":1,"x":2}')
        with self.assertRaises(ValueError):
            validate_content({'type':'object','properties':{'x':{'type':'number'}}}, {'x':True})

    def test_permissions_echo_only_requested_subset_and_turn_scope(self):
        permissions = {'network': {'enabled': True}, 'fileSystem': {'read': ['/tmp/demo'], 'write': None}}
        row = self.event(request(PERMISSIONS, permissions=permissions, cwd='/tmp', reason='synthetic'))
        self.answer('1 ' + row['code'])
        self.assertEqual(self.state.claim('conn'), (71, {'permissions': permissions, 'scope': 'turn'}, PERMISSIONS))
        row = self.event(request(PERMISSIONS, identity=72, permissions=permissions, cwd='/tmp'))
        self.answer('2 ' + row['code'], 'deny')
        self.assertEqual(self.state.claim('conn')[1], {'permissions': {}, 'scope': 'turn'})

    def test_file_change_requires_matching_bound_item_full_diff(self):
        event = request(FILE, itemId='patch', reason='synthetic', grantRoot=None)
        row = self.event(event)
        self.assertEqual(row['state'], 'native')
        patch = {'type': 'fileChange', 'id': 'patch', 'changes': [
            {'path': '/tmp/demo.py', 'kind': {'type': 'update', 'move_path': None}, 'diff': '-old\n+new'}]}
        self.state.event({'method': 'item/started', 'params': {'threadId': 'thread', 'turnId': 'turn', 'item': patch}}, 'conn')
        event['id'] = 72
        row = self.event(event)
        self.assertIn('-old', row['preview'])
        self.answer('1 ' + row['code'])
        self.assertEqual(self.state.claim('conn'), (72, {'decision':'accept'}, FILE))

    def test_multipart_details_must_all_be_sent_before_acceptance(self):
        row = self.event(request(_meta={'codex_approval_kind':'mcp_tool_call', 'tool_name':'lookup',
                                        'tool_params':{'query':'x'*5000}}))
        self.assertEqual(row['state'], 'pending')
        parts = self.store.db.execute("SELECT id,length(text) FROM outbox WHERE id LIKE '%:part:%'").fetchall()
        self.assertGreater(len(parts), 1)
        self.assertTrue(all(r[1] < 2500 for r in parts))
        self.answer('1 ' + row['code'])
        self.assertIsNone(self.state.claim('conn'))
        self.sent()
        self.answer('1 ' + row['code'], 'after-details')
        self.assertEqual(self.state.claim('conn')[1]['action'], 'accept')

    def test_dense_long_text_redaction_keeps_credential_detection(self):
        from agent_progress_card.sanitize import clean_text
        text = 'x' * 60000 + '\nmy_api_key="synthetic-value"'
        result = clean_text(text, 64000)
        self.assertTrue(result.startswith('x' * 60000))
        self.assertNotIn('synthetic-value', result)
        self.assertIn('my_api_key=[已隐藏]', result)
        self.assertNotIn('fake-value', clean_text('prefix-token=fake-value'))

    def test_long_command_is_complete_and_last_part_is_required(self):
        command = 'printf ' + 'x' * 15900 + '\necho done'
        row = self.event(request('item/commandExecution/requestApproval', command=command, cwd='/tmp',
                                 reason='Long-command test', availableDecisions=['accept', 'cancel']))
        self.assertEqual(row['state'], 'pending')
        parts = self.store.db.execute("SELECT id,text FROM outbox WHERE id LIKE ? ORDER BY rowid",
                                      ('approval:' + row['code'] + ':part:%',)).fetchall()
        joined = ''.join(r['text'].split('\n', 1)[1] for r in parts)
        self.assertEqual(joined, row['preview'])
        self.assertIn(command, joined)
        self.assertGreater(len(parts), 5)
        self.sent()
        self.store.db.execute('UPDATE outbox SET delivered=0 WHERE id=?', (parts[-1]['id'],))
        self.store.db.commit()
        self.answer('Allow')
        self.assertIsNone(self.state.claim('conn'))
        self.assertIn('完整详情还未全部送达', self.store.db.execute("SELECT text FROM outbox WHERE id='local:reply'").fetchone()[0])
        self.sent()
        self.answer('Allow', 'all-parts-sent')
        self.assertEqual(self.state.claim('conn'), (71, 'accept'))

    def test_typed_requests_obey_owner_expiry_resolution_and_restart(self):
        row = self.event(request())
        self.answer('1 ' + row['code'], owner='stranger')
        self.assertIsNone(self.state.claim('conn'))
        self.state.event({'method':'serverRequest/resolved','params':{'threadId':'thread','requestId':71}}, 'conn')
        self.answer('1 ' + row['code'])
        self.assertIsNone(self.state.claim('conn'))
        row = self.event(request(identity=72))
        self.answer('1 ' + row['code'], 'queued')
        fresh = ApprovalState(self.store, 'thread')
        self.assertIsNone(fresh.claim('conn'))
        self.assertEqual(self.store.db.execute('SELECT state FROM remote_approvals WHERE code=?',(row['code'],)).fetchone()[0], 'expired')

    def test_transport_keeps_forms_and_file_context_but_not_reasoning(self):
        self.assertTrue(retained_event(request()))
        self.assertTrue(retained_event(request(INPUT)))
        self.assertTrue(retained_event({'method':'item/started','params':{'item':{'type':'fileChange'}}}))
        self.assertFalse(retained_event({'method':'item/started','params':{'item':{'type':'reasoning'}}}))
        client = ApprovalConnection.__new__(ApprovalConnection)
        sent = []; client._send = sent.append
        client.respond(71, {'action':'accept','content':{},'_meta':None}, MCP)
        self.assertEqual(json.loads(sent[0])['result'], {'action':'accept','content':{},'_meta':None})
        for payload, method in [({'action':'accept','content':{},'_meta':{'persist':'always'}}, MCP),
                                ({'permissions':{},'scope':'session'},PERMISSIONS),
                                ({'decision':'acceptForSession'},FILE), ({},'unknown')]:
            with self.assertRaises(ValueError):
                client.respond(71,payload,method)
        self.assertEqual(len(sent),1)


if __name__ == '__main__':
    unittest.main()

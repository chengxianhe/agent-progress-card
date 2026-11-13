import json
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from agent_progress_card.activity import ActivityReader
from agent_progress_wechat.files import save_json
from agent_progress_wechat.relay_mirror import mirror, command_reply
from agent_progress_wechat.relay_service import deliver
from agent_progress_wechat.relay_store import RelayStore


def event(identity='q', name='functions.request_user_input_async', questions=None, at=None):
    return {'type': 'response_item', 'timestamp': datetime.fromtimestamp(at or time.time(), timezone.utc).isoformat(),
        'payload': {'type': 'function_call', 'call_id': identity, 'name': name,
                    'arguments': json.dumps({'questions': questions if questions is not None else
                        [{'title': '先做哪项？', 'options': ['修复消息', '修复选项']}]})}}


class NativeQuestionTests(unittest.TestCase):
    def test_public_async_and_sync_questions_keep_options_and_safe_instructions(self):
        for name in ('functions.request_user_input_async', 'request_user_input_async', 'functions.request_user_input'):
            reader = ActivityReader('thread', 0)
            e = event(name=name)
            reader.consume(e)
            reader.consume(e)
            feed = reader.snapshot(time.time())
            question = feed['latest_question']
            self.assertIn('1. 修复消息', question['text'])
            self.assertIn('2. 修复选项', question['text'])
            self.assertIn('原客户端', question['text'])
            self.assertNotIn('choice', feed)

    def test_plan_format_free_text_and_sanitization(self):
        reader = ActivityReader('thread', 0)
        reader.consume(event(questions=[{'question': 'token=synthetic-secret 选择方案',
            'options': [{'label': '方案甲', 'description': '先确认范围'}]}, {'title': '补充说明'}]))
        text = reader.snapshot(time.time())['latest_question']['text']
        self.assertIn('方案甲：先确认范围', text)
        self.assertIn('补充说明', text)
        self.assertNotIn('synthetic-secret', text)

    def test_permissions_unknown_tools_malformed_and_before_binding_excluded(self):
        reader = ActivityReader('thread', time.time()-10)
        for name in ('exec_command', 'tools.request_user_input_async', 'approval', 'request_permissions'):
            reader.consume(event(name=name))
        self.assertIsNone(reader.snapshot(time.time())['latest_question'])
        for questions in ([{'title': 'x', 'options': [123]}], [{'title': 123}], []):
            reader.consume(event(questions=questions))
        malformed = event()
        malformed['payload']['arguments'] = 'invalid-json'
        reader.consume(malformed)
        reader.consume(event(at=1))
        self.assertIn('结构暂不支持', reader.snapshot(time.time())['latest_question']['text'])

    def test_latest_question_survives_tool_ack_and_note_window(self):
        reader = ActivityReader('thread', 0)
        reader.consume(event())
        reader.consume({'type': 'response_item', 'timestamp': datetime.now(timezone.utc).isoformat(),
            'payload': {'type': 'function_call_output', 'call_id': 'q', 'output': '{"accepted":true}'}})
        self.assertIsNotNone(reader.snapshot(time.time())['latest_question'])
        self.assertFalse(reader.snapshot(time.time())['pending'])

    def test_live_mirrored_once_replayed_queryable_but_not_pushed(self):
        with tempfile.TemporaryDirectory() as d:
            store = RelayStore(Path(d), 'owner', 'thread', since=1)
            self.addCleanup(store.db.close)
            reader = ActivityReader('thread', 0, replay_before=time.time()-1)
            reader.consume(event())
            feed = reader.snapshot(time.time())
            mirror(store, {}, feed)
            mirror(store, {}, feed)
            self.assertEqual(1, store.db.execute("SELECT count(*) FROM outbox WHERE id LIKE 'prompt:%'").fetchone()[0])
            reader.replay_before = time.time()+10
            reader.consume(event(identity='old'))
            feed = reader.snapshot(time.time())
            mirror(store, {}, feed)
            self.assertEqual(1, store.db.execute("SELECT count(*) FROM outbox WHERE id LIKE 'prompt:%'").fetchone()[0])
            self.assertIn('修复消息', command_reply('选项', {}, feed))

    def test_wechat_query_and_number_do_not_answer_original_form_or_start_task(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            store = RelayStore(root, 'owner', 'thread', since=1)
            self.addCleanup(store.db.close)
            reader = ActivityReader('thread', 0)
            reader.consume(event())
            save_json(root/'activity-source.json', {'thread_id': 'thread'})
            save_json(root/'activity-heartbeat.json', {'thread_id': 'thread', 'checked_at': time.time()})
            save_json(root/'activity.json', reader.snapshot(time.time()))
            save_json(root/'state.json', {})
            for identity, text in [('query', '选项'), ('number', '2')]:
                store.ingest({'msgs':[{'from_user_id':'owner','message_type':1,'message_id':identity,
                    'context_token':'synthetic','create_time_ms':time.time()*1000,
                    'item_list':[{'type':1,'text_item':{'text':text}}]}]})
                deliver(store, SimpleNamespace(thread_id='thread'), store.next_message(), root)
                self.assertEqual('local', store.db.execute('SELECT status FROM inbox WHERE id=?',(identity,)).fetchone()[0])
            messages = [r[0] for r in store.db.execute('SELECT text FROM outbox')]
            self.assertIn('修复选项', messages[0])
            self.assertIn('没有代答', messages[1])

    def test_two_prompts_between_polls_both_enqueue(self):
        with tempfile.TemporaryDirectory() as d:
            store = RelayStore(Path(d), 'owner', 'thread', since=1)
            self.addCleanup(store.db.close)
            reader = ActivityReader('thread', 0)
            reader.consume(event(identity='first'))
            reader.consume(event(identity='second'))
            mirror(store, {}, reader.snapshot(time.time()))
            self.assertEqual(2, store.db.execute("SELECT count(*) FROM outbox WHERE id LIKE 'prompt:%'").fetchone()[0])

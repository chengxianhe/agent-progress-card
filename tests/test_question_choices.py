import json
import tempfile
import time
import unittest
from pathlib import Path

from agent_progress_card.activity import ActivityReader
from agent_progress_card.choice import read_choice
from agent_progress_card.question_choice import parse, sync, answer
from agent_progress_card.watcher import atomic_json
from agent_progress_wechat.chat_form import deliver_form
from agent_progress_wechat.relay_store import RelayStore
from agent_progress_wechat.selection_text import card_code
from test_native_question import event


class QuestionChoicesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        atomic_json(self.root/'activity-source.json', {'thread_id': 'thread'})

    def test_live_two_option_async_question_becomes_one_repliable_choice(self):
        reader = ActivityReader('thread', 0)
        reader.consume(event())
        prompt = reader.snapshot(time.time())['chat_prompt']
        sync(self.root, prompt, 'thread')
        first = read_choice(self.root, 'thread')
        self.assertEqual(first['options'], ['修复消息', '修复选项'])
        sync(self.root, prompt, 'thread')
        self.assertEqual(first, read_choice(self.root, 'thread'))

    def test_only_live_async_questions_convert_not_sync_permissions_history_or_secrets(self):
        for name in ('functions.request_user_input', 'item/permissions/requestApproval', 'exec_command'):
            self.assertIsNone(parse(event(name=name)['payload'], time.time(), 0))
        self.assertIsNone(parse(event(questions=[{'title': 'token=synthetic-secret'}])['payload'], time.time(), 0))
        self.assertIsNone(parse(event(questions=[{'title': 'secret', 'isSecret': True}])['payload'], time.time(), 0))
        self.assertIsNone(parse(event(questions=[{'title': 'x', 'options': 'bad'}])['payload'], time.time(), 0))
        prompt = parse(event()['payload'], 1, 2)
        sync(self.root, prompt, 'thread')
        self.assertIsNone(read_choice(self.root, 'thread'))

    def test_multiquestion_and_free_text_have_strict_complete_chat_answers(self):
        questions = [{'title': '请选择', 'options': ['a', 'b']}, {'title': '补充说明'}]
        prompt = parse(event(questions=questions)['payload'], time.time(), 0)
        sync(self.root, prompt, 'thread')
        choice = read_choice(self.root, 'thread')
        text = answer(choice, {'q1': 'b', 'q2': 'details'})
        self.assertIn('回答：b', text)
        self.assertIn('回答：details', text)
        self.assertIn('不代交原生表单', text)
        for bad in ({'q1': 'a'}, {'q1': 'wrong', 'q2': 'x'}, {'q1': 'a', 'q2': 'token=synthetic'}):
            with self.assertRaises(ValueError): answer(choice, bad)

    def test_new_user_input_retires_auto_choice_without_replaying_it(self):
        reader = ActivityReader('thread', 0)
        reader.consume(event())
        sync(self.root, reader.chat_prompt, 'thread')
        reader.consume({'type': 'event_msg', 'timestamp': __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),
                        'payload': {'type': 'user_message', 'message': 'answer'}})
        sync(self.root, reader.chat_prompt, 'thread')
        self.assertIsNone(read_choice(self.root, 'thread'))

    def test_manual_choice_is_never_replaced_and_thread_mismatch_refused(self):
        from agent_progress_card.choice import create_choice
        first = create_choice(self.root, 'manual', ['a', 'b'])
        sync(self.root, parse(event()['payload'], time.time(), 0), 'thread')
        self.assertEqual(first, read_choice(self.root, 'thread'))
        with self.assertRaises(ValueError): sync(self.root, None, 'another-thread')

    def test_concurrent_manual_publish_does_not_break_activity_collection(self):
        from unittest.mock import patch
        from agent_progress_card.choice import create_choice
        def race(*args, **kwargs):
            create_choice(self.root, 'manual won', ['a', 'b'])
            return create_choice(*args, **kwargs)
        with patch('agent_progress_card.choice.create_choice', side_effect=race):
            sync(self.root, parse(event()['payload'], time.time(), 0), 'thread')
        self.assertEqual(read_choice(self.root, 'thread')['question'], 'manual won')

    def test_long_form_details_are_complete_and_missing_part_prevents_phone_answer(self):
        from agent_progress_wechat.choice_notice import publish, incomplete
        from agent_progress_wechat.relay_mirror import choice_text
        questions = [{'title': 'Question ' + str(i), 'options': [str(j) + 'x'*170 for j in range(8)]} for i in range(3)]
        sync(self.root, parse(event(questions=questions)['payload'], time.time(), 0), 'thread')
        choice = read_choice(self.root, 'thread')
        store = RelayStore(self.root/'wechat', 'owner', 'thread', since=1)
        self.addCleanup(store.db.close)
        store.put('context', 'synthetic')
        publish(store, choice)
        parts = store.db.execute("SELECT * FROM outbox WHERE id LIKE ? ORDER BY rowid", ('choice:' + choice['id'] + ':part:%',)).fetchall()
        self.assertGreater(len(parts), 1)
        self.assertEqual(''.join(r['text'].split('\n', 1)[1] for r in parts), choice_text(choice))
        self.assertTrue(incomplete(store, choice))
        for row in parts: store.sent(row['id'], True)
        self.assertFalse(incomplete(store, choice))

    def test_explicit_form_answer_is_delivered_as_chat_not_permission_rpc(self):
        prompt = parse(event(questions=[{'title': '补充说明'}])['payload'], time.time(), 0)
        sync(self.root, prompt, 'thread')
        choice = read_choice(self.root, 'thread')
        captured = []
        class Connection:
            def call(self, method, params):
                captured.append((method, params)); return {'turn': {'id': 'turn'}}
            def close(self): pass
        class Session:
            thread_id = 'thread'
            def open(self): return Connection()
            def prepare(self, connection, text, identity): return 'turn/start', {'text': text}
        store = RelayStore(self.root/'wechat', 'owner', 'thread', since=1)
        self.addCleanup(store.db.close)
        store.put('context', 'synthetic')
        message = {'id': 'reply', 'text': '填写 ' + card_code(choice) + ' {"q1":"details"}', 'created': time.time()}
        store.db.execute('INSERT INTO inbox(id,text,status,created) VALUES (?,?,?,?)', ('reply', message['text'], 'queued', message['created']))
        self.assertTrue(deliver_form(store, Session(), message, self.root))
        self.assertEqual(captured[0][0], 'turn/start')
        self.assertIn('details', captured[0][1]['text'])
        self.assertIsNone(read_choice(self.root, 'thread'))


if __name__ == '__main__': unittest.main()
